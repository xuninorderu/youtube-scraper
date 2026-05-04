# YouTube SEO Intelligence Tool

Find YouTube channels by niche + location. Extracts emails, phones, social links, subscriber counts, and key contact people. Embeddable in Google Sites.

---

## Files in this repo

| File | Purpose |
|---|---|
| `app.py` | Flask backend — deploy to Railway |
| `requirements.txt` | Python dependencies |
| `Procfile` | Railway start command |
| `youtube_seo.html` | Frontend — embed in Google Sites |

---

## Deploy to Railway

### Step 1 — Push to GitHub
Upload all files to this repo (already done).

### Step 2 — Deploy on Railway
1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select this repo → Railway auto-detects Python + deploys
3. Wait ~3 minutes for build

### Step 3 — Set YouTube API Key
In Railway dashboard → your project → **Variables** → Add:
```
YT_API_KEY = your_youtube_api_key_here
```

> Get a free key: [console.cloud.google.com](https://console.cloud.google.com) → New Project → Enable **YouTube Data API v3** → Credentials → Create API Key

### Step 4 — Get your URL
Railway dashboard → Settings → **Generate Domain**
Copy it (e.g. `https://web-production-54c9f.up.railway.app`)

---

## Test your backend

```
https://YOUR-APP.up.railway.app/health
```
Should return:
```json
{"status": "ok", "yt_api": "connected"}
```

---

## Embed in Google Sites

1. Open `youtube_seo.html` in Notepad
2. Find the backend URL field (it's editable in the UI — no code change needed)
3. In Google Sites → Edit → Insert → Embed → **Embed code** tab
4. Paste the full HTML → Next → Insert
5. Drag the embed box to at least **900px tall**
6. Publish

---

## Optional: Hunter.io (finds more emails)

In Railway Variables add:
```
HUNTER_API_KEY = your_hunter_key
```
Free at [hunter.io](https://hunter.io) — 25 searches/month.

---

## Features

- Search by keyword + location
- Sort by relevance, views, rating, video count
- Filter by min/max subscribers
- Filter by country
- Extracts: email, phone, website, Facebook, Instagram, Twitter/X, TikTok, LinkedIn
- Key people: name, role, email from creator websites
- Channel stats: subscribers, total views, video count, join date
- Export to CSV
- Works without API key (scrape fallback mode)
