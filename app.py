"""
Business Intelligence Scraper - Flask Backend
Scrapes Google, Yelp, Yellow Pages for businesses
with contacts, emails, phones, socials, key people.

Install: pip install flask flask-cors requests beautifulsoup4 gunicorn lxml
Run:     python app.py
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import re, time, json, logging, csv, io, random
import requests as req
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urljoin, urlparse, quote_plus

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }

def safe_get(url, timeout=12):
    try:
        time.sleep(random.uniform(0.5, 1.5))
        r = req.get(url, headers=get_headers(), timeout=timeout)
        if r.status_code == 200:
            return r.text
        return ""
    except Exception as e:
        log.warning(f"GET failed {url}: {e}")
        return ""

EMAIL_RE  = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
PHONE_RE  = r"(?:\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}"
PHONE_BD  = r"(?:\+880|0)1[3-9]\d{8}"

SOCIAL_RE = {
    "facebook":  r"(?:https?://)?(?:www\.)?facebook\.com/(?!sharer|share|dialog)[A-Za-z0-9_.%-]+",
    "instagram": r"(?:https?://)?(?:www\.)?instagram\.com/[A-Za-z0-9_.%-]+",
    "twitter":   r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+",
    "linkedin":  r"(?:https?://)?(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_%-]+",
    "youtube":   r"(?:https?://)?(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.%-]+",
    "tiktok":    r"(?:https?://)?(?:www\.)?tiktok\.com/@[A-Za-z0-9_.%-]+",
}

def extract_emails(text):
    found = re.findall(EMAIL_RE, text)
    bad_ext = (".png",".jpg",".gif",".svg",".webp",".css",".js",".php")
    return list({e for e in found if not any(e.endswith(x) for x in bad_ext)})

def extract_phones(text):
    found = re.findall(PHONE_RE, text) + re.findall(PHONE_BD, text)
    cleaned = []
    for p in found:
        p = p.strip()
        digits = re.sub(r"\D","",p)
        if 7 <= len(digits) <= 15:
            cleaned.append(p)
    return list(dict.fromkeys(cleaned))[:3]

def extract_socials(text):
    result = {}
    for platform, pattern in SOCIAL_RE.items():
        found = re.findall(pattern, text, re.IGNORECASE)
        if found:
            url = found[0]
            if not url.startswith("http"):
                url = "https://" + url
            # Filter out false positives
            if platform == "facebook" and any(x in url for x in ["/home","/login","/ads"]):
                continue
            result[platform] = url
    return result


# ══════════════════════════════════════════════════════════
#  SOURCE 1 - Google Search
# ══════════════════════════════════════════════════════════
def search_google(query, num=20):
    businesses = []
    seen = set()
    for page in range(0, min(num * 2, 60), 10):
        url = f"https://www.google.com/search?q={quote_plus(query)}&start={page}&num=10"
        html = safe_get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        for result in soup.select("div.g"):
            title_el = result.select_one("h3")
            link_el  = result.select_one("a[href]")
            desc_el  = result.select_one("div.VwiC3b, span.st")
            if not title_el or not link_el:
                continue
            name = title_el.get_text(strip=True)
            href = link_el.get("href","")
            if not href.startswith("http") or "google.com" in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            desc   = desc_el.get_text(strip=True)[:250] if desc_el else ""
            domain = urlparse(href).netloc.replace("www.","")
            businesses.append({
                "name": name, "website": href,
                "domain": domain, "description": desc, "source": "Google",
            })
        if len(businesses) >= num:
            break
    return businesses[:num]


# ══════════════════════════════════════════════════════════
#  SOURCE 2 - Yelp
# ══════════════════════════════════════════════════════════
def search_yelp(niche, location, num=20):
    businesses = []
    for page in range(0, min(num, 40), 10):
        url = f"https://www.yelp.com/search?find_desc={quote_plus(niche)}&find_loc={quote_plus(location)}&start={page}"
        html = safe_get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("div[data-testid='serp-ia-card'], li.regular-search-result"):
            name_el = card.select_one("h3 a, a.css-19v1rkv, span.css-1egxyvc")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            link = name_el.get("href","")
            if link and not link.startswith("http"):
                link = "https://www.yelp.com" + link
            phone_el  = card.select_one("p[class*='phone'], span[class*='phone']")
            addr_el   = card.select_one("address, span[class*='address']")
            rating_el = card.select_one("div[aria-label*='star']")
            businesses.append({
                "name":     name,
                "phone":    phone_el.get_text(strip=True) if phone_el else "",
                "address":  addr_el.get_text(strip=True) if addr_el else "",
                "rating":   rating_el.get("aria-label","").replace(" star rating","") if rating_el else "",
                "yelp_url": link,
                "source":   "Yelp",
            })
        if len(businesses) >= num:
            break
    return businesses[:num]


# ══════════════════════════════════════════════════════════
#  SOURCE 3 - Yellow Pages
# ══════════════════════════════════════════════════════════
def search_yellowpages(niche, location, num=20):
    businesses = []
    for page in range(1, 4):
        url = f"https://www.yellowpages.com/search?search_terms={quote_plus(niche)}&geo_location_terms={quote_plus(location)}&page={page}"
        html = safe_get(url)
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("div.result, div.organic"):
            name_el = card.select_one("a.business-name, h2.n span")
            if not name_el:
                continue
            name    = name_el.get_text(strip=True)
            phone   = card.select_one("div.phones, a.phone")
            addr    = card.select_one("p.adr, div.street-address")
            web_el  = card.select_one("a.track-visit-website")
            cats    = card.select("div.categories a")
            businesses.append({
                "name":     name,
                "phone":    phone.get_text(strip=True) if phone else "",
                "address":  addr.get_text(strip=True) if addr else "",
                "website":  web_el.get("href","") if web_el else "",
                "category": ", ".join(c.get_text(strip=True) for c in cats),
                "source":   "Yellow Pages",
            })
        if len(businesses) >= num:
            break
    return businesses[:num]


# ══════════════════════════════════════════════════════════
#  WEBSITE DEEP SCRAPE
# ══════════════════════════════════════════════════════════
def scrape_website(url):
    data = {"emails":[], "phones":[], "socials":{}, "people":[], "address":""}
    if not url:
        return data

    pages = [url]
    for slug in ["/contact","/about","/about-us","/contact-us","/team","/our-team","/leadership"]:
        pages.append(url.rstrip("/") + slug)

    combined = ""
    for p in pages[:5]:
        html = safe_get(p)
        if html:
            combined += html

    if not combined:
        return data

    data["emails"]  = extract_emails(combined)[:5]
    data["phones"]  = extract_phones(combined)[:3]
    data["socials"] = extract_socials(combined)

    soup = BeautifulSoup(combined, "lxml")

    # Address
    addr_el = soup.select_one("address,[class*='address'],[itemprop='address']")
    if addr_el:
        data["address"] = addr_el.get_text(separator=" ",strip=True)[:200]

    # Key people
    people = []
    selectors = [
        "div[class*='team'] [class*='member']",
        "div[class*='people'] [class*='person']",
        "div[class*='staff'] [class*='card']",
        "div[class*='leadership'] [class*='card']",
        "article[class*='team']",
        "li[class*='team-member']",
    ]
    blocks = []
    for sel in selectors:
        blocks += soup.select(sel)
        if len(blocks) >= 6:
            break

    for block in blocks[:6]:
        name_el = block.select_one("h2,h3,h4,h5,strong,[class*='name']")
        role_el = block.select_one("[class*='title'],[class*='role'],[class*='position'],[class*='job'],p")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if len(name) < 3 or len(name) > 60:
            continue
        role = role_el.get_text(strip=True) if role_el else ""
        block_str = str(block)
        p_emails = extract_emails(block_str)
        p_phones = extract_phones(block_str)
        li_m = re.search(r"linkedin\.com/in/[A-Za-z0-9_%-]+", block_str, re.I)
        people.append({
            "name":     name,
            "role":     role[:80],
            "email":    p_emails[0] if p_emails else "",
            "phone":    p_phones[0] if p_phones else "",
            "linkedin": "https://"+li_m.group(0) if li_m else "",
        })

    data["people"] = people[:3]
    return data


# ══════════════════════════════════════════════════════════
#  MERGE + ENRICH
# ══════════════════════════════════════════════════════════
def merge(all_results, max_n):
    seen = set()
    out  = []
    for b in all_results:
        name = b.get("name","").strip()
        if not name or len(name) < 2:
            continue
        key = re.sub(r"[^a-z0-9]","",name.lower())[:18]
        if key in seen:
            continue
        seen.add(key)
        out.append(b)
        if len(out) >= max_n:
            break
    return out

def enrich(biz):
    website = biz.get("website","")
    if not website:
        return biz
    log.info(f"  Enriching: {biz.get('name','?')}")
    try:
        sd = scrape_website(website)
        if sd["emails"] and not biz.get("email"):
            biz["email"] = sd["emails"][0]
        biz["all_emails"] = sd["emails"]
        if sd["phones"] and not biz.get("phone"):
            biz["phone"] = sd["phones"][0]
        if not biz.get("address") and sd["address"]:
            biz["address"] = sd["address"]
        soc = biz.get("socials",{})
        soc.update(sd["socials"])
        biz["socials"] = soc
        for k,v in soc.items():
            if not biz.get(k): biz[k] = v
        biz["people"] = sd["people"]
    except Exception as e:
        log.error(f"Enrich error: {e}")
    return biz


# ══════════════════════════════════════════════════════════
#  API ROUTES
# ══════════════════════════════════════════════════════════
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","time":datetime.now().isoformat()})


@app.route("/scrape", methods=["POST"])
def scrape():
    body     = request.get_json() or {}
    niche    = body.get("niche","").strip()
    location = body.get("location","").strip()
    max_res  = min(int(body.get("max_results", 10)), 50)
    sources  = body.get("sources", ["google","yelp","yellowpages"])

    if not niche or not location:
        return jsonify({"error":"niche and location are required"}), 400

    query = f"{niche} {location}"
    log.info(f"Query: '{query}' | max={max_res} | sources={sources}")

    all_raw = []
    per = max(max_res // max(len(sources),1), 5)

    if "google" in sources:
        all_raw += search_google(f"{niche} business {location}", per)
    if "yelp" in sources:
        all_raw += search_yelp(niche, location, per)
    if "yellowpages" in sources:
        all_raw += search_yellowpages(niche, location, per)

    businesses = merge(all_raw, max_res)
    log.info(f"Merged {len(businesses)} unique businesses")

    enriched = []
    for b in businesses:
        enriched.append(enrich(b))

    results = []
    for b in enriched:
        s = b.get("socials",{})
        results.append({
            "name":        b.get("name",""),
            "address":     b.get("address",""),
            "phone":       b.get("phone",""),
            "website":     b.get("website",""),
            "email":       b.get("email",""),
            "all_emails":  b.get("all_emails",[]),
            "description": b.get("description","")[:300],
            "rating":      b.get("rating",""),
            "category":    b.get("category",""),
            "source":      b.get("source",""),
            "facebook":    b.get("facebook") or s.get("facebook",""),
            "instagram":   b.get("instagram") or s.get("instagram",""),
            "linkedin":    b.get("linkedin") or s.get("linkedin",""),
            "twitter":     b.get("twitter") or s.get("twitter",""),
            "youtube":     b.get("youtube") or s.get("youtube",""),
            "tiktok":      b.get("tiktok") or s.get("tiktok",""),
            "people":      b.get("people",[]),
            "yelp_url":    b.get("yelp_url",""),
        })

    return jsonify({
        "query":      query,
        "count":      len(results),
        "results":    results,
        "scraped_at": datetime.now().strftime("%d %b %Y, %H:%M"),
    })


@app.route("/export-csv", methods=["POST"])
def export_csv():
    body    = request.get_json() or {}
    results = body.get("results",[])
    fields  = ["name","address","phone","email","website",
               "facebook","instagram","linkedin","twitter","youtube","tiktok",
               "rating","category","source","description"]
    buf = io.StringIO()
    w   = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in results:
        w.writerow(r)
        for p in r.get("people",[]):
            w.writerow({
                "name":     f"  -> {p.get('name','')} ({p.get('role','')})",
                "phone":    p.get("phone",""),
                "email":    p.get("email",""),
                "linkedin": p.get("linkedin",""),
            })
    return Response(buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition":"attachment; filename=business_intel.csv"})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
