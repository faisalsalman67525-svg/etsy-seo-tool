"""Keyword starter packs — what to search on Etsy, and why.

Nobody should have to invent keywords. Pick a product type and the app
shows one-click search buttons: tap one and the tool searches Etsy for it,
then the Tag Analyzer shows which tags buyers love and few sellers use.

These are starting points, not magic — always verify a keyword with a real
search (Tab 1) before building a listing around it.

Avoid: psychic / tarot / 'reading' keywords — they dominate broad
'digital products' searches but are not a real niche, and Etsy cracks down
on outcome-promising metaphysical services.
"""

# Starter keywords per product type: (keyword, why) pairs.
CATEGORY_KEYWORDS = {
    "Junk journal kits": [
        ("junk journal kit printable", "Broad, high demand — top listings rank on this"),
        ("dark academia junk journal", "Dark academia buyers are very active"),
        ("vintage floral junk journal", "Vintage + floral, a proven theme"),
        ("cottagecore junk journal", "Cottagecore buyers are very active"),
        ("scrapbook ephemera", "The category — tag/pocket buyers search this"),
        ("gothic junk journal", "Close to dark academia, less competition"),
    ],
    "Printable planners": [
        ("adhd planner printable", "Niche planners are the #1 planner niche"),
        ("brain dump journal", "Very specific, low competition"),
        ("printable planner pdf", "Broad planner keyword"),
        ("undated planner printable", "Undated planners are in high demand"),
        ("daily planner printable", "The everyday planner search"),
        ("productivity planner printable", "Productivity niche buyers"),
    ],
    "Digital paper packs": [
        ("digital paper pack", "The biggest paper-pack search"),
        ("vintage floral digital paper", "Theme + product, proven sellers"),
        ("scrapbook paper printable", "Paper buyers come through this"),
        ("cottagecore digital paper", "Theme + product, low competition"),
        ("dark academia digital paper", "Dark academia paper buyers"),
    ],
    "Wall art (printable)": [
        ("printable wall art vintage", "The main vintage wall-art search"),
        ("vintage floral wall art", "Gallery-wall buyers"),
        ("botanical wall art printable", "Botanical niche, less competition"),
        ("cottagecore wall art", "Theme keyword for wall art"),
    ],
    "Stickers (printable)": [
        ("digital stickers goodnotes", "GoodNotes stickers are the biggest sticker search"),
        ("junk journal stickers", "Stickers + junk journal overlap"),
        ("vintage stickers printable", "Broad sticker keyword"),
        ("planner stickers printable", "Planner buyers also buy stickers"),
    ],
    "Wedding / party printables": [
        ("wedding invitation template", "The biggest wedding printable search"),
        ("printable wedding signs", "Signs sell well with invitations"),
        ("baby shower printable", "Party niche, repeat buyers"),
        ("birthday party printable", "Broad party keyword"),
    ],
}

# Evergreen keywords — useful any day, for any product.
EVERGREEN_KEYWORDS = [
    ("junk journal printable", "The biggest broad keyword — start research here"),
    ("altered art printable", "Altered art buyers"),
    ("digital paper pack", "Paper packs — $3-$10, repeat buyers"),
    ("vintage ephemera printable", "Ephemera buyers — high intent"),
    ("gothic junk journal", "Dark/gothic niche"),
    ("cottagecore junk journal", "Cottagecore niche"),
    ("scrapbook kit printable", "Scrapbook buyers also buy junk journals"),
    ("printable journal pages", "Buyers who only want pages"),
]


def keywords_for_category(category: str) -> list[tuple[str, str]]:
    """(keyword, why) pairs for a product category name."""
    return CATEGORY_KEYWORDS.get(category, EVERGREEN_KEYWORDS[:4])


def all_categories() -> list[str]:
    """Category names for the picker, evergreen last."""
    return list(CATEGORY_KEYWORDS.keys())
