import os
import re
import time
import json
import random
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup

app = Flask(__name__)

# ── CORS: allow all origins (required for Google Sites embed) ──────────────────
CORS(app, origins="*", methods=["GET", "POST", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"])

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ── Optional API keys (leave blank if not using) ──────────────────────────────
HUNTER_API_KEY = ""   # https://hunter.io  — 25 free/month
SERP_API_KEY   = ""   # https://serpapi.com — 100 free/month
YT_API_KEY     = ""   # YouTube Data API v3

# ── Config ────────────────────────────────────────────────────────────────────
SELENIUM_OK    = False   # Keep False on Railway (no Chrome)
REQUEST_DELAY  = 1.5
MAX_WEBSITE_DEPTH = 3    # pages to scrape per business website

HEADERS_LIST = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"},
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"},
]

def get_headers():
    return random.choice(HEADERS_LIST)

def safe_get(url, timeout=10):
    try:
        time.sleep(random.uniform(0.8, REQUEST_DELAY))
        r = requests.get(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
        if r.status_code == 200:
            return r
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH SOURCES
# ─────────────────────────────────────────────────────────────────────────────

def search_duckduckgo(query, max_results=20):
    """Scrape DuckDuckGo HTML results — no bot detection."""
    urls = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        r = safe_get(url)
        if not r:
            return urls
        soup = BeautifulSoup(r.text, "lxml")
        for a in soup.select("a.result__url"):
            href = a.get("href", "")
            if href.startswith("http") and "duckduckgo" not in href:
                urls.append(href)
            if len(urls) >= max_results:
                break
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real = parsed.get("uddg", [""])[0]
                if real.startswith("http") and real not in urls:
                    urls.append(real)
            if len(urls) >= max_results:
                break
    except Exception as e:
        print(f"DuckDuckGo error: {e}")
    return urls

def search_bing(query, max_results=20):
    """Scrape Bing search results."""
    urls = []
    try:
        url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&count={max_results}"
        r = safe_get(url)
        if not r:
            return urls
        soup = BeautifulSoup(r.text, "lxml")
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if a and a.get("href", "").startswith("http"):
                href = a["href"]
                if "bing.com" not in href and href not in urls:
                    urls.append(href)
            if len(urls) >= max_results:
                break
    except Exception as e:
        print(f"Bing error: {e}")
    return urls

def search_yellowpages(niche, location, max_results=15):
    """Scrape Yellow Pages for structured business data."""
    results = []
    try:
        query = requests.utils.quote(niche)
        loc   = requests.utils.quote(location)
        url   = f"https://www.yellowpages.com/search?search_terms={query}&geo_location_terms={loc}"
        r = safe_get(url)
        if not r:
            return results
        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.select("div.result")[:max_results]:
            name_el  = card.select_one("a.business-name span")
            phone_el = card.select_one("div.phones.phone.primary")
            addr_el  = card.select_one("p.adr")
            web_el   = card.select_one("a.track-visit-website")
            cat_el   = card.select_one("div.categories a")
            if not name_el:
                continue
            results.append({
                "name":        name_el.get_text(strip=True),
                "phone":       phone_el.get_text(strip=True) if phone_el else "",
                "address":     addr_el.get_text(separator=" ", strip=True) if addr_el else "",
                "website":     web_el["href"] if web_el and web_el.get("href") else "",
                "category":    cat_el.get_text(strip=True) if cat_el else niche,
                "email":       "",
                "facebook":    "",
                "instagram":   "",
                "twitter":     "",
                "linkedin":    "",
                "description": "",
                "rating":      "",
                "people":      [],
                "source":      "Yellow Pages",
            })
    except Exception as e:
        print(f"Yellow Pages error: {e}")
    return results

def search_yelp(niche, location, max_results=15):
    """Scrape Yelp for structured business data."""
    results = []
    try:
        query = requests.utils.quote(niche)
        loc   = requests.utils.quote(location)
        url   = f"https://www.yelp.com/search?find_desc={query}&find_loc={loc}"
        r = safe_get(url)
        if not r:
            return results
        soup = BeautifulSoup(r.text, "lxml")
        for card in soup.select("div[data-testid='serp-ia-card']")[:max_results]:
            name_el   = card.select_one("a span")
            rating_el = card.select_one("div[aria-label*='rating']")
            addr_el   = card.select_one("p")
            if not name_el:
                continue
            results.append({
                "name":        name_el.get_text(strip=True),
                "phone":       "",
                "address":     addr_el.get_text(strip=True) if addr_el else "",
                "website":     "",
                "category":    niche,
                "email":       "",
                "facebook":    "",
                "instagram":   "",
                "twitter":     "",
                "linkedin":    "",
                "description": "",
                "rating":      rating_el["aria-label"] if rating_el else "",
                "people":      [],
                "source":      "Yelp",
            })
    except Exception as e:
        print(f"Yelp error: {e}")
    return results

# ─────────────────────────────────────────────────────────────────────────────
# DEEP WEBSITE SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(
    r"(\+?[\d\s\-().]{7,})"
    r"(?=\s*(?:ext|x|#)?\s*\d{0,5}\s*$|\s*[^\d])"
)
PHONE_STRICT = re.compile(r"(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")

SOCIAL_PATTERNS = {
    "facebook":  re.compile(r"https?://(www\.)?facebook\.com/[^\s\"'<>]+"),
    "instagram": re.compile(r"https?://(www\.)?instagram\.com/[^\s\"'<>]+"),
    "twitter":   re.compile(r"https?://(www\.)?(twitter|x)\.com/[^\s\"'<>]+"),
    "linkedin":  re.compile(r"https?://(www\.)?linkedin\.com/(company|in)/[^\s\"'<>]+"),
    "tiktok":    re.compile(r"https?://(www\.)?tiktok\.com/@[^\s\"'<>]+"),
    "youtube":   re.compile(r"https?://(www\.)?youtube\.com/(channel|c|@)[^\s\"'<>]+"),
}

PEOPLE_SELECTORS = [
    "[class*='team-member']", "[class*='person-card']", "[class*='staff-member']",
    "[class*='leadership']",  "[class*='our-team']",    "[class*='meet-the-team']",
    "[class*='bio']",         "[class*='founder']",     "[class*='executive']",
]

CONTACT_PATHS = ["/contact", "/contact-us", "/about", "/about-us",
                 "/team", "/staff", "/leadership", "/people", "/get-in-touch"]

def extract_emails(text):
    found = EMAIL_RE.findall(text)
    clean = []
    for e in found:
        e = e.strip(".,;:\"'")
        if "." in e.split("@")[-1] and e not in clean:
            skip = any(x in e.lower() for x in ["example", "domain", "youremail",
                                                  "email@", "test@", "info@example"])
            if not skip:
                clean.append(e)
    return clean

def extract_phones(text):
    found = PHONE_STRICT.findall(text)
    clean = []
    for match in found:
        p = "".join(match).strip()
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15 and p not in clean:
            clean.append(p)
    return clean

def extract_socials(html_text):
    socials = {}
    for platform, pattern in SOCIAL_PATTERNS.items():
        matches = pattern.findall(html_text)
        if matches:
            full = pattern.search(html_text)
            if full:
                url = full.group(0).rstrip("\"'/>")
                if platform not in socials:
                    socials[platform] = url
    return socials

def extract_people(soup):
    people = []
    for selector in PEOPLE_SELECTORS:
        cards = soup.select(selector)
        for card in cards[:10]:
            name_el  = card.select_one("h2, h3, h4, strong, [class*='name']")
            role_el  = card.select_one("p, span, [class*='title'], [class*='role'], [class*='position']")
            email_el = card.select_one("a[href^='mailto:']")
            link_el  = card.select_one("a[href*='linkedin']")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if len(name) < 3 or len(name) > 60:
                continue
            person = {
                "name":    name,
                "role":    role_el.get_text(strip=True) if role_el else "",
                "email":   email_el["href"].replace("mailto:", "") if email_el else "",
                "linkedin": link_el["href"] if link_el else "",
                "phone":   "",
            }
            if person not in people:
                people.append(person)
    return people[:8]

def scrape_website(url, depth=MAX_WEBSITE_DEPTH):
    """Deep scrape a business website for contact info, socials, key people."""
    if not url or not url.startswith("http"):
        return {}

    result = {
        "emails": [], "phones": [], "people": [],
        "facebook": "", "instagram": "", "twitter": "",
        "linkedin": "", "tiktok": "", "youtube": "",
        "description": "",
    }

    base = url.rstrip("/")
    visited = set()
    pages_to_visit = [base]

    # Add common contact pages
    for path in CONTACT_PATHS:
        pages_to_visit.append(base + path)

    scraped = 0
    for page_url in pages_to_visit:
        if scraped >= depth or page_url in visited:
            continue
        visited.add(page_url)

        r = safe_get(page_url)
        if not r:
            continue
        scraped += 1

        html = r.text
        soup = BeautifulSoup(html, "lxml")

        # Remove script/style noise
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ")

        # Emails
        for e in extract_emails(text):
            if e not in result["emails"]:
                result["emails"].append(e)

        # Phones
        for p in extract_phones(text):
            if p not in result["phones"]:
                result["phones"].append(p)

        # Socials
        socials = extract_socials(html)
        for platform, link in socials.items():
            if not result.get(platform):
                result[platform] = link

        # mailto: links (most reliable email source)
        for a in soup.select("a[href^='mailto:']"):
            email = a["href"].replace("mailto:", "").split("?")[0].strip()
            if email and email not in result["emails"]:
                result["emails"].append(email)

        # tel: links
        for a in soup.select("a[href^='tel:']"):
            phone = a["href"].replace("tel:", "").strip()
            if phone and phone not in result["phones"]:
                result["phones"].append(phone)

        # Key people
        if not result["people"]:
            result["people"] = extract_people(soup)

        # Description from meta
        if not result["description"]:
            meta = soup.select_one("meta[name='description'], meta[property='og:description']")
            if meta and meta.get("content"):
                result["description"] = meta["content"][:300]

    # Hunter.io fallback for emails
    if not result["emails"] and HUNTER_API_KEY:
        try:
            domain = re.sub(r"https?://(www\.)?", "", base).split("/")[0]
            hunter_url = f"https://api.hunter.io/v2/domain-search?domain={domain}&api_key={HUNTER_API_KEY}&limit=5"
            hr = requests.get(hunter_url, timeout=8)
            data = hr.json()
            for em in data.get("data", {}).get("emails", []):
                val = em.get("value", "")
                if val and val not in result["emails"]:
                    result["emails"].append(val)
                    # Try to get person info
                    fname = em.get("first_name", "")
                    lname = em.get("last_name", "")
                    pos   = em.get("position", "")
                    if fname or lname:
                        result["people"].append({
                            "name":    f"{fname} {lname}".strip(),
                            "role":    pos,
                            "email":   val,
                            "phone":   "",
                            "linkedin": "",
                        })
        except Exception:
            pass

    return result

# ─────────────────────────────────────────────────────────────────────────────
# BUILD RESULT FROM URL (general web search hits)
# ─────────────────────────────────────────────────────────────────────────────

def build_result_from_url(url, niche, location):
    """Visit a URL, extract business name + all contact info."""
    r = safe_get(url)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "lxml")

    # Name from title or og:title
    name = ""
    og_title = soup.select_one("meta[property='og:title']")
    if og_title and og_title.get("content"):
        name = og_title["content"].strip()
    if not name and soup.title:
        name = soup.title.string.strip() if soup.title.string else ""
    if not name:
        h1 = soup.select_one("h1")
        name = h1.get_text(strip=True) if h1 else ""

    # Clean common suffixes from title
    for suffix in [" | Home", " – Home", " - Home", " | Official", " | Welcome"]:
        name = name.replace(suffix, "")
    name = name[:80]

    if not name:
        return None

    # Deep scrape the site
    site_data = scrape_website(url)

    return {
        "name":        name,
        "website":     url,
        "address":     location,
        "phone":       site_data["phones"][0] if site_data["phones"] else "",
        "email":       site_data["emails"][0] if site_data["emails"] else "",
        "facebook":    site_data.get("facebook", ""),
        "instagram":   site_data.get("instagram", ""),
        "twitter":     site_data.get("twitter", ""),
        "linkedin":    site_data.get("linkedin", ""),
        "tiktok":      site_data.get("tiktok", ""),
        "youtube":     site_data.get("youtube", ""),
        "description": site_data.get("description", ""),
        "rating":      "",
        "category":    niche,
        "people":      site_data.get("people", []),
        "source":      "Web",
    }

# ─────────────────────────────────────────────────────────────────────────────
# DEDUPLICATE
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(results):
    seen_names = set()
    seen_urls  = set()
    clean = []
    for r in results:
        name_key = r.get("name", "").lower().strip()[:40]
        url_key  = r.get("website", "").lower().strip().rstrip("/")
        if name_key in seen_names:
            continue
        if url_key and url_key in seen_urls:
            continue
        if name_key:
            seen_names.add(name_key)
        if url_key:
            seen_urls.add(url_key)
        clean.append(r)
    return clean

# ─────────────────────────────────────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Business scraper is running"})

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "endpoints": ["/health", "/scrape", "/export-csv"]})

@app.route("/scrape", methods=["POST", "OPTIONS"])
def scrape():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(force=True, silent=True) or {}

    niche       = data.get("niche", "").strip()
    location    = data.get("location", "").strip()
    max_results = int(data.get("max_results", 20))
    sources     = data.get("sources", ["duckduckgo", "bing", "yellowpages", "yelp"])

    if not niche or not location:
        return jsonify({"error": "niche and location are required"}), 400

    query = f"{niche} {location}"
    all_results = []

    print(f"[SCRAPE] query='{query}' max={max_results} sources={sources}")

    # ── Yellow Pages (structured, fast) ───────────────────────────────────────
    if "yellowpages" in sources:
        yp = search_yellowpages(niche, location, max_results)
        print(f"  Yellow Pages: {len(yp)} results")
        for biz in yp:
            if biz.get("website"):
                site_data = scrape_website(biz["website"])
                if not biz["email"]:
                    biz["email"] = site_data["emails"][0] if site_data["emails"] else ""
                if not biz["phone"]:
                    biz["phone"] = site_data["phones"][0] if site_data["phones"] else ""
                for plat in ["facebook", "instagram", "twitter", "linkedin", "tiktok"]:
                    if not biz[plat]:
                        biz[plat] = site_data.get(plat, "")
                if not biz["description"]:
                    biz["description"] = site_data.get("description", "")
                if not biz["people"]:
                    biz["people"] = site_data.get("people", [])
        all_results.extend(yp)

    # ── Yelp (structured, ratings) ────────────────────────────────────────────
    if "yelp" in sources:
        yl = search_yelp(niche, location, max_results)
        print(f"  Yelp: {len(yl)} results")
        all_results.extend(yl)

    # ── DuckDuckGo (web search → visit each site) ────────────────────────────
    if "duckduckgo" in sources and len(all_results) < max_results:
        ddg_urls = search_duckduckgo(f"{query} official website", max_results)
        print(f"  DuckDuckGo: {len(ddg_urls)} URLs")
        for url in ddg_urls:
            if len(all_results) >= max_results * 2:
                break
            skip = any(x in url for x in ["google.", "bing.", "facebook.", "instagram.",
                                            "twitter.", "youtube.", "wikipedia.",
                                            "yelp.com", "yellowpages.com"])
            if skip:
                continue
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    # ── Bing (web search → visit each site) ──────────────────────────────────
    if "bing" in sources and len(all_results) < max_results:
        bing_urls = search_bing(f"{query} contact email", max_results)
        print(f"  Bing: {len(bing_urls)} URLs")
        for url in bing_urls:
            if len(all_results) >= max_results * 2:
                break
            skip = any(x in url for x in ["google.", "bing.", "facebook.", "instagram.",
                                            "twitter.", "youtube.", "wikipedia.",
                                            "yelp.com", "yellowpages.com"])
            if skip:
                continue
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    # ── Deduplicate and trim ──────────────────────────────────────────────────
    all_results = deduplicate(all_results)[:max_results]

    print(f"[SCRAPE] Done — {len(all_results)} unique results")

    return jsonify({
        "query":   query,
        "count":   len(all_results),
        "results": all_results,
    })

@app.route("/export-csv", methods=["POST", "OPTIONS"])
def export_csv():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data    = request.get_json(force=True, silent=True) or {}
    results = data.get("results", [])

    if not results:
        return jsonify({"error": "No results provided"}), 400

    cols = ["name", "address", "phone", "email", "website",
            "facebook", "instagram", "twitter", "linkedin",
            "tiktok", "youtube", "rating", "description", "source"]

    lines = [",".join(cols)]
    for r in results:
        row = []
        for col in cols:
            val = str(r.get(col, "")).replace('"', '""').replace("\n", " ")
            row.append(f'"{val}"')
        lines.append(",".join(row))

    csv_text = "\n".join(lines)

    from flask import Response
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=businesses.csv"}
    )

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
