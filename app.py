"""
YouTuber Scraper — Flask Backend API
=====================================
Run locally or deploy to Railway / Render for free.

Install:
    pip install flask flask-cors requests beautifulsoup4 selenium webdriver-manager pandas google-api-python-client

Run locally:
    python app.py
    → http://localhost:5000

Deploy to Railway:
    1. Push this folder to GitHub
    2. Connect repo on railway.app
    3. Done — Railway auto-detects Flask
"""

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import re, time, json, logging, requests, csv, io
from bs4 import BeautifulSoup
from datetime import datetime

# ── Optional Selenium ────────────────────────────────────────────────────────
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False

# ── Optional YouTube API ─────────────────────────────────────────────────────
try:
    from googleapiclient.discovery import build as yt_build
    YT_API_OK = True
except ImportError:
    YT_API_OK = False

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)   # Allow Google Sites to call this API

# ════════════════════════════════════════════════════════════
#  CONFIG  (edit YouTube API key if you have one)
# ════════════════════════════════════════════════════════════
YT_API_KEY = ""   # Optional — paste your key here for richer data

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
PHONE_RE = [
    r"\+880[\s\-]?\d{2}[\s\-]?\d{8}",
    r"01[3-9]\d{8}",
    r"\+?\d[\d\s\-\(\)]{9,17}\d",
]
SOCIAL_RE = {
    "facebook":  r"facebook\.com/[A-Za-z0-9_.%-]+",
    "instagram": r"instagram\.com/[A-Za-z0-9_.%-]+",
    "twitter":   r"(?:twitter|x)\.com/[A-Za-z0-9_]+",
    "tiktok":    r"tiktok\.com/@[A-Za-z0-9_.%-]+",
    "linkedin":  r"linkedin\.com/(?:in|company)/[A-Za-z0-9_%-]+",
}

# ════════════════════════════════════════════════════════════
#  SELENIUM DRIVER
# ════════════════════════════════════════════════════════════
_driver = None

def get_driver():
    global _driver
    if _driver:
        try:
            _ = _driver.title
            return _driver
        except Exception:
            _driver = None
    if not SELENIUM_OK:
        return None
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
    try:
        svc = Service(ChromeDriverManager().install())
        _driver = webdriver.Chrome(service=svc, options=opts)
        return _driver
    except Exception as e:
        log.error(f"Chrome driver error: {e}")
        return None

def fetch_html(url, wait=3):
    driver = get_driver()
    if driver:
        try:
            driver.get(url)
            time.sleep(wait)
            return driver.page_source
        except Exception:
            pass
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        return r.text
    except Exception:
        return ""

# ════════════════════════════════════════════════════════════
#  YOUTUBE SEARCH
# ════════════════════════════════════════════════════════════

def search_via_api(query, max_results=30):
    if not YT_API_OK or not YT_API_KEY:
        return []
    try:
        yt = yt_build("youtube", "v3", developerKey=YT_API_KEY)
        resp = yt.search().list(
            q=query, part="snippet", type="channel",
            maxResults=min(max_results, 50)
        ).execute()
        results = []
        for item in resp.get("items", []):
            s = item["snippet"]
            cid = item["id"]["channelId"]
            results.append({
                "channel_id":   cid,
                "channel_name": s.get("channelTitle", ""),
                "description":  s.get("description", ""),
                "channel_url":  f"https://www.youtube.com/channel/{cid}",
                "thumbnail":    s.get("thumbnails", {}).get("medium", {}).get("url", ""),
            })
        return results
    except Exception as e:
        log.error(f"YT API error: {e}")
        return []

def search_via_scrape(query):
    url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}&sp=EgIQAg%3D%3D"
    html = fetch_html(url, wait=4)
    if not html:
        return []

    match = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except Exception:
        return []

    contents = (
        data.get("contents", {})
            .get("twoColumnSearchResultsRenderer", {})
            .get("primaryContents", {})
            .get("sectionListRenderer", {})
            .get("contents", [])
    )
    results = []
    for section in contents:
        for item in section.get("itemSectionRenderer", {}).get("contents", []):
            ch = item.get("channelRenderer")
            if not ch:
                continue
            cid  = ch.get("channelId", "")
            name = ch.get("title", {}).get("simpleText", "")
            desc = "".join(r.get("text","") for r in ch.get("descriptionSnippet",{}).get("runs",[]))
            subs = ch.get("subscriberCountText", {}).get("simpleText", "")
            thumb = (ch.get("thumbnail",{}).get("thumbnails") or [{}])[-1].get("url","")
            results.append({
                "channel_id":   cid,
                "channel_name": name,
                "description":  desc,
                "channel_url":  f"https://www.youtube.com/channel/{cid}",
                "thumbnail":    thumb,
                "subscribers":  subs,
            })
    return results

# ════════════════════════════════════════════════════════════
#  CHANNEL ABOUT PAGE
# ════════════════════════════════════════════════════════════

def scrape_about(channel_url):
    about_url = channel_url.rstrip("/") + "/about"
    html = fetch_html(about_url, wait=3)
    info = {"website": "", "email": "", "phone": "", "socials": {}}

    emails = [e for e in re.findall(EMAIL_RE, html)
              if not e.endswith((".png",".jpg",".svg",".webp"))]
    if emails:
        info["email"] = emails[0]

    for pat in PHONE_RE:
        found = re.findall(pat, html)
        if found:
            info["phone"] = found[0].strip()
            break

    for platform, pat in SOCIAL_RE.items():
        found = re.findall(pat, html, re.IGNORECASE)
        if found:
            info["socials"][platform] = "https://" + found[0]

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and "youtube.com" not in href and "google.com" not in href:
            info["website"] = href
            break

    return info

# ════════════════════════════════════════════════════════════
#  WEBSITE SCRAPE
# ════════════════════════════════════════════════════════════

def scrape_website(url):
    data = {"web_email": "", "web_phone": "", "web_socials": {}}
    if not url:
        return data

    combined = ""
    for slug in ["", "/contact", "/about", "/contact-us"]:
        try:
            combined += fetch_html(url.rstrip("/") + slug, wait=2)
        except Exception:
            pass

    emails = [e for e in re.findall(EMAIL_RE, combined)
              if not e.endswith((".png",".jpg",".svg",".webp"))]
    if emails:
        data["web_email"] = emails[0]

    for pat in PHONE_RE:
        found = re.findall(pat, combined)
        if found:
            data["web_phone"] = found[0].strip()
            break

    for platform, pat in SOCIAL_RE.items():
        found = re.findall(pat, combined, re.IGNORECASE)
        if found:
            data["web_socials"][platform] = "https://" + found[0]

    return data

# ════════════════════════════════════════════════════════════
#  API ROUTES
# ════════════════════════════════════════════════════════════

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


@app.route("/scrape", methods=["POST"])
def scrape():
    body       = request.get_json() or {}
    niche      = body.get("niche", "").strip()
    location   = body.get("location", "").strip()
    max_results = int(body.get("max_results", 20))

    if not niche or not location:
        return jsonify({"error": "niche and location are required"}), 400

    query    = f"{niche} {location}"
    channels = search_via_api(query, max_results) or search_via_scrape(query)
    channels = channels[:max_results]

    results = []
    for ch in channels:
        about    = scrape_about(ch.get("channel_url", ""))
        web_data = scrape_website(about.get("website", ""))

        results.append({
            "channel_name": ch.get("channel_name", ""),
            "channel_url":  ch.get("channel_url", ""),
            "subscribers":  ch.get("subscribers", ""),
            "description":  ch.get("description", "")[:200],
            "thumbnail":    ch.get("thumbnail", ""),
            "website":      about.get("website", ""),
            "email":        web_data.get("web_email") or about.get("email", ""),
            "phone":        web_data.get("web_phone") or about.get("phone", ""),
            "facebook":     about["socials"].get("facebook") or web_data["web_socials"].get("facebook",""),
            "instagram":    about["socials"].get("instagram") or web_data["web_socials"].get("instagram",""),
            "twitter":      about["socials"].get("twitter") or web_data["web_socials"].get("twitter",""),
            "tiktok":       about["socials"].get("tiktok") or web_data["web_socials"].get("tiktok",""),
            "linkedin":     about["socials"].get("linkedin") or web_data["web_socials"].get("linkedin",""),
        })

    return jsonify({
        "query":   query,
        "count":   len(results),
        "results": results,
        "scraped_at": datetime.now().strftime("%d %b %Y, %H:%M"),
    })


@app.route("/export-csv", methods=["POST"])
def export_csv():
    body    = request.get_json() or {}
    results = body.get("results", [])
    fields  = ["channel_name","channel_url","subscribers","email","phone",
               "website","facebook","instagram","twitter","tiktok","description"]
    buf = io.StringIO()
    w   = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(results)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=youtubers.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
