# 🔍 Etsy SEO Tool

**Free keyword research, tag analysis and SEO audit for Etsy sellers — self-hosted, read-only, no monthly fee.**

Search live Etsy listings for any keyword, see which tags buyers actually love, score your own listing 0–100, look up any public shop, and track competitors over time.

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.36+-red)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

| Tab | What you get |
|---|---|
| 🔎 **Keyword Research** | Live Etsy search with filters (category, price, sort, release time, min. favourites/views) + results table + CSV/Excel export |
| 🏷️ **Tag Analyzer** | Which tags perform best — Opportunity Score = avg favourites ÷ frequency. Tags used by only one listing are left out (they are not real opportunities) |
| ✅ **SEO Audit** | Paste title/tags/description/photos/price → 0–100 score with exact fixes |
| 💡 **Keyword Ideas** | One-click starter keywords per product type (junk journals, planners, paper packs, wall art, stickers, wedding) |
| 🏪 **Shop Analyzer** | Any public shop by name/URL/ID — reviews, total sold, top listings |
| 📸 **Competitor Tracker** | Save a snapshot of favourites/views today, compare with the last one |

**Honest limit:** the Etsy API does not report sales numbers. Other tools show "total sales" as estimates. This tool uses Favorites + Views as the popularity signal — and never labels them "sales".

---

## Quick start

### 1. Get free Etsy API credentials

1. Go to [Etsy Developers — Your Apps](https://www.etsy.com/developers/your-apps) and create an app.
2. Set the **Callback URL** to exactly: `http://localhost:8080/callback`
3. Enable the scopes: `listings_r`, `shops_r` (read-only — this tool never edits your shop).
4. Copy your **Keystring** and **Shared Secret**.

### 2. Install

```bash
git clone https://github.com/<your-username>/etsy-seo-tool.git
cd etsy-seo-tool
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and paste your Keystring and Shared Secret.

**Windows shortcut:** double-click `Start_Etsy_SEO_Tool.bat` — it creates the venv, installs everything and opens the app.

### 3. Run

```bash
streamlit run app.py
```

Open http://localhost:8501, click **Connect to Etsy** in the sidebar, approve in the browser — done. Tokens are saved locally in `tokens.json` and refresh automatically (they last ~1 hour).

---

## Why this exists

Paid Etsy research tools charge $10–30/month for the same public data. This one is free, open source, and runs on your own computer. Your API keys stay in your own `.env` — they are never uploaded anywhere.

## How it earns its keep (for the maintainer)

This project is free. If it saves you money, you can support it:

- ⭐ Star the repo
- 💚 [Sponsor on GitHub](https://github.com/sponsors/<your-username>) — $5/month keeps it maintained
- 📘 The companion **Etsy SEO Playbook** (paid PDF guide) — link in the repo

## Contributing

Issues and pull requests are welcome. Keep it free, keep it honest: no fake "sales" numbers, no copied competitor images, no secrets in the code.

## License

MIT — see [LICENSE](LICENSE).
