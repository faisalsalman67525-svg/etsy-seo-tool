"""
research.py — Market research & competitor spy (Etsy listings/active).

EHunt-style upgrade (2026-11-24):
  * Filters like EHunt's Product Research page: category (taxonomy_id),
    price range, minimum favourites / views, release time (30 / 180 /
    365 days / All Time), sort by relevancy / newest / top favourites /
    price.
  * Shop Analyzer: any public shop by name, URL or ID — profile,
    reviews, total sold, top listings by favourites.
  * Competitor Tracker: save a snapshot of listings today, compare it
    with the last snapshot — see how favourites / views moved.
    The tracker only builds history from the day you save your first
    snapshot — Etsy does not provide past data.

HONEST LIMIT:
  The Etsy API does not report "total sales" or "7-day sales / revenue".
  Other tools show those numbers as ESTIMATES (guessed from favourites,
  reviews and history). This tool uses Favorites and Views as the
  popularity signal instead — and never labels them "sales". The numbers
  Etsy does provide (favourites, views, reviews, a shop's
  transaction_sold_count) are real; everything else is a guess.

Uses the public GET /listings/active endpoint — no shop ownership needed.
Sort options map to Etsy's real sort_on values:
  relevancy       -> sort_on=score
  most recent     -> sort_on=created, desc
  top favorites   -> sort_on=score, desc, then sorted locally by Favorites
                     (Etsy has no direct favourites sort)
  top reviews     -> sort_on=score, desc (Etsy has no direct review sort;
                      score is its relevance/quality ranking — best proxy)
  price low-high  -> sort_on=price, asc
  price high-low  -> sort_on=price, desc
"""
from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from etsy_client import EtsyClient

SORT_MAP = {
    "relevancy": ("score", "desc"),
    "most recent": ("created", "desc"),
    "top favorites": ("score", "desc"),
    "top customer reviews": ("score", "desc"),
    "price: low to high": ("price", "asc"),
    "price: high to low": ("price", "desc"),
}

# EHunt "Release time" buttons, as days (None = All Time).
RELEASE_TIME_OPTIONS = {
    "All Time": None,
    "30 Days": 30,
    "180 Days": 180,
    "1 Year": 365,
}

# Category presets. 6585 = Scrapbooking Ephemera (junk-journal kits) is
# one example — any other category: enter its taxonomy ID in the Custom ID box.
# Find taxonomy IDs with Etsy's seller-taxonomy endpoint or the Category Finder.
CATEGORY_PRESETS = [
    ("All categories", 0),
    ("Scrapbooking Ephemera — junk journal kits (6585)", 6585),
]

SALES_NOTE = (
    "The Etsy API does not report sales numbers, so an exact 'Total sales' "
    "figure is not possible. Favorites + Views are the best popularity "
    "signals Etsy actually provides."
)

# Competitor Tracker snapshots live next to this file (created on first save).
TRACKER_FILE = Path(__file__).resolve().parent / "tracker_snapshots.json"
MAX_SNAPSHOTS_KEPT = 30


# ---------------------------------------------------------------------------
# Helpers — pure functions (no API call), so they are easy to test
# ---------------------------------------------------------------------------
def listing_age_days(item: dict, now: float | None = None) -> int | None:
    """Days since the listing was created (None if Etsy gave no date)."""
    created = item.get("created_timestamp") or item.get("original_creation_timestamp")
    if not created:
        return None
    now = now if now is not None else time.time()
    return max(0, int((now - int(created)) // 86400))


def passes_filters(
    item: dict,
    release_days: int | None = None,
    min_favorites: int | None = None,
    min_views: int | None = None,
    now: float | None = None,
) -> bool:
    """Client-side EHunt-style filters (Etsy API has no favourites/views filter)."""
    if release_days is not None:
        age = listing_age_days(item, now=now)
        if age is not None and age > release_days:
            return False
    if min_favorites:
        if int(item.get("num_favorers") or 0) < int(min_favorites):
            return False
    if min_views:
        if int(item.get("views") or 0) < int(min_views):
            return False
    return True


def filter_listings(
    listings: list[dict],
    release_days: int | None = None,
    min_favorites: int | None = None,
    min_views: int | None = None,
) -> list[dict]:
    """Filter a raw listing list with the EHunt-style filters above."""
    now = time.time()
    return [
        item
        for item in listings
        if passes_filters(item, release_days, min_favorites, min_views, now=now)
    ]


# ---------------------------------------------------------------------------
# Product search — EHunt-style
# ---------------------------------------------------------------------------
def search_active_listings(
    client: EtsyClient,
    keyword: str,
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = "relevancy",
    limit: int = 50,
    taxonomy_id: int | None = None,
    release_days: int | None = None,
    min_favorites: int | None = None,
    min_views: int | None = None,
) -> list[dict]:
    """Fetch up to `limit` active listings (Etsy caps 100 per page).

    taxonomy_id / release_days / min_favorites / min_views are the
    EHunt-style filters. taxonomy_id goes to the Etsy API; the rest are
    applied client-side, so this keeps fetching pages until `limit`
    filtered listings are found (or the API runs out / 500 raw listings
    have been checked — a safety cap so a very strict filter cannot
    loop forever against Etsy's 10,000/day limit).
    """
    sort_on, sort_order = SORT_MAP.get(sort.lower(), ("score", "desc"))
    results: list[dict] = []
    offset = 0
    raw_checked = 0
    while len(results) < limit and raw_checked < 500:
        page_size = min(100, limit - len(results) + 50)
        # Etsy v3 wants "keywords" (plural) — "keyword" (singular) is ignored
        # by the API, so every search used to return the same generic feed.
        # Fixed 2026-11-22 after the "same results every time" bug.
        params: dict = {
            "keywords": keyword,
            "limit": page_size,
            "offset": offset,
            "sort_on": sort_on,
            "sort_order": sort_order,
        }
        if min_price is not None:
            params["min_price"] = min_price
        if max_price is not None:
            params["max_price"] = max_price
        if taxonomy_id:
            params["taxonomy_id"] = int(taxonomy_id)
        data = client.get("/listings/active", params=params)
        batch = data.get("results", []) if isinstance(data, dict) else []
        if not batch:
            break
        raw_checked += len(batch)
        offset += len(batch)
        results.extend(filter_listings(batch, release_days, min_favorites, min_views))
        if len(batch) < page_size:
            break
    return results[:limit]


def listings_to_dataframe(listings: list[dict]) -> pd.DataFrame:
    """Normalise raw Etsy JSON into the clean research table.

    Columns: Price, Views, Favorites, Created, Age (days),
    Tags, Shop — plus Is Digital / Taxonomy ID. Sorted by Favorites
    (the best popularity signal Etsy provides) — NOT by claimed sales,
    which Etsy does not report.
    """
    rows = []
    for item in listings:
        price = item.get("price") or {}
        created_ts = item.get("created_timestamp") or item.get(
            "original_creation_timestamp"
        )
        rows.append(
            {
                "Listing ID": item.get("listing_id"),
                "Title": item.get("title", ""),
                "Price": price.get("amount", 0) / 100 if price.get("amount") else 0,
                "Currency": price.get("currency_code", "USD"),
                "Views": item.get("views", 0),
                "Favorites": item.get("num_favorers", 0),
                "Created": (
                    datetime.fromtimestamp(int(created_ts), tz=timezone.utc).date().isoformat()
                    if created_ts
                    else ""
                ),
                "Age (days)": listing_age_days(item),
                "Tags": ", ".join(item.get("tags") or []),
                "Materials": ", ".join(item.get("materials") or []),
                "Shop": (item.get("shop") or {}).get("shop_name", ""),
                "URL": f"https://www.etsy.com/listing/{item.get('listing_id')}/",
                "Is Digital": (
                    "Yes"
                    if item.get("is_digital") or item.get("type") == "download"
                    else "No"
                ),
                "Taxonomy ID": item.get("taxonomy_id", ""),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Favorites", ascending=False).reset_index(drop=True)
    return df


def analyze_tags(df: pd.DataFrame, listings: list[dict] | None = None) -> pd.DataFrame:
    """
    Tag frequency across the researched listings.
    Opportunity score = avg favourites per listing using the tag,
    divided by how often the tag appears — high score + low frequency
    suggests a high-performing, lower-competition keyword.
    Returns a DataFrame sorted by opportunity score.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["Tag", "Frequency", "Avg Price", "Avg Favorites", "Avg Views", "Opportunity Score"]
        )
    # Rebuild per-tag stats from the raw tag lists (not the joined string).
    tag_stats: dict[str, dict] = {}
    for _, row in df.iterrows():
        tags = [t.strip().lower() for t in str(row["Tags"]).split(",") if t.strip()]
        for tag in tags:
            s = tag_stats.setdefault(
                tag, {"count": 0, "price_sum": 0.0, "fav_sum": 0, "view_sum": 0}
            )
            s["count"] += 1
            s["price_sum"] += float(row["Price"] or 0)
            s["fav_sum"] += int(row["Favorites"] or 0)
            s["view_sum"] += int(row["Views"] or 0)

    rows = []
    for tag, s in tag_stats.items():
        freq = s["count"]
        # 2026-11-22 fix: frequency-1 tags are NOT opportunities — they are
        # just the #1 listing's own tags (e.g. "my porch prints" scored 1872
        # from a single listing). Only tags used by 2+ listings are ranked.
        if freq < 2:
            continue
        avg_fav = s["fav_sum"] / freq
        rows.append(
            {
                "Tag": tag,
                "Frequency": freq,
                "Avg Price": round(s["price_sum"] / freq, 2),
                "Avg Favorites": round(avg_fav, 1),
                "Avg Views": round(s["view_sum"] / freq, 1),
                "Opportunity Score": round(avg_fav / freq, 2),
            }
        )
    out = pd.DataFrame(rows).sort_values(
        ["Opportunity Score", "Avg Favorites"], ascending=False
    ).reset_index(drop=True)
    return out


def tag_frequency_counter(listings: list[dict]) -> Counter:
    counter: Counter = Counter()
    for item in listings:
        for tag in item.get("tags") or []:
            counter[str(tag).strip().lower()] += 1
    return counter


def export_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def export_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Research") -> bytes:
    import io

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        # Sensible column widths so the file opens cleanly.
        widths = [12, 55, 10, 10, 10, 12, 12, 10, 45, 30, 20, 55, 10, 12]
        for i, col in enumerate(df.columns):
            letter = chr(65 + i) if i < 26 else "A"
            worksheet.column_dimensions[letter].width = widths[i] if i < len(widths) else 15
    buffer.seek(0)
    return buffer.read()


# ---------------------------------------------------------------------------
# Shop Analyzer — any public shop by name, URL or ID
# ---------------------------------------------------------------------------
def resolve_shop_id(client: EtsyClient, query: str) -> int:
    """'MAYLArts' / 'https://www.etsy.com/shop/MAYLArts' / '12345678' -> shop_id."""
    q = (query or "").strip()
    if not q:
        raise ValueError("Enter a shop name, URL or ID.")
    if q.isdigit():
        return int(q)
    if "etsy.com/shop/" in q:
        path = urlparse(q if q.startswith("http") else f"https://{q}").path
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "shop":
            q = parts[1]
    data = client.get("/shops", params={"shop_name": q})
    results = data.get("results", []) if isinstance(data, dict) else []
    if not results:
        raise ValueError(f"No shop named '{q}' found on Etsy.")
    return int(results[0]["shop_id"])


def get_shop_profile(client: EtsyClient, shop_id: int) -> dict:
    """GET /shops/{shop_id} — name, title, active count, reviews, sold count."""
    return client.get(f"/shops/{shop_id}")


def get_shop_active_listings(
    client: EtsyClient, shop_id: int, limit: int = 20
) -> list[dict]:
    """Active listings of one shop (paged, Etsy caps 100 per page)."""
    results: list[dict] = []
    offset = 0
    while len(results) < limit:
        page = min(100, limit - len(results))
        data = client.get(
            f"/shops/{shop_id}/listings/active",
            params={"limit": page, "offset": offset},
        )
        batch = data.get("results", []) if isinstance(data, dict) else []
        if not batch:
            break
        results.extend(batch)
        offset += len(batch)
        if len(batch) < page:
            break
    return results[:limit]


def analyze_shop(client: EtsyClient, query: str, limit: int = 20) -> dict:
    """Shop Analyzer — profile + summary + top listings (by Favorites).

    Summary numbers are Etsy's real numbers: active listings,
    review count / average, transaction_sold_count (the shop's total sales),
    num_favorers. The top listings' avg price / total favorites are based
    only on the top listings shown — not the whole shop.
    """
    shop_id = resolve_shop_id(client, query)
    profile = get_shop_profile(client, shop_id)
    listings = get_shop_active_listings(client, shop_id, limit=limit)
    df = listings_to_dataframe(listings)
    summary = {
        "shop_id": shop_id,
        "shop_name": profile.get("shop_name", ""),
        "title": profile.get("title", ""),
        "url": profile.get("url", f"https://www.etsy.com/shop/{profile.get('shop_name', '')}"),
        "active_listings": profile.get("listing_active_count", len(listings)),
        "digital_listings": profile.get("digital_listing_count", ""),
        "review_count": profile.get("review_count", 0),
        "review_average": profile.get("review_average", 0),
        "total_sold": profile.get("transaction_sold_count", 0),
        "shop_favorers": profile.get("num_favorers", 0),
        "country": profile.get("shipping_from_country_iso")
        or profile.get("shop_location_country_iso", ""),
        "currency": profile.get("currency_code", "USD"),
        "avg_price_top": round(float(df["Price"].mean()), 2) if not df.empty else 0.0,
        "total_favorites_top": int(df["Favorites"].sum()) if not df.empty else 0,
        "best_listing": str(df.iloc[0]["Title"]) if not df.empty else "",
    }
    return {"profile": profile, "summary": summary, "top_listings": df}


# ---------------------------------------------------------------------------
# Competitor Tracker — local snapshots, compare with the last one
# ---------------------------------------------------------------------------
def _snapshot_items(listings: list[dict]) -> dict:
    items: dict = {}
    for item in listings:
        lid = item.get("listing_id")
        if not lid:
            continue
        price = item.get("price") or {}
        items[str(lid)] = {
            "title": item.get("title", ""),
            "price": price.get("amount", 0) / 100 if price.get("amount") else 0,
            "favorites": int(item.get("num_favorers") or 0),
            "views": int(item.get("views") or 0),
            "url": f"https://www.etsy.com/listing/{lid}/",
        }
    return items


def load_snapshots() -> list[dict]:
    if not TRACKER_FILE.exists():
        return []
    try:
        data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_snapshot(listings: list[dict], label: str) -> dict:
    """Save today's favourites/views for these listings. Returns the snapshot."""
    label = (label or "tracker").strip() or "tracker"
    snapshot = {
        "label": label,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "items": _snapshot_items(listings),
    }
    snaps = load_snapshots()
    snaps.append(snapshot)
    snaps = snaps[-MAX_SNAPSHOTS_KEPT:]
    TRACKER_FILE.write_text(json.dumps(snaps, indent=2), encoding="utf-8")
    return snapshot


def save_snapshot_for_ids(client: EtsyClient, listing_ids: list[int], label: str) -> dict:
    """Fetch each listing live, then save the snapshot (1 API call per ID)."""
    listings = []
    for lid in listing_ids:
        try:
            listings.append(client.get(f"/listings/{int(lid)}"))
        except Exception:
            continue
    if not listings:
        raise ValueError("No listings found — check the IDs.")
    return save_snapshot(listings, label)


def compare_latest_snapshots(label: str | None = None) -> tuple[pd.DataFrame, str, str]:
    """Compare the last two snapshots (same label if given).

    Returns (delta DataFrame, previous saved_at, latest saved_at).
    Empty DataFrame + empty dates = fewer than 2 snapshots to compare.
    """
    snaps = load_snapshots()
    if label:
        snaps = [s for s in snaps if s.get("label") == label]
    if len(snaps) < 2:
        return pd.DataFrame(), "", ""
    prev, latest = snaps[-2], snaps[-1]
    rows = []
    for lid, cur in latest.get("items", {}).items():
        old = prev.get("items", {}).get(lid)
        rows.append(
            {
                "Listing ID": lid,
                "Title": (cur.get("title", "") or "")[:60],
                "Price": cur.get("price", 0),
                "Favorites": cur.get("favorites", 0),
                "Fav change": cur.get("favorites", 0) - (old.get("favorites", 0) if old else 0),
                "Views": cur.get("views", 0),
                "View change": cur.get("views", 0) - (old.get("views", 0) if old else 0),
                "Status": "New" if old is None else "Tracked",
                "URL": cur.get("url", ""),
            }
        )
    for lid, old in prev.get("items", {}).items():
        if lid not in latest.get("items", {}):
            rows.append(
                {
                    "Listing ID": lid,
                    "Title": (old.get("title", "") or "")[:60],
                    "Price": old.get("price", 0),
                    "Favorites": old.get("favorites", 0),
                    "Fav change": 0,
                    "Views": old.get("views", 0),
                    "View change": 0,
                    "Status": "Gone",
                    "URL": old.get("url", ""),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Fav change", ascending=False).reset_index(drop=True)
    return df, str(prev.get("saved_at", "")), str(latest.get("saved_at", ""))
