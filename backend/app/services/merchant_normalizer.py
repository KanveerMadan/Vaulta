"""
Indian Merchant Normalizer — vaulta-normalizer

Regex-based pattern matching for UPI strings, bank narrations, and email subjects
from all major Indian banks. Built as a standalone service so it can be extracted
to a PyPI package (planned: end of Phase 2, after Gmail stress-tests).

Architecture:
  - Pattern matching, NOT dictionary lookup — handles UPI string variations
  - Each pattern returns: (merchant_clean, category, confidence_score 0.0–1.0)
  - Confidence < 0.5 = uncategorized, surfaced to user for correction
  - User corrections feed back into a corrections table (Phase 3)

Coverage target: top 150 Indian merchants across all UPI string formats.
Current coverage: ~120 merchants across Food, Transport, Shopping, Utilities,
Entertainment, Health, Travel, Education, Finance.

Test suite lives in: tests/test_normalizer.py (200+ real UPI strings)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


@dataclass
class NormalizedMerchant:
    merchant_clean: str
    category: str
    confidence: float  # 0.0 – 1.0


# ─────────────────────────────────────────────
# Pattern registry
# Each entry: (regex_pattern, merchant_clean, category, confidence)
# Patterns are tried in ORDER — put more specific patterns BEFORE general ones.
# ─────────────────────────────────────────────

_PATTERNS: List[Tuple[str, str, str, float]] = [

    # ── Food & Dining ────────────────────────────────────────────────────────
    (r"swiggy", "Swiggy", "Food & Dining", 0.97),
    (r"zomato", "Zomato", "Food & Dining", 0.97),
    (r"blinkit|grofers", "Blinkit", "Groceries", 0.96),
    (r"zepto", "Zepto", "Groceries", 0.96),
    (r"dunzo", "Dunzo", "Groceries", 0.93),
    (r"bigbasket|big\s?basket", "BigBasket", "Groceries", 0.96),
    (r"domino.?s|dpz", "Domino's", "Food & Dining", 0.95),
    (r"pizza\s?hut", "Pizza Hut", "Food & Dining", 0.95),
    (r"kfc", "KFC", "Food & Dining", 0.95),
    (r"mcdonald.?s|mcd\b", "McDonald's", "Food & Dining", 0.94),
    (r"subway\b", "Subway", "Food & Dining", 0.94),
    (r"burger\s?king", "Burger King", "Food & Dining", 0.94),
    (r"starbucks", "Starbucks", "Food & Dining", 0.96),
    (r"cafe\s?coffee\s?day|ccd\b", "Cafe Coffee Day", "Food & Dining", 0.93),
    (r"haldiram", "Haldirams", "Food & Dining", 0.93),
    (r"naturals\s?ice\s?cream", "Naturals", "Food & Dining", 0.90),
    (r"barbeque\s?nation|bbn\b", "Barbeque Nation", "Food & Dining", 0.92),
    (r"social\b.*bar|the\s?social", "Social", "Food & Dining", 0.85),
    (r"instamart", "Swiggy Instamart", "Groceries", 0.95),
    (r"d-?mart|avenue\s?super", "DMart", "Groceries", 0.92),
    (r"reliance\s?fresh|reliancefresh", "Reliance Fresh", "Groceries", 0.91),
    (r"more\s?retail|moreretail", "More Retail", "Groceries", 0.88),
    (r"nature.?s\s?basket", "Nature's Basket", "Groceries", 0.90),
    (r"jiomart", "JioMart", "Groceries", 0.93),
    (r"licious", "Licious", "Groceries", 0.92),

    # ── Transport ────────────────────────────────────────────────────────────
    (r"uber\b", "Uber", "Transport", 0.97),
    (r"ola\b|olacabs", "Ola", "Transport", 0.96),
    (r"rapido", "Rapido", "Transport", 0.95),
    (r"namma\s?yatri|yatri", "Namma Yatri", "Transport", 0.90),
    (r"bluSmart|blusmart", "BluSmart", "Transport", 0.92),
    (r"meru\s?cabs?", "Meru Cabs", "Transport", 0.88),
    (r"indian\s?railway|irctc|railways?\s?ticket", "IRCTC", "Travel", 0.96),
    (r"indigo\b|6e\b", "IndiGo", "Travel", 0.95),
    (r"air\s?india\b", "Air India", "Travel", 0.95),
    (r"spicejet", "SpiceJet", "Travel", 0.94),
    (r"go\s?first|go\s?air", "Go First", "Travel", 0.93),
    (r"akasa\s?air", "Akasa Air", "Travel", 0.92),
    (r"vistara", "Vistara", "Travel", 0.94),
    (r"makemytrip|mmt\b", "MakeMyTrip", "Travel", 0.93),
    (r"goibibo", "Goibibo", "Travel", 0.93),
    (r"oyo\b", "OYO", "Travel", 0.92),
    (r"yatra\.com|yatra\b", "Yatra", "Travel", 0.90),
    (r"cleartrip", "Cleartrip", "Travel", 0.91),
    (r"redbus|red\s?bus", "redBus", "Travel", 0.92),
    (r"abhibus", "AbhiBus", "Travel", 0.88),
    (r"paytm\s?travel", "Paytm Travel", "Travel", 0.87),
    (r"petrol|fuel\b|iocl|bpcl|hpcl|hp\s?petro", "Petrol/Fuel", "Transport", 0.88),
    (r"fastag|fas\s?tag", "FASTag", "Transport", 0.90),

    # ── Shopping (E-commerce) ────────────────────────────────────────────────
    (r"amazon(?!\s?web\s?services|\s?aws)", "Amazon", "Shopping", 0.97),
    (r"flipkart", "Flipkart", "Shopping", 0.97),
    (r"myntra", "Myntra", "Shopping", 0.96),
    (r"ajio\b", "Ajio", "Shopping", 0.95),
    (r"nykaa", "Nykaa", "Shopping", 0.95),
    (r"meesho", "Meesho", "Shopping", 0.94),
    (r"snapdeal", "Snapdeal", "Shopping", 0.93),
    (r"shopsy", "Shopsy", "Shopping", 0.92),
    (r"tata\s?cliq|tatacliq", "Tata CLiQ", "Shopping", 0.93),
    (r"croma\b", "Croma", "Shopping", 0.92),
    (r"vijay\s?sales", "Vijay Sales", "Shopping", 0.91),
    (r"reliance\s?digital|rdigital", "Reliance Digital", "Shopping", 0.91),
    (r"lenskart", "Lenskart", "Shopping", 0.93),
    (r"pepperfry", "Pepperfry", "Shopping", 0.92),
    (r"urban\s?ladder", "Urban Ladder", "Shopping", 0.91),
    (r"ikea\b", "IKEA", "Shopping", 0.95),
    (r"firstcry", "FirstCry", "Shopping", 0.93),
    (r"bewakoof", "Bewakoof", "Shopping", 0.91),

    # ── Entertainment ────────────────────────────────────────────────────────
    (r"netflix", "Netflix", "Entertainment", 0.98),
    (r"prime\s?video|amazon\s?prime", "Amazon Prime", "Entertainment", 0.96),
    (r"hotstar|disney\+?\s?hotstar", "Disney+ Hotstar", "Entertainment", 0.96),
    (r"sony\s?liv|sonyliv", "SonyLIV", "Entertainment", 0.95),
    (r"zee5", "ZEE5", "Entertainment", 0.95),
    (r"jio\s?cinema|jiocinema", "JioCinema", "Entertainment", 0.94),
    (r"mx\s?player", "MX Player", "Entertainment", 0.92),
    (r"voot\b", "Voot", "Entertainment", 0.92),
    (r"spotify", "Spotify", "Entertainment", 0.97),
    (r"gaana\b", "Gaana", "Entertainment", 0.93),
    (r"jiosaavn|saavn", "JioSaavn", "Entertainment", 0.93),
    (r"wynk\b", "Wynk Music", "Entertainment", 0.90),
    (r"bookmyshow|bms\b", "BookMyShow", "Entertainment", 0.95),
    (r"pvr\b|pvrcinemas", "PVR Cinemas", "Entertainment", 0.94),
    (r"inox\b", "INOX", "Entertainment", 0.93),
    (r"cinepolis", "Cinepolis", "Entertainment", 0.92),
    (r"youtube\s?premium", "YouTube Premium", "Entertainment", 0.95),

    # ── Utilities & Bills ────────────────────────────────────────────────────
    (r"airtel\b", "Airtel", "Utilities", 0.95),
    (r"jio\b|reliance\s?jio", "Jio", "Utilities", 0.95),
    (r"bsnl\b", "BSNL", "Utilities", 0.93),
    (r"vi\b|vodafone|idea\s?cellular", "Vodafone Idea", "Utilities", 0.93),
    (r"tata\s?play|tataplay|tata\s?sky", "Tata Play", "Utilities", 0.92),
    (r"dish\s?tv|dishtv", "Dish TV", "Utilities", 0.92),
    (r"d2h\b|videocon\s?d2h", "Videocon D2H", "Utilities", 0.90),
    (r"electricity|bescom|msedcl|tpddl|cesc\b|adani\s?electric", "Electricity Bill", "Utilities", 0.88),
    (r"gas\s?bill|indane|bharat\s?gas|hp\s?gas|mahanagar\s?gas|mgl\b", "Gas Bill", "Utilities", 0.87),
    (r"water\s?bill|bwssb|mcgm\s?water", "Water Bill", "Utilities", 0.85),
    (r"broadband|hathway|act\s?fibernet|tikona|spectranet", "Broadband", "Utilities", 0.88),

    # ── Health & Wellness ────────────────────────────────────────────────────
    (r"apollo\s?pharmacy|apollopharmacy", "Apollo Pharmacy", "Health", 0.95),
    (r"medplus|med\s?plus", "MedPlus", "Health", 0.93),
    (r"netmeds", "Netmeds", "Health", 0.94),
    (r"1mg\b|one\s?mg", "1mg", "Health", 0.94),
    (r"practo\b", "Practo", "Health", 0.93),
    (r"pharmeasy", "PharmEasy", "Health", 0.93),
    (r"cult\.fit|curefit|cure\s?fit", "Cult.fit", "Health", 0.93),
    (r"healthifyme", "HealthifyMe", "Health", 0.92),
    (r"portea\b", "Portea", "Health", 0.88),
    (r"lybrate\b", "Lybrate", "Health", 0.87),

    # ── Finance & Insurance ──────────────────────────────────────────────────
    (r"lic\b|life\s?insurance\s?corp", "LIC", "Insurance", 0.93),
    (r"hdfc\s?life|hdfclife", "HDFC Life", "Insurance", 0.92),
    (r"icici\s?prudential|icicipru", "ICICI Prudential", "Insurance", 0.92),
    (r"sbi\s?life", "SBI Life", "Insurance", 0.91),
    (r"bajaj\s?allianz", "Bajaj Allianz", "Insurance", 0.91),
    (r"policy\s?bazar|policybazaar", "Policybazaar", "Finance", 0.92),
    (r"groww\b", "Groww", "Investments", 0.94),
    (r"zerodha|kite\b", "Zerodha", "Investments", 0.94),
    (r"upstox", "Upstox", "Investments", 0.93),
    (r"angel\s?one|angelone|angel\s?broking", "Angel One", "Investments", 0.91),
    (r"coin\b.*zerodha|zerodha.*coin", "Zerodha Coin", "Investments", 0.92),
    (r"cred\b", "CRED", "Finance", 0.92),
    (r"paytm\b", "Paytm", "Finance", 0.88),  # Broad — many Paytm verticals
    (r"phonepe\b", "PhonePe", "Finance", 0.85),
    (r"gpay|google\s?pay", "Google Pay", "Finance", 0.85),
    (r"emi\b|equated\s?monthly", "EMI Payment", "Finance", 0.82),

    # ── Education ────────────────────────────────────────────────────────────
    (r"byju.?s|byjus", "BYJU'S", "Education", 0.94),
    (r"unacademy", "Unacademy", "Education", 0.93),
    (r"vedantu", "Vedantu", "Education", 0.93),
    (r"coursera\b", "Coursera", "Education", 0.94),
    (r"udemy\b", "Udemy", "Education", 0.94),
    (r"simplilearn", "Simplilearn", "Education", 0.92),
    (r"whitehat\s?jr|whitehat", "WhiteHat Jr", "Education", 0.91),

    # ── Government & Taxes ───────────────────────────────────────────────────
    (r"income\s?tax|incometax|tin\s?nsdl", "Income Tax", "Taxes & Government", 0.90),
    (r"gst\b|goods\s?and\s?service\s?tax", "GST Payment", "Taxes & Government", 0.88),
    (r"challan\b|traffic\s?fine|e-challan", "Traffic Challan", "Taxes & Government", 0.85),
    (r"mca\b|ministry\s?of\s?corp", "MCA", "Taxes & Government", 0.83),

    # ── Rent & Housing ───────────────────────────────────────────────────────
    (r"nobroker|no\s?broker", "NoBroker", "Rent & Housing", 0.90),
    (r"rent\b|house\s?rent|monthly\s?rent", "Rent", "Rent & Housing", 0.80),
    (r"maintenance\b|society\s?maintenance|apartment.*maintenance", "Maintenance", "Rent & Housing", 0.78),
    (r"magicbricks", "Magicbricks", "Rent & Housing", 0.85),
    (r"99acres", "99acres", "Rent & Housing", 0.85),

    # ── AWS/Cloud (avoid collision with Amazon shopping) ─────────────────────
    (r"amazon\s?web\s?services|aws\b", "AWS", "Software & Cloud", 0.96),
    (r"google\s?cloud|gcp\b", "Google Cloud", "Software & Cloud", 0.95),
    (r"microsoft\s?azure|azure\b", "Microsoft Azure", "Software & Cloud", 0.95),
    (r"digitalocean", "DigitalOcean", "Software & Cloud", 0.93),
    (r"github\b", "GitHub", "Software & Cloud", 0.93),
    (r"atlassian|jira\b|confluence", "Atlassian", "Software & Cloud", 0.91),
    (r"notion\b", "Notion", "Software & Cloud", 0.92),
    (r"slack\b", "Slack", "Software & Cloud", 0.92),
    (r"zoom\b", "Zoom", "Software & Cloud", 0.92),
    (r"figma\b", "Figma", "Software & Cloud", 0.91),
]

# Compile all patterns once at module load — not on every call
_COMPILED_PATTERNS: List[Tuple[re.Pattern, str, str, float]] = [
    (re.compile(pattern, re.IGNORECASE), merchant, category, confidence)
    for pattern, merchant, category, confidence in _PATTERNS
]

# Known UPI noise prefixes to strip before matching
_UPI_NOISE = re.compile(
    r"^(upi|neft|imps|rtgs|nach|ecs|ach|pos|atm|trf|transfer|payment|pay|to|from|"
    r"debit|credit|dr|cr|rec|ref|txn|transaction|order|purchase|bill|sub|subscription|"
    r"auto|mandate|emandate|standing\s?instruction|si\b)\s*[-/:*|#@]?\s*",
    re.IGNORECASE,
)

# UPI ID suffix patterns to strip: "@ibl", "@oksbi", "@paytm", etc.
_UPI_SUFFIX = re.compile(r"\*[A-Z0-9]+@[a-z]+|@[a-z]+\.[a-z]+|@[a-z]+", re.IGNORECASE)


def _clean_raw(raw: str) -> str:
    """Strip UPI boilerplate to expose the merchant-relevant portion."""
    cleaned = _UPI_SUFFIX.sub("", raw)
    cleaned = _UPI_NOISE.sub("", cleaned)
    return cleaned.strip()


def normalize(merchant_raw: str) -> NormalizedMerchant:
    """
    Normalize a raw merchant string from any Indian bank into a clean
    merchant name, category, and confidence score.

    Args:
        merchant_raw: Raw string from bank CSV/SMS/email
                      (e.g., "SWIGGY*ORDER123@ibl", "UPI-ZOMATO-ZOMATO@hdfcbank")

    Returns:
        NormalizedMerchant with merchant_clean, category, confidence.
        If no pattern matches, returns category="Uncategorized" with confidence=0.0.
    """
    if not merchant_raw or not merchant_raw.strip():
        return NormalizedMerchant(
            merchant_clean=merchant_raw or "Unknown",
            category="Uncategorized",
            confidence=0.0,
        )

    cleaned = _clean_raw(merchant_raw)

    # Try patterns against both cleaned and raw (some patterns need full context)
    for compiled_pattern, merchant_clean, category, confidence in _COMPILED_PATTERNS:
        if compiled_pattern.search(cleaned) or compiled_pattern.search(merchant_raw):
            return NormalizedMerchant(
                merchant_clean=merchant_clean,
                category=category,
                confidence=confidence,
            )

    # No match — return cleaned string as best-effort, flagged for user review
    return NormalizedMerchant(
        merchant_clean=cleaned if cleaned else merchant_raw,
        category="Uncategorized",
        confidence=0.0,
    )


def normalize_batch(merchant_raws: list[str]) -> list[NormalizedMerchant]:
    """Normalize a list of raw merchant strings."""
    return [normalize(raw) for raw in merchant_raws]