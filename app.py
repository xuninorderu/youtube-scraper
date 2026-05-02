"""
Business Intelligence Scraper - Flask Backend v3
Uses multiple reliable methods to find businesses.

Install: pip install flask flask-cors requests beautifulsoup4 gunicorn lxml
Run:     python app.py
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import re, time, logging, csv, io, random, json
import requests as req
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlparse

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ════════════════════════════════════════════════
#  OPTIONAL: Free API keys for better results
#  SerpAPI: https://serpapi.com (100 free/month)
#  Places: uses Google Places free tier
# ════════════════════════════════════════════════
SERP_API_KEY = ""   # paste your SerpAPI key here for best results

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

SESSION = req.Session()

def get_headers(referer="https://www.google.com"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Cache-Control": "max-age=0",
    }

def safe_get(url, timeout=15, referer="https://www.google.com"):
    try:
        time.sleep(random.uniform(1.0, 2.5))
        r = SESSION.get(url, headers=get_headers(referer), timeout=timeout)
        if r.status_code == 200:
            return r.text
        log.warning(f"HTTP {r.status_code} for {url}")
        return ""
    except Exception as e:
        log.warning(f"GET failed {url}: {e}")
        return ""

# ════════════════════════════════════════════════
#  PATTERNS
# ════════════════════════════════════════════════
EMAIL_RE = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
PHONE_RE = r"[\+\(]?[1-9][0-9\s\.\-\(\)]{7,}[0-9]"
SOCIAL_RE = {
    "facebook":  r"(?:https?://)?(?:www\.)?facebook\.com/(?!sharer|share|dialog|home\.php|login)[A-Za-z0-9_.%-]{3,}",
    "instagram": r"(?:https?://)?(?:www\.)?instagram\.com/[A-Za-z0-9_.%-]{2,}",
    "twitter":   r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/(?!share|intent)[A-Za-z0-9_]{2,}",
    "linkedin":  r"(?:https?://)?(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_%-]{2,}",
    "youtube":   r"(?:https?://)?(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.%-]{2,}",
    "tiktok":    r"(?:https?://)?(?:www\.)?tiktok\.com/@[A-Za-z0-9_.%-]{2,}",
}

def clean_emails(text):
    found = re.findall(EMAIL_RE, text)
    bad = (".png",".jpg",".gif",".svg",".webp",".css",".js",".php","example.","test@","noreply","no-reply","@sentry","@email.","wixpress","squarespace")
    return list({e.lower() for e in found if not any(b in e.lower() for b in bad)})

def clean_phones(text):
    found = re.findall(PHONE_RE, text)
    out = []
    for p in found:
        digits = re.sub(r"\D","",p)
        if 7 <= len(digits) <= 15:
            out.append(p.strip())
    return list(dict.fromkeys(out))[:3]

def clean_socials(text):
    result = {}
    for platform, pattern in SOCIAL_RE.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if not m.startswith("http"):
                m = "https://" + m
            # Extra validation
            path = urlparse(m).path.strip("/")
            if len(path) > 2 and path not in ["home","login","signup","register"]:
                result[platform] = m
                break
    return result

# ════════════════════════════════════════════════
#  SOURCE 1: DuckDuckGo (no bot detection)
# ════════════════════════════════════════════════
def search_duckduckgo(query, num=20):
    """DuckDuckGo HTML search — most reliable, no API needed."""
    results = []
    seen = set()

    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html = safe_get(url, referer="https://duckduckgo.com")
    if not html:
        return results

    soup = BeautifulSoup(html, "lxml")
    for result in soup.select("div.result, div.web-result"):
        title_el = result.select_one("a.result__a, h2 a")
        url_el   = result.select_one("a.result__url, span.result__url")
        desc_el  = result.select_one("a.result__snippet, div.result__body")

        if not title_el:
            continue

        name = title_el.get_text(strip=True)
        href = title_el.get("href","")

        # DuckDuckGo uses redirect URLs — extract real URL
        if "uddg=" in href:
            import urllib.parse
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href = parsed.get("uddg",[""])[0]

        if not href or not href.startswith("http"):
            if url_el:
                href = "https://" + url_el.get_text(strip=True).strip()
            else:
                continue

        if any(x in href for x in ["duckduckgo","google.com","bing.com","yahoo.com",
                                     "wikipedia","youtube.com","facebook.com"]):
            continue
        if href in seen:
            continue
        seen.add(href)

        desc   = desc_el.get_text(strip=True)[:250] if desc_el else ""
        domain = urlparse(href).netloc.replace("www.","")

        results.append({
            "name":        name,
            "website":     href,
            "domain":      domain,
            "description": desc,
            "source":      "DuckDuckGo",
        })

        if len(results) >= num:
            break

    log.info(f"DuckDuckGo: {len(results)} results for '{query}'")
    return results

# ════════════════════════════════════════════════
#  SOURCE 2: Bing Search (more lenient than Google)
# ════════════════════════════════════════════════
def search_bing(query, num=20):
    results = []
    seen = set()

    for offset in range(0, min(num * 2, 40), 10):
        url  = f"https://www.bing.com/search?q={quote_plus(query)}&first={offset+1}&count=10"
        html = safe_get(url, referer="https://www.bing.com")
        if not html:
            break

        soup = BeautifulSoup(html, "lxml")
        for li in soup.select("li.b_algo"):
            title_el = li.select_one("h2 a")
            desc_el  = li.select_one("div.b_caption p, p.b_algoSlug")
            if not title_el:
                continue

            name = title_el.get_text(strip=True)
            href = title_el.get("href","")

            if not href.startswith("http"):
                continue
            if any(x in href for x in ["bing.com","microsoft.com","msn.com","wikipedia"]):
                continue
            if href in seen:
                continue
            seen.add(href)

            desc   = desc_el.get_text(strip=True)[:250] if desc_el else ""
            domain = urlparse(href).netloc.replace("www.","")

            results.append({
                "name":        name,
                "website":     href,
                "domain":      domain,
                "description": desc,
                "source":      "Bing",
            })

        if len(results) >= num:
            break

    log.info(f"Bing: {len(results)} results for '{query}'")
    return results

# ════════════════════════════════════════════════
#  SOURCE 3: Yellow Pages
# ════════════════════════════════════════════════
def search_yellowpages(niche, location, num=20):
    results = []
    niche_slug    = niche.lower().replace(" ","-")
    location_slug = location.lower().replace(" ","-").replace(",","-")

    for page in range(1, 4):
        url  = f"https://www.yellowpages.com/search?search_terms={quote_plus(niche)}&geo_location_terms={quote_plus(location)}&page={page}"
        html = safe_get(url, referer="https://www.yellowpages.com")
        if not html:
            break

        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.result, div.organic, div[class*='result']")
        if not cards:
            # Try alternate selectors
            cards = soup.select("div.info-section, article")

        for card in cards:
            name_el = card.select_one("a.business-name, h2 a, h3 a, .business-name")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            phone_el = card.select_one("div.phones, a.phone, .phone")
            addr_el  = card.select_one("p.adr, .street-address, address")
            web_el   = card.select_one("a.track-visit-website, a[href*='http']")
            cats_el  = card.select("div.categories a, .categories a")

            website = ""
            if web_el:
                href = web_el.get("href","")
                if href.startswith("http") and "yellowpages" not in href:
                    website = href

            results.append({
                "name":     name,
                "phone":    phone_el.get_text(strip=True) if phone_el else "",
                "address":  addr_el.get_text(separator=" ",strip=True) if addr_el else "",
                "website":  website,
                "category": ", ".join(c.get_text(strip=True) for c in cats_el[:3]),
                "source":   "Yellow Pages",
            })

        if len(results) >= num:
            break

    log.info(f"Yellow Pages: {len(results)} results")
    return results[:num]

# ════════════════════════════════════════════════
#  SOURCE 4: SerpAPI (optional, most reliable)
# ════════════════════════════════════════════════
def search_serpapi(query, num=20):
    if not SERP_API_KEY:
        return []
    try:
        url = "https://serpapi.com/search"
        params = {
            "q": query, "api_key": SERP_API_KEY,
            "engine": "google", "num": num,
        }
        r = req.get(url, params=params, timeout=15)
        data = r.json()
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "name":        item.get("title",""),
                "website":     item.get("link",""),
                "description": item.get("snippet","")[:250],
                "domain":      urlparse(item.get("link","")).netloc.replace("www.",""),
                "source":      "Google (SerpAPI)",
            })
        log.info(f"SerpAPI: {len(results)} results")
        return results
    except Exception as e:
        log.error(f"SerpAPI error: {e}")
        return []

# ════════════════════════════════════════════════
#  WEBSITE DEEP SCRAPER
# ════════════════════════════════════════════════
def scrape_website(url):
    data = {"emails":[], "phones":[], "socials":{}, "people":[], "address":""}
    if not url:
        return data

    # Pages to check
    pages = [url]
    base = url.rstrip("/")
    for slug in ["/contact","/about","/about-us","/contact-us","/team","/our-team"]:
        pages.append(base + slug)

    combined = ""
    for page_url in pages[:4]:
        html = safe_get(page_url, referer=url)
        if html:
            combined += html

    if not combined:
        return data

    data["emails"]  = clean_emails(combined)[:5]
    data["phones"]  = clean_phones(combined)[:3]
    data["socials"] = clean_socials(combined)

    soup = BeautifulSoup(combined, "lxml")

    # Address
    for sel in ["address","[class*='address']","[itemprop='address']","[class*='location']"]:
        el = soup.select_one(sel)
        if el:
            addr = el.get_text(separator=" ", strip=True)
            if len(addr) > 10:
                data["address"] = addr[:200]
                break

    # Key people — try many selector patterns
    people = []
    person_selectors = [
        "[class*='team-member']","[class*='team_member']",
        "[class*='staff-member']","[class*='person']",
        "[class*='people'] [class*='card']",
        "[class*='team'] [class*='card']",
        "[class*='leadership'] [class*='item']",
        "[class*='about'] [class*='member']",
    ]
    blocks = []
    for sel in person_selectors:
        blocks = soup.select(sel)
        if blocks:
            break

    # Also try schema.org Person markup
    if not blocks:
        blocks = soup.select("[itemtype*='Person']")

    for block in blocks[:6]:
        name_el = block.select_one(
            "h2,h3,h4,h5,strong,[class*='name'],[itemprop='name']"
        )
        role_el = block.select_one(
            "[class*='title'],[class*='role'],[class*='position'],"
            "[class*='job'],[itemprop='jobTitle'],p"
        )
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if len(name) < 3 or len(name) > 60 or any(c.isdigit() for c in name[:3]):
            continue

        role   = role_el.get_text(strip=True)[:80] if role_el else ""
        bstr   = str(block)
        emails = clean_emails(bstr)
        phones = clean_phones(bstr)
        li     = re.search(r"linkedin\.com/in/[A-Za-z0-9_%-]+", bstr, re.I)

        people.append({
            "name":     name,
            "role":     role,
            "email":    emails[0] if emails else "",
            "phone":    phones[0] if phones else "",
            "linkedin": "https://"+li.group(0) if li else "",
        })

    data["people"] = people[:3]
    return data

# ════════════════════════════════════════════════
#  MERGE + ENRICH
# ════════════════════════════════════════════════
def merge(all_results, max_n):
    seen = set()
    out  = []
    for b in all_results:
        name = b.get("name","").strip()
        if not name or len(name) < 2:
            continue
        key = re.sub(r"[^a-z0-9]","", name.lower())[:20]
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
        log.error(f"Enrich error for {biz.get('name')}: {e}")
    return biz

def normalize(b):
    s = b.get("socials",{})
    return {
        "name":       b.get("name",""),
        "address":    b.get("address",""),
        "phone":      b.get("phone",""),
        "website":    b.get("website",""),
        "email":      b.get("email",""),
        "all_emails": b.get("all_emails",[]),
        "description":b.get("description","")[:300],
        "rating":     b.get("rating",""),
        "category":   b.get("category",""),
        "source":     b.get("source",""),
        "facebook":   b.get("facebook") or s.get("facebook",""),
        "instagram":  b.get("instagram") or s.get("instagram",""),
        "linkedin":   b.get("linkedin") or s.get("linkedin",""),
        "twitter":    b.get("twitter") or s.get("twitter",""),
        "youtube":    b.get("youtube") or s.get("youtube",""),
        "tiktok":     b.get("tiktok") or s.get("tiktok",""),
        "people":     b.get("people",[]),
        "yelp_url":   b.get("yelp_url",""),
    }

# ════════════════════════════════════════════════
#  ROUTES
# ════════════════════════════════════════════════
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
    log.info(f"=== SCRAPE: '{query}' max={max_res} sources={sources} ===")

    all_raw = []
    per     = max(max_res, 10)   # get plenty from each source

    # Always use DuckDuckGo + Bing as reliable base
    log.info("Searching DuckDuckGo...")
    all_raw += search_duckduckgo(f"{niche} company {location}", per)

    log.info("Searching Bing...")
    all_raw += search_bing(f"{niche} business {location}", per)

    # SerpAPI if key provided
    if SERP_API_KEY:
        all_raw += search_serpapi(query, per)

    # Yellow Pages if selected
    if "yellowpages" in sources:
        log.info("Searching Yellow Pages...")
        all_raw += search_yellowpages(niche, location, per)

    log.info(f"Raw results before merge: {len(all_raw)}")

    businesses = merge(all_raw, max_res)
    log.info(f"After merge: {len(businesses)} unique businesses")

    # Enrich with website scraping
    enriched = []
    for b in businesses:
        enriched.append(enrich(b))

    results = [normalize(b) for b in enriched]

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
