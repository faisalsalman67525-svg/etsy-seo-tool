"""SEO Audit for Etsy listings — Etsy 2026 best practice.

Scores a listing 0-100 and says exactly what to fix, in plain words.
No API call needed — it works on the title / tags / description /
photo count you paste in.

Rules (from Etsy's own seller guidance):
- Title <= 140 chars, ideally 100-140, primary keyword in the first 40 chars,
  no filler words, no keyword repeated 3+ times.
- Exactly 13 tags, each <= 20 chars, 2-3 words each (multi-word phrases
  rank for real searches; single words like "paper" are wasted).
- Description: hook + keywords in the first ~160 chars, then what's
  included / sizes / how to use / "digital download — no physical item".
- Photos: 7-10 for a digital product (first photo = cover, not a plain page).
- Price: $5-$20 sweet spot for a single digital product.
"""

WEAK_TAGS = {
    "a4 printable", "letter size", "mixed media", "a5 printable",
    "digital", "printable", "paper", "journal", "art", "craft",
}

KEYWORD_HINTS = [
    "junk journal", "dark academia", "vintage", "ephemera", "scrapbook",
    "gothic", "printable", "instant download", "digital download",
    "planner", "wall art", "stickers", "digital paper",
]


def score_listing(title, tags, description="", photos=0, price=None):
    """Return {'score': 0-100, 'grade': str, 'checks': [...], 'fixes': [...]}."""
    title = (title or "").strip()
    tags = [t.strip().lower() for t in (tags or []) if t.strip()]
    desc = (description or "").strip()
    checks = []

    def add(name, ok, points, max_points, tip=""):
        checks.append({"check": name, "ok": bool(ok),
                       "points": points if ok else 0, "max": max_points,
                       "tip": "" if ok else tip})

    # 1. Title length (15)
    n = len(title)
    add(f"Title length: {n}/140 chars", 100 <= n <= 140, 15, 15,
        f"Make the title 100-140 chars — it is only {n} now, add more keywords."
        if n < 100 else "Title is over 140 chars — shorten it, Etsy will cut it off.")

    # 2. Primary keyword in first 40 chars (10)
    first40 = title[:40].lower()
    hit = any(k in first40 for k in KEYWORD_HINTS)
    add("Primary keyword in the first 40 chars", hit, 10, 10,
        "Put the words buyers search for at the start of the title, "
        "e.g. 'Dark Academia Junk Journal Kit'.")

    # 3. Title not stuffed with the same word 3+ times (5)
    words = [w.strip(",|").lower() for w in title.split()]
    repeated = [w for w in set(words) if words.count(w) >= 3 and len(w) > 3]
    add("No word repeated 3+ times in the title", not repeated, 5, 5,
        "These words repeat too often — Etsy treats that as keyword stuffing: %s" % ", ".join(repeated))

    # 4. Exactly 13 tags (15)
    add(f"Tags: {len(tags)}/13", len(tags) == 13, 15, 15,
        "Use all 13 tags — every empty tag is a lost search.")

    # 5. All tags <= 20 chars (10)
    long_tags = [t for t in tags if len(t) > 20]
    add("Every tag 20 chars or less", not long_tags, 10, 10,
        "These tags are over 20 chars, Etsy will reject them: %s" % ", ".join(long_tags))

    # 6. Tags are multi-word phrases (10)
    multi = [t for t in tags if len(t.split()) >= 2]
    add(f"Multi-word tags: {len(multi)}/{len(tags) or 1}", len(tags) and len(multi) / len(tags) >= 0.8, 10, 10,
        "One-word tags ('paper', 'art') are wasted — use 2-3 word phrases, "
        "e.g. 'junk journal kit'.")

    # 7. No weak / filler tags (5)
    weak = [t for t in tags if t in WEAK_TAGS]
    add("No weak tags (a4 printable, letter size…)", not weak, 5, 5,
        "These tags are weak, replace them with search phrases: %s" % ", ".join(weak))

    # 8. Description long enough (10)
    add(f"Description: {len(desc)} chars", len(desc) >= 500, 10, 10,
        "Make the description at least 500 chars — what's included, sizes, "
        "how to use it, licence.")

    # 9. Keywords in first 160 chars of description (5)
    first160 = desc[:160].lower()
    add("Keywords in the first 160 chars of the description", any(k in first160 for k in KEYWORD_HINTS), 5, 5,
        "Put 'junk journal', 'instant download' in the first 2 lines — "
        "that is what the buyer sees first.")

    # 10. Photos (10)
    add(f"Photos: {photos}", photos >= 7, 10, 10,
        "Use at least 7 photos: cover, inside pages, tags/pockets, finished product. "
        "The first photo must be the cover, not a plain page.")

    # 11. Price in sweet spot (5)
    if price is None:
        add("Price in the $5-$20 range", True, 5, 5)
    else:
        add(f"Price: ${price:.2f}", 5 <= price <= 20, 5, 5,
            "$5-$20 is the best range for a single digital product — above $20 "
            "the first sale is much harder.")

    score = sum(c["points"] for c in checks)
    grade = "Excellent ✅" if score >= 90 else "Good 🙂" if score >= 75 else "Needs work ⚠️" if score >= 60 else "Weak ❌"
    fixes = [c["check"] + " — " + c["tip"] for c in checks if not c["ok"]]
    return {"score": score, "grade": grade, "checks": checks, "fixes": fixes}


def suggest_tags(tags):
    """Replace weak tags with stronger search phrases. Returns new list."""
    replacements = {
        "a4 printable": "scrapbook ephemera",
        "letter size": "gothic ephemera",
        "mixed media": "printable ephemera",
        "a5 printable": "vintage journal",
        "paper": "junk journal paper",
        "art": "dark academia art",
    }
    out = []
    for t in tags:
        out.append(replacements.get(t.strip().lower(), t))
    return out
