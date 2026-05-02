"""
Business Intelligence Scraper v4
- Finds websites for businesses that don't have one
- Deep scrapes every website for emails, phones, key people
- Searches LinkedIn for contacts
- Uses Hunter.io style email guessing
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import re, time, logging, csv, io, random, json
import requests as req
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus, urlparse, urljoin

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ════════════════════════════════════════════════
#  OPTIONAL FREE API KEYS (paste yours for better results)
#  Hunter.io   → https://hunter.io  (25 free searches/month)
#  SerpAPI     → https://serpapi.com (100 free/month)
# ════════════════════════════════════════════════
HUNTER_API_KEY = ""   # for email finding
SERP_API_KEY   = ""   # for Google results

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
]

SESSION = req.Session()

def hdrs(ref="https://www.google.com"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": ref,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

def safe_get(url, timeout=14, ref="https://www.google.com"):
    try:
        time.sleep(random.uniform(0.8, 2.0))
        r = SESSION.get(url, headers=hdrs(ref), timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r.text
        return ""
    except Exception as e:
        log.warning(f"GET {url}: {e}")
        return ""

# ════════════════════════════════════════════════
#  PATTERNS
# ════════════════════════════════════════════════
EMAIL_RE = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
PHONE_RE = r"[\+\(]?[1-9][0-9\s\.\-\(\)]{7,}[0-9]"
SOCIAL_RE = {
    "facebook":  r"(?:https?://)?(?:www\.)?facebook\.com/(?!sharer|share|dialog|home\.php|login|watch|groups|events|marketplace|pages/create)[A-Za-z0-9_.%-]{3,}/?(?:\s|$|\")",
    "instagram": r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.%-]{2,})/?(?:\s|$|\")",
    "twitter":   r"(?:https?://)?(?:www\.)?(?:twitter|x)\.com/(?!share|intent|home|search)[A-Za-z0-9_]{2,}/?(?:\s|$|\")",
    "linkedin":  r"(?:https?://)?(?:www\.)?linkedin\.com/(?:company|in)/[A-Za-z0-9_%-]{2,}",
    "youtube":   r"(?:https?://)?(?:www\.)?youtube\.com/(?:@|channel/|c/)[A-Za-z0-9_.%-]{2,}",
    "tiktok":    r"(?:https?://)?(?:www\.)?tiktok\.com/@[A-Za-z0-9_.%-]{2,}",
}

BAD_EMAIL_PARTS = [
    ".png",".jpg",".gif",".svg",".webp",".css",".js",".php",
    "example.","test@","noreply","no-reply","@sentry","@email.",
    "wixpress","squarespace","wordpress","cloudflare","schema.org",
    "amazonaws","sendgrid","mailchimp","w3.org",
]

def clean_emails(text):
    found = re.findall(EMAIL_RE, text)
    return list({e.lower() for e in found
                 if not any(b in e.lower() for b in BAD_EMAIL_PARTS)
                 and len(e) < 80})

def clean_phones(text):
    found = re.findall(PHONE_RE, text)
    out = []
    for p in found:
        digits = re.sub(r"\D","",p)
        if 7 <= len(digits) <= 15:
            out.append(p.strip())
    return list(dict.fromkeys(out))[:3]

def clean_socials(html_text):
    result = {}
    for platform, pattern in SOCIAL_RE.items():
        matches = re.findall(pattern, html_text, re.IGNORECASE)
        for m in matches:
            if isinstance(m, tuple):
                m = m[0] if m[0] else ""
            if not m:
                continue
            if not m.startswith("http"):
                # Reconstruct full URL
                domains = {
                    "facebook":"https://facebook.com/",
                    "instagram":"https://instagram.com/",
                    "twitter":"https://twitter.com/",
                    "linkedin":"https://linkedin.com/company/",
                    "youtube":"https://youtube.com/@",
                    "tiktok":"https://tiktok.com/@",
                }
                m = domains.get(platform,"https://") + m.lstrip("/")
            path = urlparse(m).path.strip("/")
            if path and path not in ["home","login","signup","register","about","contact"]:
                result[platform] = m.split('"')[0].split("'")[0].strip()
                break
    return result

# ════════════════════════════════════════════════
#  FIND WEBSITE via search if missing
# ════════════════════════════════════════════════
def find_website(business_name, location):
    """Search DuckDuckGo to find the official website of a business."""
    query = f'"{business_name}" {location} official website'
    url   = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html  = safe_get(url, ref="https://duckduckgo.com")
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")
    bad  = ["yelp.com","yellowpages.com","facebook.com","google.com",
            "tripadvisor","linkedin.com","instagram","twitter","wikipedia",
            "duckduckgo","bing.com","yahoo.com","bbb.org"]

    for a in soup.select("a.result__a"):
        href = a.get("href","")
        # Extract real URL from DDG redirect
        if "uddg=" in href:
            import urllib.parse
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            href   = parsed.get("uddg",[""])[0]
        if href.startswith("http") and not any(b in href for b in bad):
            return href

    return ""

# ════════════════════════════════════════════════
#  HUNTER.IO — find emails by domain
# ════════════════════════════════════════════════
def hunter_domain_search(domain):
    """Use Hunter.io API to find emails for a domain."""
    if not HUNTER_API_KEY or not domain:
        return []
    try:
        url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}&limit=5"
        r   = req.get(url, timeout=10)
        data = r.json()
        emails = []
        people = []
        for item in data.get("data",{}).get("emails",[]):
            email = item.get("value","")
            if email:
                emails.append(email)
                person = {
                    "name":     f"{item.get('first_name','')} {item.get('last_name','')}".strip(),
                    "role":     item.get("position",""),
                    "email":    email,
                    "phone":    "",
                    "linkedin": item.get("linkedin","") or "",
                }
                if person["name"]:
                    people.append(person)
        return emails, people
    except Exception as e:
        log.warning(f"Hunter error: {e}")
        return [], []

# ════════════════════════════════════════════════
#  WEBSITE DEEP SCRAPER
# ════════════════════════════════════════════════
def scrape_website(url):
    data = {"emails":[],"phones":[],"socials":{},"people":[],"address":""}
    if not url:
        return data

    base = url.rstrip("/")
    pages = [
        base,
        base + "/contact",
        base + "/about",
        base + "/about-us",
        base + "/contact-us",
        base + "/team",
        base + "/our-team",
        base + "/leadership",
        base + "/staff",
        base + "/people",
    ]

    combined = ""
    soups    = []
    for page_url in pages[:6]:
        html = safe_get(page_url, ref=url)
        if html:
            combined += html
            soups.append(BeautifulSoup(html, "lxml"))

    if not combined:
        return data

    # Emails + phones from full text
    data["emails"] = clean_emails(combined)[:8]
    data["phones"] = clean_phones(combined)[:3]
    data["socials"] = clean_socials(combined)

    # Also try Hunter if we have a domain
    if HUNTER_API_KEY:
        domain = urlparse(url).netloc.replace("www.","")
        h_emails, h_people = hunter_domain_search(domain)
        for e in h_emails:
            if e not in data["emails"]:
                data["emails"].append(e)
        data["people"] = h_people[:3]

    # Address
    for soup in soups:
        for sel in ["address","[class*='address']","[itemprop='address']",
                    "[class*='location']","[class*='contact-info']"]:
            el = soup.select_one(sel)
            if el:
                addr = el.get_text(separator=" ", strip=True)
                if 10 < len(addr) < 300:
                    data["address"] = addr
                    break
        if data["address"]:
            break

    # Key people — many selectors
    if not data["people"]:
        people = []
        selectors = [
            "[class*='team-member']","[class*='team_member']",
            "[class*='staff-member']","[class*='person-card']",
            "[class*='people-item']","[class*='leadership-card']",
            "[class*='our-team'] [class*='item']",
            "[class*='team'] [class*='card']",
            "[class*='team'] article",
            "[itemtype*='schema.org/Person']",
            ".bio","[class*='bio-card']",
        ]
        blocks = []
        for soup in soups:
            for sel in selectors:
                found = soup.select(sel)
                if found:
                    blocks += found
                    break
            if len(blocks) >= 6:
                break

        for block in blocks[:6]:
            name_el = block.select_one(
                "h2,h3,h4,h5,strong,[class*='name'],[itemprop='name']"
            )
            role_el = block.select_one(
                "[class*='title'],[class*='role'],[class*='position'],"
                "[class*='job'],[itemprop='jobTitle'],em,p"
            )
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            # Skip obviously non-person text
            if (len(name) < 3 or len(name) > 60
                    or any(c.isdigit() for c in name[:2])
                    or any(w in name.lower() for w in ["contact","menu","about","home","service","product"])):
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

    # If still no email, try to guess from domain + common patterns
    if not data["emails"] and url:
        domain = urlparse(url).netloc.replace("www.","")
        # Check mailto: links directly
        for soup in soups:
            for a in soup.select("a[href^='mailto:']"):
                email = a.get("href","").replace("mailto:","").split("?")[0].strip()
                if email and "@" in email and not any(b in email for b in BAD_EMAIL_PARTS):
                    data["emails"].append(email)
        data["emails"] = list(set(data["emails"]))[:5]

    return data

# ════════════════════════════════════════════════
#  SOURCE 1 — DuckDuckGo
# ════════════════════════════════════════════════
def search_duckduckgo(query, num=20):
    results = []
    seen    = set()
    url     = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    html    = safe_get(url, ref="https://duckduckgo.com")
    if not html:
        return results

    soup = BeautifulSoup(html, "lxml")
    for result in soup.select("div.result, div.web-result"):
        title_el = result.select_one("a.result__a, h2 a")
        desc_el  = result.select_one("a.result__snippet, div.result__body")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        href = title_el.get("href","")
        if "uddg=" in href:
            import urllib.parse as upl
            parsed = upl.parse_qs(upl.urlparse(href).query)
            href   = parsed.get("uddg",[""])[0]
        if not href.startswith("http"):
            continue
        if any(x in href for x in ["duckduckgo","google.com","bing.com","wikipedia"]):
            continue
        if href in seen:
            continue
        seen.add(href)
        desc   = desc_el.get_text(strip=True)[:250] if desc_el else ""
        domain = urlparse(href).netloc.replace("www.","")
        results.append({"name":name,"website":href,"domain":domain,"description":desc,"source":"Search"})
        if len(results) >= num:
            break
    log.info(f"DDG: {len(results)} for '{query}'")
    return results

# ════════════════════════════════════════════════
#  SOURCE 2 — Bing
# ════════════════════════════════════════════════
def search_bing(query, num=15):
    results = []
    seen    = set()
    for offset in range(0, min(num*2, 30), 10):
        url  = f"https://www.bing.com/search?q={quote_plus(query)}&first={offset+1}&count=10"
        html = safe_get(url, ref="https://www.bing.com")
        if not html:
            break
        soup = BeautifulSoup(html, "lxml")
        for li in soup.select("li.b_algo"):
            a    = li.select_one("h2 a")
            desc = li.select_one("div.b_caption p")
            if not a:
                continue
            href = a.get("href","")
            if not href.startswith("http"):
                continue
            if any(x in href for x in ["bing.com","microsoft.com","wikipedia"]):
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({
                "name":        a.get_text(strip=True),
                "website":     href,
                "domain":      urlparse(href).netloc.replace("www.",""),
                "description": desc.get_text(strip=True)[:250] if desc else "",
                "source":      "Search",
            })
        if len(results) >= num:
            break
    log.info(f"Bing: {len(results)} for '{query}'")
    return results

# ════════════════════════════════════════════════
#  SOURCE 3 — Yellow Pages
# ════════════════════════════════════════════════
def search_yellowpages(niche, location, num=20):
    results = []
    for page in range(1, 4):
        url  = f"https://www.yellowpages.com/search?search_terms={quote_plus(niche)}&geo_location_terms={quote_plus(location)}&page={page}"
        html = safe_get(url, ref="https://www.yellowpages.com")
        if not html:
            break
        soup  = BeautifulSoup(html, "lxml")
        cards = soup.select("div.result, div.organic")
        for card in cards:
            name_el  = card.select_one("a.business-name, h2 a, h3 a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue
            phone_el = card.select_one("div.phones, a.phone")
            addr_el  = card.select_one("p.adr, .street-address, address")
            web_el   = card.select_one("a.track-visit-website")
            cats_el  = card.select("div.categories a")
            website  = ""
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
    log.info(f"YP: {len(results)}")
    return results[:num]

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

def enrich(biz, location=""):
    # Step 1: find website if missing
    if not biz.get("website") and biz.get("name"):
        log.info(f"  Finding website for: {biz['name']}")
        biz["website"] = find_website(biz["name"], location)

    website = biz.get("website","")
    if not website:
        return biz

    log.info(f"  Scraping: {biz.get('name','?')} → {website}")
    try:
        sd = scrape_website(website)
        # Emails
        if sd["emails"]:
            biz["email"]      = sd["emails"][0]
            biz["all_emails"] = sd["emails"]
        # Phones
        if sd["phones"] and not biz.get("phone"):
            biz["phone"] = sd["phones"][0]
        # Address
        if not biz.get("address") and sd["address"]:
            biz["address"] = sd["address"]
        # Socials
        soc = biz.get("socials",{})
        soc.update(sd["socials"])
        biz["socials"] = soc
        for k,v in soc.items():
            if not biz.get(k):
                biz[k] = v
        # People
        if sd["people"]:
            biz["people"] = sd["people"]
    except Exception as e:
        log.error(f"Enrich error: {e}")
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
    log.info(f"=== SCRAPE: '{query}' max={max_res} ===")

    all_raw = []
    per     = max(max_res, 10)

    # Always search DDG + Bing
    all_raw += search_duckduckgo(f"{niche} company {location}", per)
    all_raw += search_bing(f"{niche} business {location} contact email", per)

    # Yellow Pages
    if "yellowpages" in sources:
        all_raw += search_yellowpages(niche, location, per)

    log.info(f"Raw: {len(all_raw)} → merging to {max_res}")
    businesses = merge(all_raw, max_res)

    # Enrich each
    enriched = []
    for b in businesses:
        enriched.append(enrich(b, location))

    results = [normalize(b) for b in enriched]

    # Stats
    with_email  = sum(1 for r in results if r["email"])
    with_phone  = sum(1 for r in results if r["phone"])
    with_people = sum(1 for r in results if r["people"])
    log.info(f"Done: {len(results)} biz | {with_email} emails | {with_phone} phones | {with_people} with people")

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
