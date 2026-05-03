import os
import re
import time
import json
import random
import requests
from urllib.parse import quote, urlparse, parse_qs
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from bs4 import BeautifulSoup

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# CORS — Bulletproof for Google Sites embed
# ═══════════════════════════════════════════════════════════════════════════════
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"]
    }
})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Accept"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
REQUEST_DELAY = 1.0
MAX_RESULTS = 50
TIMEOUT = 15

# Free API Keys (optional but recommended for bulletproof results)
SERP_API_KEY = os.environ.get("SERP_API_KEY", "")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_CX = os.environ.get("GOOGLE_CX", "")

HEADERS_LIST = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.5", "Accept-Encoding": "gzip, deflate", "Connection": "keep-alive"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.5"},
    {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
]

def get_headers():
    return random.choice(HEADERS_LIST)

def safe_get(url, timeout=TIMEOUT, retries=2):
    """Robust GET with retries and delay."""
    for attempt in range(retries + 1):
        try:
            time.sleep(random.uniform(0.5, REQUEST_DELAY))
            r = requests.get(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                return r
            if r.status_code in [429, 503, 502, 500]:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            print(f"safe_get failed for {url}: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# BUILT-IN MOCK DATA — Bulletproof fallback when ALL scraping fails
# ═══════════════════════════════════════════════════════════════════════════════
MOCK_DATABASE = {
    "real estate": [
        {"name": "Keller Williams NYC", "phone": "(212) 555-0100", "email": "nyc@kw.com", "website": "https://kw.com/nyc", "address": "100 Park Ave, New York, NY", "rating": "4.8", "people": [{"name": "Sarah Johnson", "role": "Broker", "email": "sarah@kw.com"}]},
        {"name": "Douglas Elliman", "phone": "(212) 555-0200", "email": "info@elliman.com", "website": "https://elliman.com", "address": "575 Madison Ave, New York, NY", "rating": "4.7", "people": [{"name": "Michael Ross", "role": "CEO", "email": "mross@elliman.com"}]},
        {"name": "Corcoran Group", "phone": "(212) 555-0300", "email": "hello@corcoran.com", "website": "https://corcoran.com", "address": "660 Madison Ave, New York, NY", "rating": "4.6", "people": [{"name": "Pamela Liebman", "role": "President", "email": "pliebman@corcoran.com"}]},
        {"name": "Compass Real Estate", "phone": "(212) 555-0400", "email": "nyc@compass.com", "website": "https://compass.com", "address": "90 5th Ave, New York, NY", "rating": "4.9", "people": [{"name": "Ori Allon", "role": "Founder", "email": "ori@compass.com"}]},
        {"name": "Sotheby's International", "phone": "(212) 555-0500", "email": "ny@sothebysrealty.com", "website": "https://sothebysrealty.com", "address": "980 Madison Ave, New York, NY", "rating": "4.8", "people": [{"name": "David Koch", "role": "Director", "email": "dkoch@sothebys.com"}]},
        {"name": "Brown Harris Stevens", "phone": "(212) 555-0600", "email": "info@bhsusa.com", "website": "https://bhsusa.com", "address": "445 Park Ave, New York, NY", "rating": "4.5", "people": [{"name": "Bess Freedman", "role": "CEO", "email": "bfreedman@bhsusa.com"}]},
        {"name": "Halstead Real Estate", "phone": "(212) 555-0700", "email": "info@halstead.com", "website": "https://halstead.com", "address": "499 Park Ave, New York, NY", "rating": "4.4", "people": [{"name": "Diane Ramirez", "role": "Chairman", "email": "dramirez@halstead.com"}]},
        {"name": "Stribling & Associates", "phone": "(212) 555-0800", "email": "info@stribling.com", "website": "https://stribling.com", "address": "924 Broadway, New York, NY", "rating": "4.3", "people": [{"name": "Elizabeth Stribling", "role": "Founder", "email": "estribling@stribling.com"}]},
        {"name": "Warburg Realty", "phone": "(212) 555-0900", "email": "info@warburgrealty.com", "website": "https://warburgrealty.com", "address": "30 E 76th St, New York, NY", "rating": "4.6", "people": [{"name": "Frederick Peters", "role": "CEO", "email": "fpeters@warburg.com"}]},
        {"name": "Elegran Real Estate", "phone": "(212) 555-1000", "email": "info@elegran.com", "website": "https://elegran.com", "address": "787 7th Ave, New York, NY", "rating": "4.7", "people": [{"name": "Michael Ross", "role": "Managing Director", "email": "mross@elegran.com"}]},
    ],
    "restaurant": [
        {"name": "Le Bernardin", "phone": "(212) 555-2000", "email": "info@le-bernardin.com", "website": "https://le-bernardin.com", "address": "155 W 51st St, New York, NY", "rating": "4.9", "people": [{"name": "Eric Ripert", "role": "Chef", "email": "eric@le-bernardin.com"}]},
        {"name": "Eleven Madison Park", "phone": "(212) 555-2100", "email": "reservations@elevenmadisonpark.com", "website": "https://elevenmadisonpark.com", "address": "11 Madison Ave, New York, NY", "rating": "4.8", "people": [{"name": "Daniel Humm", "role": "Chef", "email": "daniel@emp.com"}]},
        {"name": "Per Se", "phone": "(212) 555-2200", "email": "info@perseny.com", "website": "https://perseny.com", "address": "10 Columbus Cir, New York, NY", "rating": "4.7", "people": [{"name": "Thomas Keller", "role": "Chef", "email": "tkeller@perseny.com"}]},
        {"name": "Peter Luger", "phone": "(718) 555-2300", "email": "info@peterluger.com", "website": "https://peterluger.com", "address": "178 Broadway, Brooklyn, NY", "rating": "4.6", "people": [{"name": "David Berson", "role": "Manager", "email": "dberson@peterluger.com"}]},
        {"name": "Katz's Delicatessen", "phone": "(212) 555-2400", "email": "info@katzdeli.com", "website": "https://katzdeli.com", "address": "205 E Houston St, New York, NY", "rating": "4.5", "people": [{"name": "Jake Dell", "role": "Owner", "email": "jake@katzdeli.com"}]},
        {"name": "Joe's Pizza", "phone": "(212) 555-2500", "email": "info@joespizza.com", "website": "https://joespizza.com", "address": "7 Carmine St, New York, NY", "rating": "4.8", "people": [{"name": "Joe Pozzuoli", "role": "Owner", "email": "joe@joespizza.com"}]},
        {"name": "Shake Shack", "phone": "(646) 555-2600", "email": "info@shakeshack.com", "website": "https://shakeshack.com", "address": "Madison Square Park, New York, NY", "rating": "4.4", "people": [{"name": "Randy Garutti", "role": "CEO", "email": "randy@shakeshack.com"}]},
        {"name": "Momofuku Noodle Bar", "phone": "(212) 555-2700", "email": "info@momofuku.com", "website": "https://momofuku.com", "address": "171 1st Ave, New York, NY", "rating": "4.5", "people": [{"name": "David Chang", "role": "Founder", "email": "david@momofuku.com"}]},
        {"name": "The Halal Guys", "phone": "(212) 555-2800", "email": "info@thehalalguys.com", "website": "https://thehalalguys.com", "address": "W 53rd St & 6th Ave, New York, NY", "rating": "4.3", "people": [{"name": "Ahmed Abdelbasit", "role": "Founder", "email": "ahmed@thehalalguys.com"}]},
        {"name": "Carbone", "phone": "(212) 555-2900", "email": "info@carbonenewyork.com", "website": "https://carbonenewyork.com", "address": "181 Thompson St, New York, NY", "rating": "4.7", "people": [{"name": "Mario Carbone", "role": "Chef", "email": "mario@carbonenewyork.com"}]},
    ],
    "digital marketing": [
        {"name": "Wunderman Thompson", "phone": "(212) 555-3000", "email": "info@wundermanthompson.com", "website": "https://wundermanthompson.com", "address": "200 Park Ave, New York, NY", "rating": "4.6", "people": [{"name": "Mel Edwards", "role": "CEO", "email": "mel@wunderman.com"}]},
        {"name": "Ogilvy New York", "phone": "(212) 555-3100", "email": "info@ogilvy.com", "website": "https://ogilvy.com", "address": "636 11th Ave, New York, NY", "rating": "4.7", "people": [{"name": "Andy Main", "role": "CEO", "email": "andy@ogilvy.com"}]},
        {"name": "BBDO New York", "phone": "(212) 555-3200", "email": "info@bbdo.com", "website": "https://bbdo.com", "address": "1285 6th Ave, New York, NY", "rating": "4.5", "people": [{"name": "David Lubars", "role": "CCO", "email": "david@bbdo.com"}]},
        {"name": "Droga5", "phone": "(212) 555-3300", "email": "info@droga5.com", "website": "https://droga5.com", "address": "120 Wall St, New York, NY", "rating": "4.8", "people": [{"name": "David Droga", "role": "Founder", "email": "david@droga5.com"}]},
        {"name": "R/GA", "phone": "(212) 555-3400", "email": "info@rga.com", "website": "https://rga.com", "address": "450 W 33rd St, New York, NY", "rating": "4.6", "people": [{"name": "Sean Lyons", "role": "CEO", "email": "sean@rga.com"}]},
        {"name": "Huge Inc", "phone": "(212) 555-3500", "email": "info@hugeinc.com", "website": "https://hugeinc.com", "address": "45 Main St, Brooklyn, NY", "rating": "4.4", "people": [{"name": "Lisa Main", "role": "CEO", "email": "lisa@hugeinc.com"}]},
        {"name": "360i", "phone": "(212) 555-3600", "email": "info@360i.com", "website": "https://360i.com", "address": "32 6th Ave, New York, NY", "rating": "4.5", "people": [{"name": "Jared Belsky", "role": "CEO", "email": "jared@360i.com"}]},
        {"name": "MRY", "phone": "(212) 555-3700", "email": "info@mry.com", "website": "https://mry.com", "address": "601 W 26th St, New York, NY", "rating": "4.3", "people": [{"name": "Matt Britton", "role": "CEO", "email": "matt@mry.com"}]},
        {"name": "Deutsch NY", "phone": "(212) 555-3800", "email": "info@deutsch.com", "website": "https://deutsch.com", "address": "111 8th Ave, New York, NY", "rating": "4.4", "people": [{"name": "Val DiFebo", "role": "CEO", "email": "val@deutsch.com"}]},
        {"name": "Saatchi & Saatchi", "phone": "(212) 555-3900", "email": "info@saatchi.com", "website": "https://saatchi.com", "address": "375 Hudson St, New York, NY", "rating": "4.5", "people": [{"name": "Andrea Diquez", "role": "CEO", "email": "andrea@saatchi.com"}]},
    ],
    "law firm": [
        {"name": "Skadden Arps", "phone": "(212) 555-4000", "email": "info@skadden.com", "website": "https://skadden.com", "address": "4 Times Square, New York, NY", "rating": "4.8", "people": [{"name": "Eric Friedman", "role": "Partner", "email": "eric@skadden.com"}]},
        {"name": "Sullivan & Cromwell", "phone": "(212) 555-4100", "email": "info@sullcrom.com", "website": "https://sullcrom.com", "address": "125 Broad St, New York, NY", "rating": "4.7", "people": [{"name": "Joseph Shenker", "role": "Chairman", "email": "joe@sullcrom.com"}]},
        {"name": "Cravath Swaine", "phone": "(212) 555-4200", "email": "info@cravath.com", "website": "https://cravath.com", "address": "825 8th Ave, New York, NY", "rating": "4.9", "people": [{"name": "Faiza Saeed", "role": "Presiding Partner", "email": "faiza@cravath.com"}]},
        {"name": "Wachtell Lipton", "phone": "(212) 555-4300", "email": "info@wlrk.com", "website": "https://wlrk.com", "address": "51 W 52nd St, New York, NY", "rating": "4.8", "people": [{"name": "Daniel Neff", "role": "Partner", "email": "dan@wlrk.com"}]},
        {"name": "Davis Polk", "phone": "(212) 555-4400", "email": "info@davispolk.com", "website": "https://davispolk.com", "address": "450 Lexington Ave, New York, NY", "rating": "4.7", "people": [{"name": "John Bellinger", "role": "Partner", "email": "john@davispolk.com"}]},
        {"name": "Simpson Thacher", "phone": "(212) 555-4500", "email": "info@stblaw.com", "website": "https://stblaw.com", "address": "425 Lexington Ave, New York, NY", "rating": "4.6", "people": [{"name": "Bill Dougherty", "role": "Partner", "email": "bill@stblaw.com"}]},
        {"name": "Paul Weiss", "phone": "(212) 555-4600", "email": "info@paulweiss.com", "website": "https://paulweiss.com", "address": "1285 6th Ave, New York, NY", "rating": "4.7", "people": [{"name": "Brad Karp", "role": "Chairman", "email": "brad@paulweiss.com"}]},
        {"name": "Cleary Gottlieb", "phone": "(212) 555-4700", "email": "info@cgsh.com", "website": "https://cgsh.com", "address": "One Liberty Plaza, New York, NY", "rating": "4.5", "people": [{"name": "Michael Gerstenzang", "role": "Managing Partner", "email": "mike@cgsh.com"}]},
        {"name": "Kirkland & Ellis", "phone": "(212) 555-4800", "email": "info@kirkland.com", "website": "https://kirkland.com", "address": "601 Lexington Ave, New York, NY", "rating": "4.8", "people": [{"name": "Jon Ballis", "role": "Partner", "email": "jon@kirkland.com"}]},
        {"name": "Latham & Watkins", "phone": "(212) 555-4900", "email": "info@lw.com", "website": "https://lw.com", "address": "1271 6th Ave, New York, NY", "rating": "4.6", "people": [{"name": "Richard Trobman", "role": "Partner", "email": "rich@lw.com"}]},
    ],
    "plumber": [
        {"name": "Roto-Rooter NYC", "phone": "(212) 555-5000", "email": "nyc@rotorooter.com", "website": "https://rotorooter.com", "address": "520 8th Ave, New York, NY", "rating": "4.5", "people": [{"name": "Mike Johnson", "role": "Manager", "email": "mike@rotorooter.com"}]},
        {"name": "Mr. Rooter NYC", "phone": "(212) 555-5100", "email": "nyc@mrrooter.com", "website": "https://mrrooter.com", "address": "Various Locations, New York, NY", "rating": "4.4", "people": [{"name": "Tom Smith", "role": "Owner", "email": "tom@mrrooter.com"}]},
        {"name": "NYC Plumbing", "phone": "(212) 555-5200", "email": "info@nycplumbing.com", "website": "https://nycplumbing.com", "address": "123 Main St, New York, NY", "rating": "4.6", "people": [{"name": "David Lee", "role": "Master Plumber", "email": "david@nycplumbing.com"}]},
        {"name": "Petri Plumbing", "phone": "(718) 555-5300", "email": "info@petriplumbing.com", "website": "https://petriplumbing.com", "address": "901 Bay Ridge Ave, Brooklyn, NY", "rating": "4.7", "people": [{"name": "Mark Petri", "role": "Owner", "email": "mark@petriplumbing.com"}]},
        {"name": "Balkan Plumbing", "phone": "(718) 555-5400", "email": "info@balkanplumbing.com", "website": "https://balkanplumbing.com", "address": "Bushwick, Brooklyn, NY", "rating": "4.8", "people": [{"name": "David Balkan", "role": "CEO", "email": "david@balkanplumbing.com"}]},
        {"name": "Astro Plumbing", "phone": "(212) 555-5500", "email": "info@astroplumbing.com", "website": "https://astroplumbing.com", "address": "Upper East Side, New York, NY", "rating": "4.3", "people": [{"name": "Sam Astro", "role": "Owner", "email": "sam@astroplumbing.com"}]},
        {"name": "Queen's Plumbing", "phone": "(718) 555-5600", "email": "info@queensplumbing.com", "website": "https://queensplumbing.com", "address": "Queens Blvd, Queens, NY", "rating": "4.5", "people": [{"name": "Joe Queen", "role": "Manager", "email": "joe@queensplumbing.com"}]},
        {"name": "Manhattan Sewer", "phone": "(212) 555-5700", "email": "info@manhattansewer.com", "website": "https://manhattansewer.com", "address": "Manhattan, New York, NY", "rating": "4.4", "people": [{"name": "Alex Man", "role": "Owner", "email": "alex@manhattansewer.com"}]},
        {"name": "Bronx Plumbing", "phone": "(718) 555-5800", "email": "info@bronxplumbing.com", "website": "https://bronxplumbing.com", "address": "Grand Concourse, Bronx, NY", "rating": "4.2", "people": [{"name": "Carlos Bronx", "role": "Master Plumber", "email": "carlos@bronxplumbing.com"}]},
        {"name": "Emergency Plumbing NYC", "phone": "(212) 555-5900", "email": "emergency@nycplumbing.com", "website": "https://emergencyplumbingnyc.com", "address": "24/7 Service, New York, NY", "rating": "4.6", "people": [{"name": "Steve Emergency", "role": "Dispatcher", "email": "steve@emergencyplumbingnyc.com"}]},
    ],
}

def get_mock_results(niche, location, max_results=10):
    """Return mock data that matches the niche/location."""
    niche_lower = niche.lower().strip()

    # Try exact match first
    if niche_lower in MOCK_DATABASE:
        results = MOCK_DATABASE[niche_lower]
    else:
        # Try partial match
        results = []
        for key, data in MOCK_DATABASE.items():
            if key in niche_lower or niche_lower in key:
                results.extend(data)
        if not results:
            # Default to real estate if no match
            results = MOCK_DATABASE["real estate"]

    # Add location to each result
    for r in results:
        r["address"] = location
        r["source"] = "Mock Database (Demo Mode)"
        r["facebook"] = ""
        r["instagram"] = ""
        r["twitter"] = ""
        r["linkedin"] = ""
        r["tiktok"] = ""
        r["youtube"] = ""

    return results[:max_results]

# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPING FUNCTIONS (with fallbacks)
# ═══════════════════════════════════════════════════════════════════════════════

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(\+?1?\s?)?(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"https?://(www\.)?facebook\.com/[^\s"'<>]+"),
    "instagram": re.compile(r"https?://(www\.)?instagram\.com/[^\s"'<>]+"),
    "twitter": re.compile(r"https?://(www\.)?(twitter|x)\.com/[^\s"'<>]+"),
    "linkedin": re.compile(r"https?://(www\.)?linkedin\.com/(company|in)/[^\s"'<>]+"),
    "tiktok": re.compile(r"https?://(www\.)?tiktok\.com/@[^\s"'<>]+"),
    "youtube": re.compile(r"https?://(www\.)?youtube\.com/(channel|c|@)[^\s"'<>]+"),
}

def search_duckduckgo(query, max_results=15):
    """Scrape DuckDuckGo HTML — works better from cloud than Google."""
    urls = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
        r = safe_get(url, timeout=12)
        if not r:
            return urls
        soup = BeautifulSoup(r.text, "html.parser")

        # Multiple selector strategies
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                parsed = urlparse(href)
                qs = parse_qs(parsed.query)
                real = qs.get("uddg", [""])[0]
                if real.startswith("http") and real not in urls:
                    urls.append(real)
            elif href.startswith("http") and "duckduckgo" not in href and href not in urls:
                urls.append(href)
            if len(urls) >= max_results:
                break

        # Fallback selectors
        if not urls:
            for a in soup.select("a[href*='/l/?uddg=']"):
                href = a.get("href", "")
                if "uddg=" in href:
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    real = qs.get("uddg", [""])[0]
                    if real.startswith("http") and real not in urls:
                        urls.append(real)
                if len(urls) >= max_results:
                    break
    except Exception as e:
        print(f"DuckDuckGo error: {e}")
    return urls

def search_bing(query, max_results=15):
    """Scrape Bing search results."""
    urls = []
    try:
        url = f"https://www.bing.com/search?q={quote(query)}&count={max_results}"
        r = safe_get(url, timeout=12)
        if not r:
            return urls
        soup = BeautifulSoup(r.text, "html.parser")
        for li in soup.select("li.b_algo"):
            a = li.select_one("h2 a")
            if a:
                href = a.get("href", "")
                if href.startswith("http") and "bing.com" not in href and href not in urls:
                    urls.append(href)
            if len(urls) >= max_results:
                break
    except Exception as e:
        print(f"Bing error: {e}")
    return urls

def search_google_custom(query, max_results=10):
    """Use Google Custom Search API if key is configured."""
    if not GOOGLE_API_KEY or not GOOGLE_CX:
        return []
    try:
        url = f"https://www.googleapis.com/customsearch/v1?q={quote(query)}&key={GOOGLE_API_KEY}&cx={GOOGLE_CX}&num={min(max_results, 10)}"
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            urls = []
            for item in data.get("items", []):
                link = item.get("link", "")
                if link.startswith("http"):
                    urls.append(link)
            return urls
    except Exception as e:
        print(f"Google Custom Search error: {e}")
    return []

def search_serpapi(query, max_results=10):
    """Use SerpAPI if key is configured."""
    if not SERP_API_KEY:
        return []
    try:
        url = f"https://serpapi.com/search?q={quote(query)}&api_key={SERP_API_KEY}&engine=google&num={max_results}"
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            urls = []
            for result in data.get("organic_results", []):
                link = result.get("link", "")
                if link.startswith("http"):
                    urls.append(link)
            return urls
    except Exception as e:
        print(f"SerpAPI error: {e}")
    return []

def scrape_website(url, depth=2):
    """Deep scrape a website for contact info."""
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
    pages = [base, base + "/contact", base + "/about", base + "/team"]

    scraped = 0
    for page_url in pages:
        if scraped >= depth or page_url in visited:
            continue
        visited.add(page_url)

        r = safe_get(page_url, timeout=10)
        if not r:
            continue
        scraped += 1

        html = r.text
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator=" ")

        # Extract emails
        for e in EMAIL_RE.findall(text):
            e = e.strip(".,;:"'")
            if "." in e.split("@")[-1] and e not in result["emails"]:
                if not any(x in e.lower() for x in ["example", "domain", "youremail", "email@", "test@", "info@example"]):
                    result["emails"].append(e)

        # Extract phones
        for match in PHONE_RE.findall(text):
            p = "".join(match).strip()
            digits = re.sub(r"\D", "", p)
            if 7 <= len(digits) <= 15 and p not in result["phones"]:
                result["phones"].append(p)

        # Extract socials
        for platform, pattern in SOCIAL_PATTERNS.items():
            full = pattern.search(html)
            if full and not result.get(platform):
                result[platform] = full.group(0).rstrip(""'/>")

        # mailto: links
        for a in soup.select("a[href^='mailto:']"):
            email = a["href"].replace("mailto:", "").split("?")[0].strip()
            if email and email not in result["emails"]:
                result["emails"].append(email)

        # tel: links
        for a in soup.select("a[href^='tel:']"):
            phone = a["href"].replace("tel:", "").strip()
            if phone and phone not in result["phones"]:
                result["phones"].append(phone)

        # Description
        if not result["description"]:
            meta = soup.select_one("meta[name='description'], meta[property='og:description']")
            if meta and meta.get("content"):
                result["description"] = meta["content"][:300]

        # People
        if not result["people"]:
            for selector in ["[class*='team-member']", "[class*='person-card']", "[class*='staff']", "[class*='leadership']", "[class*='bio']"]:
                cards = soup.select(selector)
                for card in cards[:5]:
                    name_el = card.select_one("h2, h3, h4, strong, [class*='name']")
                    role_el = card.select_one("p, span, [class*='title'], [class*='role']")
                    if name_el:
                        name = name_el.get_text(strip=True)
                        if 3 <= len(name) <= 60:
                            result["people"].append({
                                "name": name,
                                "role": role_el.get_text(strip=True) if role_el else "",
                                "email": "",
                                "phone": "",
                                "linkedin": "",
                            })

    return result

def build_result_from_url(url, niche, location):
    """Visit a URL and extract business info."""
    r = safe_get(url, timeout=10)
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    name = ""
    og_title = soup.select_one("meta[property='og:title']")
    if og_title and og_title.get("content"):
        name = og_title["content"].strip()
    if not name and soup.title and soup.title.string:
        name = soup.title.string.strip()
    if not name:
        h1 = soup.select_one("h1")
        name = h1.get_text(strip=True) if h1 else ""

    for suffix in [" | Home", " – Home", " - Home", " | Official", " | Welcome", " | Contact"]:
        name = name.replace(suffix, "")
    name = name[:80]

    if not name or len(name) < 2:
        return None

    site_data = scrape_website(url)

    return {
        "name": name,
        "website": url,
        "address": location,
        "phone": site_data["phones"][0] if site_data.get("phones") else "",
        "email": site_data["emails"][0] if site_data.get("emails") else "",
        "facebook": site_data.get("facebook", ""),
        "instagram": site_data.get("instagram", ""),
        "twitter": site_data.get("twitter", ""),
        "linkedin": site_data.get("linkedin", ""),
        "tiktok": site_data.get("tiktok", ""),
        "youtube": site_data.get("youtube", ""),
        "description": site_data.get("description", ""),
        "rating": "",
        "category": niche,
        "people": site_data.get("people", []),
        "source": "Web Scraping",
    }

def deduplicate(results):
    seen = set()
    clean = []
    for r in results:
        key = r.get("name", "").lower().strip()[:40] + r.get("website", "").lower()
        if key and key not in seen:
            seen.add(key)
            clean.append(r)
    return clean

# ═══════════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    return jsonify({
        "status": "ok",
        "message": "Business scraper is running",
        "version": "2.0-bulletproof",
        "mock_data_available": True,
        "google_api": bool(GOOGLE_API_KEY and GOOGLE_CX),
        "serpapi": bool(SERP_API_KEY),
        "hunter": bool(HUNTER_API_KEY),
    })

@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "endpoints": ["/health", "/scrape", "/export-csv"]})

@app.route("/scrape", methods=["POST", "OPTIONS"])
def scrape():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(force=True, silent=True) or {}

    niche = data.get("niche", "").strip()
    location = data.get("location", "").strip()
    max_results = min(int(data.get("max_results", 10)), 50)
    sources = data.get("sources", ["duckduckgo", "bing", "mock"])
    use_mock = data.get("use_mock", True)  # Default to mock for bulletproof results

    if not niche or not location:
        return jsonify({"error": "niche and location are required"}), 400

    query = f"{niche} {location}"
    all_results = []

    print(f"[SCRAPE] query='{query}' max={max_results} sources={sources}")

    # ═══════════════════════════════════════════════════════════════════════════
    # STRATEGY 1: Try real APIs first (if configured)
    # ═══════════════════════════════════════════════════════════════════════════

    # Try Google Custom Search API
    if "google" in sources and GOOGLE_API_KEY and GOOGLE_CX:
        google_urls = search_google_custom(f"{query} contact", max_results)
        print(f"  Google API: {len(google_urls)} URLs")
        for url in google_urls:
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    # Try SerpAPI
    if "serpapi" in sources and SERP_API_KEY and len(all_results) < max_results:
        serp_urls = search_serpapi(f"{query} business", max_results)
        print(f"  SerpAPI: {len(serp_urls)} URLs")
        for url in serp_urls:
            if len(all_results) >= max_results * 2:
                break
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    # ═══════════════════════════════════════════════════════════════════════════
    # STRATEGY 2: Try web scraping (usually blocked from cloud, but try anyway)
    # ═══════════════════════════════════════════════════════════════════════════

    if "duckduckgo" in sources and len(all_results) < max_results:
        ddg_urls = search_duckduckgo(f"{query} official website", max_results)
        print(f"  DuckDuckGo: {len(ddg_urls)} URLs")
        for url in ddg_urls:
            if len(all_results) >= max_results * 2:
                break
            skip = any(x in url for x in ["google.", "bing.", "facebook.", "instagram.", "twitter.", "youtube.", "wikipedia.", "yelp.com", "yellowpages.com"])
            if skip:
                continue
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    if "bing" in sources and len(all_results) < max_results:
        bing_urls = search_bing(f"{query} contact email", max_results)
        print(f"  Bing: {len(bing_urls)} URLs")
        for url in bing_urls:
            if len(all_results) >= max_results * 2:
                break
            skip = any(x in url for x in ["google.", "bing.", "facebook.", "instagram.", "twitter.", "youtube.", "wikipedia.", "yelp.com", "yellowpages.com"])
            if skip:
                continue
            biz = build_result_from_url(url, niche, location)
            if biz:
                all_results.append(biz)

    # ═══════════════════════════════════════════════════════════════════════════
    # STRATEGY 3: FALLBACK — Mock Data (GUARANTEED to work)
    # ═══════════════════════════════════════════════════════════════════════════

    if ("mock" in sources or use_mock) and len(all_results) < max_results:
        mock_results = get_mock_results(niche, location, max_results - len(all_results))
        print(f"  Mock Data: {len(mock_results)} results")
        all_results.extend(mock_results)

    # Deduplicate and trim
    all_results = deduplicate(all_results)[:max_results]

    print(f"[SCRAPE] Done — {len(all_results)} unique results")

    return jsonify({
        "query": query,
        "count": len(all_results),
        "results": all_results,
        "note": "Using demo data. Add SERP_API_KEY or GOOGLE_API_KEY environment variables for real-time scraping." if any(r.get("source") == "Mock Database (Demo Mode)" for r in all_results) else "Real-time data",
    })

@app.route("/export-csv", methods=["POST", "OPTIONS"])
def export_csv():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(force=True, silent=True) or {}
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

    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=businesses.csv"}
    )

# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
