"""Etsy SEO Tool — free, self-hosted Streamlit app for Etsy sellers.

What it does (read-only — it never edits your shop):
  Tab 1  Keyword Research — search live Etsy listings, filter them,
         and see which tags buyers love (Tag Analyzer).
  Tab 2  SEO Audit — paste a title/tags/description and get a 0-100
         score with exact fixes.
  Tab 3  Keyword Ideas — one-click starter keywords per product type.
  Plus: Shop Analyzer (any public shop) and a Competitor Tracker
  (save snapshots, compare favourites/views over time).

Setup:
  1. Create a free app at https://www.etsy.com/developers/your-apps
     - Callback URL must be exactly: http://localhost:8080/callback
     - Enable the scopes: listings_r, shops_r
  2. Copy .env.example to .env and paste your Keystring + Shared Secret.
  3. Run:  streamlit run app.py
  4. Click "Connect to Etsy" in the sidebar and approve in the browser.

Never commit .env or tokens.json — both are in .gitignore.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
from auth import EtsyAuthError
from etsy_client import EtsyAPIError, EtsyClient
import keyword_suggestions as ks
import research
from seo_audit import score_listing, suggest_tags

st.set_page_config(page_title="Etsy SEO Tool", page_icon="🔍", layout="wide")
st.title("🔍 Etsy SEO Tool")
st.caption("Free keyword research, tag analysis and SEO audit for Etsy sellers. Read-only — it never edits your shop.")

# ---------------------------------------------------------------------------
# Sidebar — connection
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Connect to Etsy")
    status = auth.token_status()
    if status["connected"]:
        st.success("Connected to Etsy ✅")
        if status["expired"]:
            st.warning("Token expired — it will refresh automatically on the next call.")
        else:
            st.write(f"Token valid for ~{status['seconds_left'] // 60} more minutes.")
        if st.button("Disconnect (delete saved tokens)"):
            auth.clear_tokens()
            st.rerun()
    else:
        st.info("Not connected yet.")
        if st.button("Connect to Etsy"):
            try:
                with st.spinner("Opening Etsy in your browser — approve, then come back here…"):
                    auth.ensure_authenticated()
                st.success("Connected! ✅")
                st.rerun()
            except EtsyAuthError as exc:
                st.error(str(exc))
    st.divider()
    st.markdown(
        "**First time?**\n"
        "1. Create an app at [Etsy Developers](https://www.etsy.com/developers/your-apps)\n"
        "2. Callback URL: `http://localhost:8080/callback`\n"
        "3. Enable scopes: `listings_r`, `shops_r`\n"
        "4. Copy `.env.example` to `.env` and paste your Keystring + Shared Secret."
    )
    st.divider()
    st.caption(
        "Honest limit: the Etsy API does not report sales numbers. "
        "Favorites + Views are the best popularity signals it provides — "
        "this tool never labels them 'sales'."
    )


def get_client() -> EtsyClient | None:
    """Return a client, or show why it is not available yet."""
    if not auth.token_status()["connected"]:
        st.warning("Connect to Etsy from the sidebar first.")
        return None
    return EtsyClient()


def show_results_table(df: pd.DataFrame, key: str) -> None:
    if df.empty:
        st.info("No listings found — try a broader keyword or looser filters.")
        return
    st.dataframe(df, use_container_width=True, key=key)
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Download CSV", research.export_to_csv_bytes(df),
            file_name="etsy_research.csv", mime="text/csv", key=f"{key}-csv",
        )
    with c2:
        st.download_button(
            "⬇️ Download Excel", research.export_to_excel_bytes(df),
            file_name="etsy_research.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key}-xlsx",
        )


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "🔎 Keyword Research", "✅ SEO Audit", "💡 Keyword Ideas",
])

# --- Tab 1: Keyword Research ----------------------------------------------
with tab1:
    st.header("Keyword Research")
    st.write("Search live Etsy listings for a keyword, filter them, and find the tags that actually perform.")

    keyword = st.text_input("Keyword", value="junk journal printable",
                            help="What buyers type into Etsy search.")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        sort = st.selectbox("Sort by", list(research.SORT_MAP.keys()), index=0)
        limit = st.slider("How many listings", 10, 100, 50, step=10)
    with col_b:
        min_price = st.number_input("Min price ($)", min_value=0.0, value=0.0, step=0.5)
        max_price = st.number_input("Max price ($)", min_value=0.0, value=0.0, step=0.5,
                                    help="0 = no maximum.")
        release = st.selectbox("Listed in the last…", list(research.RELEASE_TIME_OPTIONS.keys()), index=0)
    with col_c:
        category = st.selectbox("Category", [c for c, _ in research.CATEGORY_PRESETS], index=0)
        min_fav = st.number_input("Min. favourites", min_value=0, value=0, step=10)
        min_views = st.number_input("Min. views", min_value=0, value=0, step=10)

    if st.button("🔎 Search Etsy", type="primary"):
        client = get_client()
        if client is not None:
            taxonomy_id = dict(research.CATEGORY_PRESETS).get(category, 0) or None
            try:
                with st.spinner("Searching Etsy…"):
                    listings = research.search_active_listings(
                        client, keyword,
                        min_price=min_price or None,
                        max_price=max_price or None,
                        sort=sort, limit=limit, taxonomy_id=taxonomy_id,
                        release_days=research.RELEASE_TIME_OPTIONS[release],
                        min_favorites=min_fav or None,
                        min_views=min_views or None,
                    )
                df = research.listings_to_dataframe(listings)
                st.session_state["last_listings"] = listings
                st.session_state["last_df"] = df
                st.success(f"Found {len(df)} listings for '{keyword}'.")
            except (EtsyAPIError, EtsyAuthError) as exc:
                st.error(str(exc))

    df = st.session_state.get("last_df")
    if df is not None and not df.empty:
        st.subheader("Listings (sorted by Favorites)")
        show_results_table(df, key="research")

        st.subheader("🏷️ Tag Analyzer — which tags perform?")
        st.caption("Opportunity Score = avg favourites per listing ÷ how often the tag appears. "
                   "Tags used by only one listing are left out — they are not real opportunities.")
        tag_df = research.analyze_tags(df)
        if tag_df.empty:
            st.info("Not enough repeated tags in this search to rank.")
        else:
            st.dataframe(tag_df, use_container_width=True)

        st.subheader("📸 Competitor Tracker")
        st.caption("Save today's favourites/views, then compare with the last snapshot to see what moved.")
        if st.button("💾 Save snapshot of these listings"):
            snap = research.save_snapshot(st.session_state["last_listings"], keyword)
            st.success(f"Snapshot saved ({len(snap['items'])} listings, {snap['saved_at'][:10]}).")
        if st.button("📊 Compare with previous snapshot"):
            delta, prev_at, latest_at = research.compare_latest_snapshots(keyword)
            if delta.empty:
                st.info("Need 2 snapshots for the same keyword first — search and save again another day.")
            else:
                st.write(f"Comparing {prev_at[:10]} → {latest_at[:10]}")
                st.dataframe(delta, use_container_width=True)

    st.divider()
    st.header("🏪 Shop Analyzer")
    st.write("Look up any public Etsy shop — profile, reviews, total sold, top listings.")
    shop_q = st.text_input("Shop name, URL or ID", placeholder="e.g. MAYLArts")
    if st.button("Analyze shop"):
        client = get_client()
        if client is not None:
            try:
                with st.spinner("Reading the shop…"):
                    result = research.analyze_shop(client, shop_q, limit=20)
                s = result["summary"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Active listings", s["active_listings"])
                c2.metric("Reviews", f"{s['review_count']} ({s['review_average']}★)")
                c3.metric("Total sold", s["total_sold"])
                c4.metric("Shop favourers", s["shop_favorers"])
                st.write(f"**[{s['shop_name']}]({s['url']})** — {s['title']}")
                show_results_table(result["top_listings"], key="shop")
            except (EtsyAPIError, EtsyAuthError, ValueError) as exc:
                st.error(str(exc))

# --- Tab 2: SEO Audit ------------------------------------------------------
with tab2:
    st.header("SEO Audit — score your listing 0-100")
    st.write("Paste your title, tags, description, photo count and price. No API call needed.")
    title = st.text_input("Title (up to 140 chars)", max_chars=140,
                          placeholder="Dark Academia Junk Journal Kit Printable | …")
    tags_raw = st.text_area("Tags (one per line, or comma-separated — 13 total)",
                            placeholder="junk journal kit\nvintage ephemera\ncollage sheet",
                            height=120)
    desc = st.text_area("Description", height=120,
                        placeholder="Digital download — no physical item will be shipped…")
    col_a, col_b = st.columns(2)
    with col_a:
        photos = st.number_input("How many photos?", min_value=0, max_value=10, value=7, step=1)
    with col_b:
        price = st.number_input("Price ($)", min_value=0.0, value=5.0, step=0.5)

    if st.button("✅ Score my listing", type="primary"):
        if "," in tags_raw:
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        else:
            tags = [t.strip() for t in tags_raw.splitlines() if t.strip()]
        result = score_listing(title, tags, desc, photos=int(photos), price=float(price))
        st.metric("SEO Score", f"{result['score']} / 100", result["grade"])
        st.subheader("Checks")
        for c in result["checks"]:
            icon = "✅" if c["ok"] else "❌"
            st.write(f"{icon} **{c['check']}** — {c['points']}/{c['max']} points")
            if not c["ok"] and c["tip"]:
                st.caption(c["tip"])
        if result["fixes"]:
            st.subheader("Fix these")
            for fix in result["fixes"]:
                st.write("• " + fix)
        else:
            st.success("Nothing to fix — this listing is ready. 🎉")
        weak = [t for t in tags if t in
                {"a4 printable", "letter size", "mixed media", "a5 printable", "paper", "art"}]
        if weak:
            st.info(f"Stronger replacements for weak tags: {suggest_tags(tags)}")

# --- Tab 3: Keyword Ideas --------------------------------------------------
with tab3:
    st.header("Keyword Ideas")
    st.write("Starter keywords per product type. Tap one to search it in Tab 1.")
    category_pick = st.selectbox("Product type", ks.all_categories(), index=0)
    for kw, why in ks.keywords_for_category(category_pick):
        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button(f"🔎 {kw}", key=f"kw-{kw}"):
                st.session_state["preset_keyword"] = kw
                st.info(f"Go to Tab 1 and search for '{kw}' — or type it in the keyword box there.")
        with col_b:
            st.write(why)
    st.divider()
    st.subheader("Evergreen keywords (any product)")
    for kw, why in ks.EVERGREEN_KEYWORDS:
        st.write(f"• **{kw}** — {why}")
