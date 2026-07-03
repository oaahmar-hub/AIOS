#!/usr/bin/env python3
"""AIOS Unit Finder Step 8: multi-signal listing similarity matcher."""

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse
import sqlite3
from functools import lru_cache


KB = Path("/Users/hassanka/Downloads/AIOS/KnowledgeBase")
RESOLVER_DIR = KB / "resolver"
DB_PATH = RESOLVER_DIR / "unit_resolver_database.sqlite"
LISTING_IDENTITY_JSON = RESOLVER_DIR / "listing_identity_map.json"
LISTING_IDENTITY_CSV = RESOLVER_DIR / "listing_identity_map.csv"
INDEX_CSV = RESOLVER_DIR / "unit_resolver_index.csv"
OUT_CSV = RESOLVER_DIR / "listing_similarity_candidates.csv"
OUT_REPORT = RESOLVER_DIR / "listing_similarity_test_report.md"
RAW_DATA_DIR = KB / "raw_data" / "csv"
OMAR_STYLE_CSV = RAW_DATA_DIR / "5ca554ad55ac__omar_style_dataset_sample.csv"
_PREPARED_RECORD_CACHE = None
_CANDIDATE_INDEX_CACHE = {}

PLATFORM_RE = re.compile(r"(propertyfinder\.ae|bayut\.com|dubizzle\.com)", re.I)
URL_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:propertyfinder\.ae|bayut\.com|dubizzle\.com)[^\s\"'<>)]+", re.I)
NUMBER_RE = re.compile(r"\d+")
SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(sqm|sq\s?ft|sq\.?\s*ft|sqft|sq\. ?m|m2|m²)", re.I)
PRICE_RE = re.compile(r"([0-9][0-9,\.\-]*)(?:\s*(?:aed|aed/mo|aed/year|aed\s+/\s+month|aed\s+/\s+year|usd|dirham|dhs|aed/year|aed/mo|aed\s+month|aed\s+year))?", re.I)
PRICE_CURRENCY_HINTS = re.compile(r"\b(?:ask|asking|price|rent|rental|sale|aed|aed/mo|aed/year|aed\s+month|aed\s+year|usd|usd/mo|dhs|dirham|dirhams)\b", re.I)
PRICE_SCALE_RE = re.compile(r"(?:\s+|^)\(?\s*([0-9][0-9,.]*)\s*(m|mn|million|k|thousand|b|bn|billion)\b", re.I)
IDENT_RE = {
    "permit_number": [r"(?:permit|rera|trakheesi|advertisement permit|brn|orn)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{4,40})", r"\b(?:permit)\s*([0-9]{5,20})\b"],
    "property_number": [r"(?:property|property no|property number|property id)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{3,40})", r"\b(?:prop(?:erty)?)[\s_-]?([0-9]{3,20})\b"],
    "plot_number": [r"(?:plot|plot no|plot number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})"],
    "land_number": [r"(?:land|land no|land number)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})"],
    "municipality_number": [r"(?:municipality|municipality no|municipality number|dm no)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})"],
    "dewa_number": [r"(?:dewa|dewa premise|premise)\s*(?:no\.?|number|#|:)?\s*([A-Z0-9/-]{2,40})"],
}

BED_RE = re.compile(r"\b(studio|\d+)\s*(?:br|bed|beds|bedroom|bedrooms|b)\b", re.I)
STATUS_KEYWORDS = ("furnished", "unfurnished", "upgraded", "refurbished", "vacant")
PROPERTY_TYPES = ("apartment", "villa", "studio", "office", "duplex", "penthouse", "townhouse", "flat")
PLATFORM_RESTRICTED_TOKENS = {"listing", "plp", "go", "en", "properties", "property", "details", "new", "projects", "project"}
AREA_HINTS = {
    "JVC": ["jvc", "jumeirah village circle"],
    "JVT": ["jvt", "jumeirah village triangle"],
    "Dubai Hills": ["dubai hills", "dubai hills estate"],
    "Downtown": ["downtown", "downtown dubai"],
    "Business Bay": ["business bay", "bussiness bay", "bussines bay"],
    "Dubai Marina": ["dubai marina", "marina"],
    "Meydan": ["meydan", "midan", "maidan"],
    "Al Furjan": ["al furjan", "furjan"],
    "Palm Jumeirah": ["palm jumeirah", "palm", "pj-p-vp"],
    "Dubai South": ["dubai south"],
    "JLT": ["jlt", "jumeirah lake towers"],
    "JBR": ["jbr", "jumeirah beach residence"],
    "The Greens": ["the greens", "greens"],
    "Creek Harbour": ["creek harbour", "creek harbor", "dubai creek harbour", "dubai creek harbor"],
    "MBR City": ["mbr city", "mbr", "mohammed bin rashid city", "mohammed bin rashid"],
    "Arjan": ["arjan"],
    "Emaar South": ["emaar south"],
    "Town Square": ["town square", "townsq", "mbr town square", "townsquare"],
    "Dubai Islands": ["dubai islands", "islands"],
    "Sobha Hartland": ["sobha hartland", "hartland"],
    "Yas Island": ["yas island"],
    "Saadiyat": ["saadiyat"],
    "Reem Island": ["reem island", "al reem"],
    "Al Raha": ["al raha"],
    "Abu Dhabi": ["abu dhabi", "abu dhabi city"],
    "Sharjah": ["sharjah"],
    "Ajman": ["ajman"],
    "Ras Al Khaimah": ["ras al khaimah", "rak"],
}
PROJECT_HINTS = {
    "Binghatti": ["binghatti", "binghati"],
    "Deyaar": ["deyaar", "deyar"],
    "Oceana": ["oceana", "oceana by reportage"],
    "Tiger": ["tiger"],
    "Reportage": ["reportage"],
}
KNOWN_PROPERTY_TEXT_PATTERNS = (
    "bed",
    "bath",
    "sqft",
    "sqm",
    "aed",
    "price",
    "asking",
    "vacant",
    "studio",
    "apartment",
    "villa",
    "unit",
    "floor",
    "building",
)
TEXT_NOISE = {"and", "the", "for", "of", "to", "in", "is", "on", "a", "an", "at", "buy", "rent", "lease", "new", "resale", "apartment", "villa", "studio", "property", "house", "building"}
SLUG_NOISE = {"en", "plp", "go", "new", "projects", "project", "properties", "property", "propertyfinder", "bayut", "dubizzle", "www", "ae", "html", "htm", "sell", "rent", "lease", "sale", "buy", "for", "apartment", "villa", "studio", "flat", "office", "penthouse", "duplex"}
BUILDING_HINTS = ("tower", "building", "residence", "residences", "gardens", "park", "bay", "plaza", "heights", "village")
AREA_KEYWORDS = set()
for aliases in AREA_HINTS.values():
    for alias in aliases:
        if alias:
            AREA_KEYWORDS.update([t for t in re.split(r"[^a-z0-9]+", alias.lower()) if t])
AREA_KEYWORDS.update({"dubai", "abu", "dhabi"})
AREA_ALIAS_NOISE_TOKENS = {
    "community",
    "pool",
    "middle",
    "street",
    "corner",
    "availability",
    "list",
    "listings",
    "area",
    "city",
    "zones",
    "zone",
    "project",
}
ALLOWED_AREA_CANONS = {str(k).strip().lower() for k in AREA_HINTS}
FIELDNAMES = [
    "test_label",
    "rank",
    "resolver_record_id",
    "area",
    "project",
    "building",
    "unit",
    "bedrooms",
    "size",
    "price",
    "permit_number",
    "property_number",
    "plot_number",
    "land_number",
    "source_file",
    "source_sheet",
    "row_number",
    "source_platform",
    "listing_url",
    "score",
    "score_breakdown",
    "confidence",
    "status_label",
    "owner_contact_available",
    "input",
    "parsed_platform",
    "parsed_listing_id",
    "parsed_area",
    "parsed_project",
    "parsed_building",
    "parsed_bedrooms",
    "parsed_size",
    "parsed_price",
]


def norm(value):
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip())


def low(value):
    return norm(value).lower()


def tokenize(text):
    return [t for t in re.split(r"[^a-z0-9]+", low(text)) if t]


def token_sig(value):
    return " ".join(tokenize(value))


def strip_url_protocol(url):
    if not url:
        return ""
    u = norm(url).strip(".").strip(")")
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        return u
    return "https://" + u


def parse_platform(url):
    m = PLATFORM_RE.search(url or "")
    return m.group(1).lower() if m else ""


def parse_listing_id(url):
    if not url:
        return ""
    u = strip_url_protocol(url)
    parsed = urlparse(u)
    query = low(parsed.query)
    for key in ("listing_id", "listingId", "id", "itemId", "item_id", "pid"):
        m = re.search(rf"{key}=([A-Za-z0-9][A-Za-z0-9_-]{{3,}})", query, re.I)
        if m:
            return m.group(1)
    # PF often keeps id in final slug token
    segment = re.sub(r"\.(html?|htm)$", "", parsed.path.split("/")[-1], flags=re.I)
    if segment:
        for tok in reversed([t for t in re.split(r"[^a-zA-Z0-9]+", segment) if t]):
            cleaned = tok.strip("-_")
            if cleaned.isdigit() and len(cleaned) >= 5:
                return cleaned
            if len(cleaned) >= 6 and any(ch.isdigit() for ch in cleaned) and any(ch.isalpha() for ch in cleaned):
                return cleaned
    # fallback: highest-number token in full path/query
    digits = NUMBER_RE.findall(f"{parsed.path} {query}")
    return digits[-1] if digits else ""


def load_alias_map(json_path: Path, max_words=5, max_len=55):
    if not json_path.exists():
        return {}
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for canon, aliases in data.items():
        if not isinstance(canon, str) or not canon.strip():
            continue
        canon_n = norm(canon)
        if len(canon_n) > max_len:
            continue
        words = canon_n.split()
        if len(words) > max_words:
            continue
        if any(not tok or tok in {"https", "www", "propertyfinder", "bayut", "dubizzle"} for tok in words):
            continue
        lst = []
        if isinstance(aliases, list):
            for v in aliases:
                if isinstance(v, str):
                    vv = norm(v)
                    if len(vv) <= max_len and len(vv) >= 2:
                        lst.append(vv.lower())
        lst.append(canon_n.lower())
        out[canon_n] = sorted(set(lst))
    return out


AREA_ALIAS_MAP = load_alias_map(RESOLVER_DIR / "area_aliases.json")
PROJECT_ALIAS_MAP = load_alias_map(RESOLVER_DIR / "project_aliases.json")
BUILDING_ALIAS_MAP = load_alias_map(RESOLVER_DIR / "building_aliases.json", max_words=10, max_len=120)
AREA_ALIAS_CANDIDATES = [
    (canon, alias)
    for canon, aliases in AREA_ALIAS_MAP.items()
    for alias in aliases
    if low(canon) in ALLOWED_AREA_CANONS
    and not any(tok in low(canon).split() for tok in AREA_ALIAS_NOISE_TOKENS)
    and alias
    and not any(tok in alias for tok in AREA_ALIAS_NOISE_TOKENS)
]
AREA_ALIAS_DIRECT = {
    alias: canon
    for canon, alias in AREA_ALIAS_CANDIDATES
}
AREA_HINT_DIRECT = {
    alias: canon
    for canon, aliases in AREA_HINTS.items()
    for alias in aliases
    if alias
}
AREA_PHRASE_DIRECT = {
    alias: canon
    for canon, aliases in AREA_HINTS.items()
    for alias in aliases
    if alias and len(tokenize(alias)) >= 2
}


def canonical_from_alias(value, hints, alias_map):
    text = low(value)
    if not text:
        return ""
    # strong hints first
    for canon, aliases in hints.items():
        for alias in aliases:
            if alias and alias in text:
                return canon
    # curated alias map fallback
    for canon, aliases in alias_map.items():
        for alias in aliases:
            if alias and alias in text:
                return canon
    return ""


def is_id_like_token(token):
    tok = low(token)
    if not tok:
        return False
    if tok.isdigit():
        return len(tok) >= 5
    if any(ch.isdigit() for ch in tok) and len(tok) >= 6 and any(ch.isalpha() for ch in tok):
        return True
    return False


@lru_cache(maxsize=200000)
def canonical_area(value):
    text = low(value)
    if not text:
        return ""

    # strong hint dictionary first
    for alias, canon in AREA_HINT_DIRECT.items():
        if alias and alias in text:
            return canon

    # curated alias fallback only when canonical name is on the allowed area whitelist
    for alias, canon in AREA_ALIAS_DIRECT.items():
        if alias in text:
            return canon

    # phrase match fallback for inputs like "dubai marina"
    parts = tokenize(text)
    if len(parts) >= 2:
        for window in range(2, min(len(parts), 5) + 1):
            for i in range(len(parts) - window + 1):
                window_text = " ".join(parts[i : i + window])
                if window_text in AREA_PHRASE_DIRECT:
                    return AREA_PHRASE_DIRECT[window_text]

    return ""


def canonical_project(value):
    text = low(value)
    if not text:
        return ""
    for canon, aliases in PROJECT_HINTS.items():
        for alias in aliases:
            if alias and alias in text:
                return canon
    for canon, aliases in PROJECT_ALIAS_MAP.items():
        canon_words = canon.lower().split()
        if len(canon_words) > 8:
            continue
        if canon.lower() in AREA_ALIAS_NOISE_TOKENS or all(w in AREA_ALIAS_NOISE_TOKENS for w in canon_words):
            continue
        if any(w in ALLOWED_AREA_CANONS for w in canon_words):
            continue
        for alias in aliases:
            if not alias:
                continue
            if any(tok in alias for tok in AREA_ALIAS_NOISE_TOKENS):
                continue
            if alias in text:
                return canon
    return ""


def canonical_building(value):
    text = norm(value)
    if not text:
        return ""
    # keep short/clean phrases; do not attempt unsafe aliasing on polluted maps
    clean = re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]+", " ", text)).strip().strip("-")
    clean = re.sub(r"\b(?:the|a|an)\b", "", f" {clean} ", flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()
    clean_tokens = tokenize(clean)
    if not clean_tokens:
        return ""

    # remove area-like trailing phrases that got merged into building fields
    merged_area_phrases = []
    for _, aliases in AREA_HINTS.items():
        for alias in aliases:
            if alias:
                merged_area_phrases.append(tokenize(alias))

    # remove exact phrase matches and obvious location tokens
    for phrase in merged_area_phrases:
        if len(phrase) < 2:
            continue
        for i in range(len(clean_tokens) - len(phrase), -1, -1):
            if clean_tokens[i : i + len(phrase)] == phrase:
                clean_tokens = clean_tokens[:i] + clean_tokens[i + len(phrase) :]

    # remove leading area tokens that may have stuck to names
    while clean_tokens and clean_tokens[0] in AREA_KEYWORDS:
        clean_tokens = clean_tokens[1:]

    # strip short trailing noise
    while clean_tokens and (clean_tokens[-1].isdigit() or clean_tokens[-1] in AREA_KEYWORDS):
        if clean_tokens[-1].isdigit() and len(clean_tokens[-1]) <= 3:
            clean_tokens = clean_tokens[:-1]
        elif clean_tokens[-1] in AREA_KEYWORDS and len(clean_tokens) > 1:
            clean_tokens = clean_tokens[:-1]
        else:
            break
    clean = " ".join(clean_tokens).strip()

    # remove generic tokens that are likely slug noise
    if clean.lower() in TEXT_NOISE:
        return ""
    clean = re.sub(r"\b(?:buy|rent|for|sale|new|used|ready|off-plan|offplan|lease)\b", " ", clean, flags=re.I)
    clean = re.sub(r"\s+", " ", clean).strip()

    if clean.lower() in TEXT_NOISE:
        return ""
    m = re.match(r"(.+?)\s+(?:tower|building|unit|apt|apartment)$", clean, re.I)
    if m:
        return norm(m.group(1))
    if clean.lower() in TEXT_NOISE:
        return ""
    tokens = clean.split()
    stop_words = {
        "bed",
        "beds",
        "bedroom",
        "bedrooms",
        "br",
        "bath",
        "baths",
        "bathroom",
        "bathrooms",
        "sqft",
        "sq",
        "ft",
        "sqm",
        "m",
        "m2",
        "asking",
        "price",
        "aed",
        "dhs",
        "dirham",
        "dirhams",
        "size",
        "rent",
        "for",
        "sale",
        "buy",
        "fully",
        "semi",
        "open",
        "kitchen",
        "view",
        "vacant",
        "furnished",
        "unfurnished",
        "upgraded",
        "refurbished",
    }
    if any(t in stop_words for t in tokens):
        cut = len(tokens)
        for i, tok in enumerate(tokens):
            if tok in stop_words or re.fullmatch(r"(?:studio|\d+)\s*(?:br|bed|beds|bedroom|bath|baths|bathroom)s?", tok):
                cut = i
                break
        if cut > 0:
            clean = " ".join(tokens[:cut])
            if not clean:
                return ""
    clean = re.sub(r"\b(?:studio|\d+)\s*(?:br|bed|beds|bedroom|bath|baths|bathroom)s?\b.*$", "", clean, flags=re.I).strip()
    clean = re.sub(r"\b(?:sq\.?\s*ft|sqft|sqm|m2|m²|aed|dhs|asking|price|size)\b.*$", "", clean, flags=re.I).strip()
    clean_tokens = clean.split()
    while clean_tokens and (clean_tokens[-1].isdigit() and len(clean_tokens[-1]) <= 3 or clean_tokens[-1] in AREA_KEYWORDS):
        clean_tokens = clean_tokens[:-1]
    if len(clean_tokens) >= 2 and clean_tokens[-1] == clean_tokens[-2]:
        clean_tokens = clean_tokens[:-1]
    clean = " ".join(clean_tokens).strip()
    return clean[:180]


def canonical_property_type(value):
    if not value:
        return ""
    text = low(value)
    if re.search(r"\b\d+\s*(?:bed|beds|bedroom|bedrooms|br)\b", text):
        return "apartment"
    for t in PROPERTY_TYPES:
        if re.search(rf"\b{re.escape(t)}\b", text):
            return t
    if re.search(r"\bstudio\b", text):
        return "studio"
    return ""


def normalize_url(value):
    url = norm(value)
    if not url:
        return ""
    return re.sub(r"\.+$", "", url.strip())


def canonical_bedrooms(value):
    if not value:
        return ""
    text = low(value)
    if text.isdigit():
        return text
    if "studio" in text:
        return "studio"
    m = BED_RE.search(text)
    return m.group(1) if m else ""


def _clean_similarity_text(value):
    text = norm(value)
    if not text:
        return ""
    text = low(text)
    text = re.sub(r"https?://\S+", " ", text)
    tokens = [t for t in tokenize(text) if t not in {"en", "plp", "html", "htm", "go", "www", "propertyfinder", "bayut", "dubizzle", "dubai", "buy", "rent", "lease", "sale", "property", "for", "a", "an", "the", "on", "in", "at"}]
    return " ".join(tokens).strip()


def normalize_size_to_sqm(value):
    if not value:
        return ""
    m = SIZE_RE.search(low(value).replace(",", ""))
    if not m:
        return ""
    n = float(m.group(1))
    unit = m.group(2).replace(" ", "")
    return round(n * 0.092903, 2) if "ft" in unit else round(n, 2)


def parse_size_value(value):
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return ""
    if not value:
        return ""
    s = low(value).replace(",", "")
    m = SIZE_RE.search(s)
    if not m:
        return ""
    return normalize_size_to_sqm(value)


def _parse_price_candidates(value):
    if not value:
        return []
    text = low(value).replace(",", "")
    candidates = []

    # multiplier-based prices ("3 M", "2.5 million", "450k" style)
    for raw, scale in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(m|mn|million|k|thousand|b|bn|billion)\b", text, flags=re.I):
        try:
            base = float(raw)
        except Exception:
            continue
        s = scale.lower()
        if s in {"m", "mn", "million"}:
            base *= 1_000_000
        elif s in {"b", "bn", "billion"}:
            base *= 1_000_000_000
        elif s in {"k", "thousand"}:
            base *= 1000
        candidates.append(base)

    # currency before value ("AED 785000", "Dhs 90k" style)
    for raw, scale in re.findall(
        r"\b(?:aed|usd|dhs|dirham|dirhams|dh)\s*([0-9]+(?:\.[0-9]+)?)\s*(m|mn|million|k|thousand|b|bn|billion)?\b",
        text,
        flags=re.I,
    ):
        try:
            base = float(raw)
        except Exception:
            continue
        if scale:
            s = scale.lower()
            if s in {"m", "mn", "million"}:
                base *= 1_000_000
            elif s in {"b", "bn", "billion"}:
                base *= 1_000_000_000
            elif s in {"k", "thousand"}:
                base *= 1000
        candidates.append(base)

    # direct currency values and hinted monetary strings
    for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)\s*(?:[,-]?\s*)?(?:aed|aed/mo|aed\s*/\s*month|aed\s*/\s*year|usd|dhs|dirham|dh|aed/mo|aed\s+month|aed\s+year|aed\s+mo|aed\s+yr)\b", text):
        try:
            candidates.append(float(m.group(1)))
        except Exception:
            pass

    for m in PRICE_RE.finditer(text):
        value = m.group(1)
        if not value:
            continue
        idx = m.start(1)
        ctx = text[max(0, idx - 40): idx + 40]
        if not PRICE_CURRENCY_HINTS.search(ctx):
            continue
        if re.search(rf"\b{re.escape(value)}\s*(?:br|bed|beds|bedroom|bath|baths|bathroom|sq\.?\s*ft|sqft|sqm|m2|m²)\b", ctx):
            continue
        try:
            candidates.append(float(value))
        except Exception:
            pass

    return candidates


def parse_price_value(value):
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return ""
    if not value:
        return ""
    candidates = _parse_price_candidates(value)
    if not candidates:
        text = low(value).replace(",", "")
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
            try:
                return float(text)
            except Exception:
                return ""
        return ""
    return max(candidates)


def normalize_unit(value):
    if not value:
        return ""
    t = norm(value).upper()
    if t.lower() in {"na", "n/a", "none", "null", "-"}:
        return ""
    m = re.search(r"\b(?:unit|apt|apartment|flat|villa)\s*(?:no\.?|#|number|num)?\s*([A-Za-z0-9-]+)\b", low(t), re.I)
    return (m.group(1).upper() if m else re.sub(r"[^A-Z0-9-]", "", t)).strip("-")


def extract_identifiers(text):
    out = {}
    t = low(text)
    for key, patterns in IDENT_RE.items():
        vals = []
        for pat in patterns:
            vals.extend([m.group(1).strip() for m in re.finditer(pat, t)])
        # keep first deterministic id
        for v in vals:
            if v and v.lower() not in {"na", "none", "null"}:
                out[key] = v
                break
    return out


def clean_slug_tokens(tokens):
    cleaned = []
    for tok in tokens:
        if not tok:
            continue
        if tok in SLUG_NOISE:
            continue
        if tok.isdigit() and len(tok) > 1:
            # keep short digits in cases like floors/units only when needed later
            continue
        cleaned.append(tok)
    return cleaned


def parse_area_project_building_from_slug(tokens, area_hint):
    candidate = [t for t in clean_slug_tokens(tokens)]
    # remove platform/date prefix and id-like tail tokens
    while candidate and is_id_like_token(candidate[-1]):
        candidate = candidate[:-1]

    area = canonical_area(" ".join(candidate))
    if not area:
        area = canonical_area(area_hint)
    area_tokens = tokenize(area)
    working = list(candidate)
    if area_tokens:
        # remove first matching area token sequence from working tokens
        for i in range(len(working) - len(area_tokens), -1, -1):
            if working[i : i + len(area_tokens)] == area_tokens:
                working = working[:i] + working[i + len(area_tokens) :]
                break

    # remove duplicated city prefix fragments after area removal
    for token in ("dubai", "abu", "dhabi", "sharjah"):
        while token in working:
            working.remove(token)
    # remove transaction/style words from project building tail
    for token in ("buy", "rent", "lease", "sale", "for", "apartment", "villa", "studio", "flat", "office", "penthouse", "duplex"):
        working = [t for t in working if t != token]

    # remove generic numeric/unit style values from project/building extraction
    working = [t for t in working if t and not t.isdigit() and t not in {"area", "project", "building"}]

    project_raw = " ".join(working)
    project = canonical_project(project_raw)
    if not project:
        project = project_raw if len(project_raw) <= 100 else project_raw[:100]

    # building candidate from remaining tail
    # for typical slug form area + project_name + building_name, prefer trailing 2-4 tokens as building
    building = ""
    if working:
        for span in range(4, 1, -1):
            if len(working) >= span:
                tail = " ".join(working[-span:])
                if canonical_project(tail) and canonical_project(tail) != project:
                    continue
                building = tail
                break
        if not building:
            building = " ".join(working[-3:]) if len(working) >= 3 else " ".join(working)
    building = canonical_building(building)
    return {
        "area": area,
        "project": project,
        "building": building,
    }


def derive_fields_from_text_blob(text):
    tokens = tokenize(text)
    if not tokens:
        return {"area": "", "project": "", "building": ""}

    candidate = [t for t in tokens if t not in PLATFORM_RESTRICTED_TOKENS and t not in PROPERTY_TYPES and t not in SLUG_NOISE]
    if not candidate:
        candidate = list(tokens)

    # infer area first
    area = canonical_area(" ".join(candidate))
    if not area:
        # a direct two-word prefix can include "dubai <community>".
        # preserve ordering and test both prefix and full combinations.
        for i in range(min(4, len(candidate)), 0, -1):
            area_guess = canonical_area(" ".join(candidate[:i]))
            if area_guess:
                area = area_guess
                break

    working = list(candidate)
    area_tokens = tokenize(area)
    if area_tokens:
        # remove a likely area token sequence
        for i in range(len(working) - len(area_tokens), -1, -1):
            if working[i : i + len(area_tokens)] == area_tokens:
                working = working[:i] + working[i + len(area_tokens) :]
                break

    # trim obvious filler
    for tok in ("dubai", "uae", "abu", "dhabi", "sharjah", "emirates", "arab", "emirate", "new", "projects", "project", "plp", "listing"):
        while tok in working:
            working = [t for t in working if t != tok]

    # remove short ids/tokens that came from pagination/hash strings
    working = [t for t in working if not is_id_like_token(t) and not t.startswith("http")]
    # avoid token-only slugs where only one word repeats
    project = canonical_project(" ".join(working))
    if not project:
        project = ""

    # building hints are usually at the tail and include building keywords.
    building = ""
    if working:
        # prefer trailing window that contains a hint keyword
        for span in range(min(6, len(working)), 2, -1):
            tail = working[-span:]
            if any(token in BUILDING_HINTS for token in tail):
                building = " ".join(tail)
                break
        if not building:
            # otherwise keep trailing 2-4 tokens as a candidate building phrase
            building = " ".join(working[-min(4, len(working)) :])

    if not project and building:
        # if we could not separate project/building, retain whichever is strongest
        project = canonical_project(building)

    return {
        "area": canonical_area(area),
        "project": canonical_project(project),
        "building": canonical_building(building),
    }


def parse_url_fields(url):
    u = strip_url_protocol(url)
    parsed = urlparse(u)
    path = parsed.path.lower().strip("/")
    tokens = tokenize(path)

    listing_id = parse_listing_id(u)
    area_hint = ""
    for idx in range(len(tokens)):
        if tokens[idx] == "dubai":
            # prefer "dubai x" as a community hint when present in path tokens
            if idx + 1 < len(tokens):
                maybe = f"dubai {tokens[idx + 1]}"
                if canonical_area(maybe):
                    area_hint = maybe
                    break
            area_hint = "dubai"
            break

    q = parse_area_project_building_from_slug(tokens, area_hint)
    area = q["area"]
    project = q["project"]
    building = q["building"]

    # transaction / property type
    transaction = ""
    for t in tokens:
        if t in {"buy", "rent", "lease", "resale"}:
            transaction = t
            break
    property_type = ""
    for t in tokens:
        if t in {"apartment", "villa", "studio", "office", "duplex", "penthouse", "townhouse", "flat"}:
            property_type = t
            break

    # try extra parse from token sequence for explicit project/building patterns
    if not building and project:
        building = project
    if not project and not building and area and area in q["project"]:
        project = area

    # status is usually not derivable from URL
    status_tokens = []
    numbers = extract_identifiers(u)
    return {
        "input_type": "url",
        "source": "url",
        "source_platform": parse_platform(u),
        "platform": parse_platform(u),
        "listing_url": u,
        "listing_id": listing_id,
        "transaction": transaction,
        "property_type": property_type,
        "area": area,
        "project": canonical_project(project),
        "building": canonical_building(building),
        "unit": "",
        "bedrooms": "",
        "size": "",
        "price": "",
        "slug_title_tokens": " ".join(tokens),
        "status_tokens": " ".join([k for k in STATUS_KEYWORDS if k in low(u)]),
        "query_text": " ".join(tokens),
        **numbers,
    }


def parse_text_fields(text):
    qtext = norm(text)
    lower = low(qtext)
    transaction = ""
    for tok in ("buy", "rent", "lease"):
        if tok in lower:
            transaction = tok
            break
    property_type = canonical_property_type(lower)

    area = canonical_area(lower)
    # project extraction from canonical hints first; fall back to area + next tokens
    project = canonical_project(lower)
    if not project:
        # simple pattern for "Project Name in ..." style
        m = re.search(r"in\s+([^,;\n]+)", lower)
        if m:
            project = canonical_project(m.group(1))
    building = ""
    if area:
        # remove area words and keep next strongest phrase as project/building
        rem = " ".join([t for t in tokenize(lower) if t not in tokenize(area)])
        cand = canonical_building(rem)
        # Prefer concise building-name-first match for noisy marketing text
        if cand:
            b = canonical_building(rem[:120])
            if b and not b.lower() in cand.lower():
                cand = b
        if cand and ("bed" in cand.lower() or "bath" in cand.lower() or "asking" in cand.lower() or "sqft" in cand.lower()):
            cand = ""
        if cand:
            building = cand
    if not building:
        m = re.search(r"\b([a-z][a-z0-9\s&-]{2,40}?\s+(?:tower|heights|residence|residences|gardens|plaza|bay|centre|park|village)\b)", lower)
        building = canonical_building(m.group(1) if m else "")

    ids = extract_identifiers(lower)
    size = parse_size_value(lower)
    price = parse_price_value(lower)
    s = ""
    if size not in {"", None}:
        s = f"{size} sqm"
    p = ""
    if price not in {"", None}:
        p = f"{price}"
    bed_match = BED_RE.search(lower)
    bedrooms = bed_match.group(1) if bed_match else ""

    return {
        "input_type": "text",
        "source": "text",
        "source_platform": "",
        "platform": "",
        "listing_url": "",
        "listing_id": "",
        "slug_title_tokens": qtext,
        "transaction": transaction,
        "property_type": property_type,
        "area": area,
        "project": project or "",
        "building": building or "",
        "unit": "",
        "bedrooms": bedrooms,
        "size": s,
        "price": p,
        "status_tokens": " ".join([k for k in STATUS_KEYWORDS if k in lower]),
        "query_text": qtext,
        **ids,
    }


def parse_input_text(text):
    raw = norm(text)
    urls = URL_RE.findall(raw)
    if urls:
        return parse_url_fields(urls[0])
    result = parse_text_fields(raw)
    # final cleanup and number-like extraction for text-only tests
    for key, value in extract_identifiers(raw).items():
        if not result.get(key):
            result[key] = value
    if not result["bedrooms"]:
        result["bedrooms"] = canonical_bedrooms(raw)
    if not result["size"]:
        sz = parse_size_value(raw)
        result["size"] = f"{sz} sqm" if sz not in {"", None} else ""
    if not result["price"]:
        pr = parse_price_value(raw)
        result["price"] = f"{pr}" if pr not in {"", None} else ""
    return result


def confidence_from_score(score):
    if score >= 90:
        return "RESOLVED"
    if score >= 80:
        return "LIKELY_MATCH"
    if score >= 65:
        return "PARTIAL"
    return "UNRESOLVED"


def is_orphan_url_only_match(query, rec):
    q_url = low(query.get("listing_url", ""))
    r_url = low(list_to_text_url(rec))
    q_lid = low(query.get("listing_id", ""))
    r_lid = low(rec.get("listing_id", ""))
    if not ((q_url and r_url and (q_url == r_url or q_url in r_url or r_url in q_url)) or (q_lid and r_lid and q_lid == r_lid)):
        return False
    if any(
        norm(rec.get(key, ""))
        for key in ("unit", "permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number")
    ):
        return False
    return True


def merge_records(*record_groups):
    merged = {}
    for rows in record_groups:
        for idx, r in enumerate(rows, 1):
            rid = (
                r.get("resolver_record_id")
                or r.get("resolver_id")
                or hashlib.sha1(json.dumps(r, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
            )
            # keep source/row/url variation and row fingerprint to avoid collapsing
            # different records sharing the same resolver_record_id.
            key = (
                f"{rid}|{norm(r.get('source_file',''))}|{norm(r.get('source_sheet',''))}|"
                f"{norm(r.get('source_row',''))}|{norm(r.get('row_number',''))}|"
                f"{norm(r.get('listing_url',''))}|{norm(r.get('property_finder_url',''))}|{norm(r.get('bayut_url',''))}|{norm(r.get('dubizzle_url',''))}"
                f"|{r.get('area','')}|{r.get('project','')}|{r.get('building','')}|{r.get('size','')}|{r.get('price','')}|{idx}"
            )
            if rid not in merged:
                merged[rid] = {}
            if key not in merged[rid]:
                merged[rid][key] = dict(r)
            else:
                existing = merged[rid][key]
                for k, v in r.items():
                    if not existing.get(k) and v:
                        existing[k] = v
    records = []
    for by_id in merged.values():
        records.extend(by_id.values())
    return records


def _row_signature_for_candidate(row):
    return (
        low(row.get("resolver_record_id", "")),
        low(row.get("source_file", "")),
        low(row.get("source_sheet", "")),
        low(row.get("source_row", "")),
        low(row.get("row_number", "")),
        low(row.get("listing_url", "")),
        low(row.get("property_finder_url", "")),
        low(row.get("bayut_url", "")),
        low(row.get("dubizzle_url", "")),
        low(row.get("area", "")),
        low(row.get("project", "")),
        low(row.get("building", "")),
        low(row.get("size", "")),
        low(row.get("price", "")),
    )


def load_raw_text_records():
    """Extract lightweight text snippets from known raw corpus CSV rows for fallback matching."""
    if not OMAR_STYLE_CSV.exists():
        return []
    out = []
    try:
        with OMAR_STYLE_CSV.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, 1):
                text = norm(row.get("text", ""))
                if not text:
                    continue
                t = text.lower()
                if not any(tok in t for tok in KNOWN_PROPERTY_TEXT_PATTERNS):
                    continue
                parsed = parse_text_fields(text)
                rid = hashlib.sha1(f"{idx}|{text}|{OMAR_STYLE_CSV}".encode("utf-8")).hexdigest()[:16]
                out.append(
                    {
                        "resolver_record_id": f"raw-{rid}",
                        "source_platform": parsed.get("source_platform", ""),
                        "listing_url": "",
                        "property_finder_url": "",
                        "bayut_url": "",
                        "dubizzle_url": "",
                        "listing_id": "",
                        "listing_platform": "",
                        "slug_title_tokens": "",
                        "area_tokens": text,
                        "project_building_tokens": text,
                        "permit_number": parsed.get("permit_number", ""),
                        "property_number": parsed.get("property_number", ""),
                        "plot_number": parsed.get("plot_number", ""),
                        "land_number": parsed.get("land_number", ""),
                        "municipality_number": parsed.get("municipality_number", ""),
                        "dewa_number": parsed.get("dewa_number", ""),
                        "area": canonical_area(text),
                        "project": canonical_project(text),
                        "building": canonical_building(text),
                        "property_type": canonical_property_type(text),
                        "unit": parsed.get("unit", ""),
                        "size": parsed.get("size", ""),
                        "bedrooms": parsed.get("bedrooms", ""),
                        "price": parsed.get("price", ""),
                        "developer": "",
                        "owner_contact_available": "NO",
                        "source_file": "raw_chat_style_dataset",
                        "source_path": str(OMAR_STYLE_CSV),
                        "source_chat_group": row.get("chat", ""),
                        "source_sheet": "",
                        "source_row": str(idx),
                        "row_number": str(idx),
                        "extracted_from_pdf": "NO",
                        "extracted_from_sheet": "NO",
                        "extracted_from_text": "YES",
                        "extraction_confidence": "medium",
                        "confidence_score": "55",
                        "match_basis": "text_similarity_fallback",
                        "restricted_ref": "",
                    }
                )
    except Exception:
        return []
    return out


def record_identity(rec):
    return (
        f"{norm(rec.get('resolver_record_id'))}|{norm(rec.get('source_file',''))}|{norm(rec.get('source_sheet',''))}|"
        f"{norm(rec.get('source_row',''))}|{norm(rec.get('row_number',''))}|{norm(rec.get('listing_url',''))}|"
        f"{norm(rec.get('property_finder_url',''))}|{norm(rec.get('bayut_url',''))}|{norm(rec.get('dubizzle_url',''))}"
    )


def load_records_from_db():
    if not DB_PATH.exists():
        return []
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT * FROM resolver_records").fetchall()]
    con.close()
    return rows


def load_records_from_csv(path: Path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_records_from_json():
    if not LISTING_IDENTITY_JSON.exists():
        return []
    with LISTING_IDENTITY_JSON.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def list_to_text_url(rec):
    for key in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url"):
        value = norm(rec.get(key, ""))
        if value:
            return value
    return ""


def prepare_records(rows):
    prepared = []
    for rec in rows:
        rr = dict(rec)
        if not rr.get("listing_url"):
            rr["listing_url"] = list_to_text_url(rr)
        rr["source_platform"] = norm(rr.get("source_platform") or rr.get("listing_platform") or rr.get("platform", ""))
        rr["listing_platform"] = rr["source_platform"]
        if not rr["source_platform"] and rr["listing_url"]:
            rr["source_platform"] = parse_platform(rr["listing_url"])
            rr["listing_platform"] = rr["source_platform"]

        # Resolve blank fields from available token blobs (URL slug / extracted tokens) before matching.
        enriched = derive_fields_from_text_blob(
            " ".join(
                filter(
                    None,
                    [
                        rr.get("area_tokens", ""),
                        rr.get("project_building_tokens", ""),
                        rr.get("slug_title_tokens", ""),
                        rr.get("listing_url", ""),
                    ],
                )
            )
        )
        parsed_url_fields = parse_url_fields(rr["listing_url"]) if rr.get("listing_url") else {}

        rr["area"] = (
            canonical_area(rr.get("area", ""))
            or enriched["area"]
            or canonical_area(parsed_url_fields.get("area", ""))
            or rr.get("area", "")
            or ""
        )[:120]
        rr["project"] = (
            canonical_project(rr.get("project", ""))
            or canonical_project(rr.get("project_name", ""))
            or enriched["project"]
            or canonical_project(parsed_url_fields.get("project", ""))
            or rr.get("project", "")
            or ""
        )[:160]
        rr["building"] = (
            canonical_building(rr.get("building", ""))
            or enriched["building"]
            or canonical_building(parsed_url_fields.get("building", ""))
            or rr.get("building", "")
            or ""
        )[:180]
        rr["property_type"] = (
            canonical_property_type(rr.get("property_type", ""))
            or canonical_property_type(parsed_url_fields.get("property_type", ""))
            or canonical_property_type(
                " ".join(
                    filter(
                        None,
                        [
                            rr.get("slug_title_tokens", ""),
                            rr.get("project_building_tokens", ""),
                        ],
                    )
                )
            )
        )
        rr["bedrooms"] = canonical_bedrooms(rr.get("bedrooms", ""))
        rr["unit"] = normalize_unit(rr.get("unit", ""))
        rr["listing_id"] = rr.get("listing_id") or parsed_url_fields.get("listing_id", "") or ""
        rr["canonical_size_sqm"] = parse_size_value(rr.get("size", "")) if not isinstance(rr.get("size", ""), float) else rr.get("size", "")
        rr["canonical_price"] = parse_price_value(rr.get("price", "")) if not isinstance(rr.get("price", ""), float) else rr.get("price", "")
        rr["status_tokens"] = " ".join([k for k in STATUS_KEYWORDS if k in low(" ".join([rr.get("slug_title_tokens", ""), rr.get("project_building_tokens", ""), rr.get("area", ""), rr.get("project", ""), rr.get("building", "")]))])
        rr["_similarity_text"] = _clean_similarity_text(
            " ".join(
                filter(
                    None,
                    [
                        rr.get("slug_title_tokens", ""),
                        rr.get("project_building_tokens", ""),
                        rr.get("area", ""),
                        rr.get("project", ""),
                        rr.get("building", ""),
                        rr.get("area_tokens", ""),
                        rr.get("query_text", ""),
                    ],
                )
            )
        )
        # attach confidence for deterministic ranking when no match occurs
        rr["source_chat_group"] = rr.get("source_chat_group") or rr.get("chat_group", "")
        prepared.append(rr)
    return prepared


def get_candidate_indexes(records):
    cache_key = id(records)
    cached = _CANDIDATE_INDEX_CACHE.get(cache_key)
    if cached:
        return cached

    eq = {
        "area": defaultdict(list),
        "project": defaultdict(list),
        "source_platform": defaultdict(list),
    }
    building_token = defaultdict(list)
    search_token = defaultdict(list)
    building_token_sets = {}
    search_token_sets = {}

    for rec in records:
        for field in eq:
            value = low(rec.get(field, ""))
            if value:
                eq[field][value].append(rec)

        btokens = set(tokenize(rec.get("building", "")))
        building_token_sets[id(rec)] = btokens
        for token in btokens:
            building_token[token].append(rec)

        stokens = set(
            tokenize(
                " ".join(
                    filter(
                        None,
                        [
                            rec.get("_similarity_text", ""),
                            rec.get("area", ""),
                            rec.get("project", ""),
                            rec.get("building", ""),
                            rec.get("area_tokens", ""),
                        ],
                    )
                )
            )
        )
        search_token_sets[id(rec)] = stokens
        for token in stokens:
            search_token[token].append(rec)

    cached = {
        "eq": eq,
        "building_token": building_token,
        "search_token": search_token,
        "building_token_sets": building_token_sets,
        "search_token_sets": search_token_sets,
    }
    _CANDIDATE_INDEX_CACHE[cache_key] = cached
    return cached


def candidate_pool(records, query):
    indexes = get_candidate_indexes(records)
    qid = low(query.get("listing_id", ""))
    q_url = low(query.get("listing_url", ""))
    direct = []
    if qid:
        direct = [r for r in records if low(r.get("listing_id", "")) == qid]
    if q_url:
        direct.extend([r for r in records if q_url and q_url in low(r.get("listing_url", ""))])
        direct.extend([r for r in records if q_url and low(r.get("listing_url", "")) and low(r.get("listing_url", "")) in q_url])

    qplat = low(query.get("platform", ""))
    query_text = low(" ".join([query.get("area", ""), query.get("project", ""), query.get("building", ""), query.get("property_type", ""), query.get("bedrooms", ""), query.get("size", "")]).strip())
    qarea = canonical_area(query.get("area", ""))
    qproj = canonical_project(query.get("project", ""))
    qbuild = canonical_building(query.get("building", ""))

    plat_rows = indexes["eq"]["source_platform"].get(qplat, []) if qplat else records

    def rows_eq(field, value):
        if not value:
            return []
        target = low(value)
        if field in indexes["eq"]:
            return indexes["eq"][field].get(target, [])
        return [r for r in records if low(r.get(field, "")) == target]

    def rows_contains_tokens(field, value):
        tokens = set(tokenize(value))
        if not tokens:
            return []
        if field == "building":
            postings = indexes["building_token"]
            if any(token not in postings for token in tokens):
                return []
            seed = min((postings[token] for token in tokens), key=len)
            token_sets = indexes["building_token_sets"]
            return [r for r in seed if tokens.issubset(token_sets.get(id(r), set()))]
        out = []
        for r in records:
            row_tokens = tokenize(r.get(field, ""))
            if not row_tokens:
                continue
            if all(tok in row_tokens for tok in tokens):
                out.append(r)
        return out

    def rows_contains_any_tokens(field, value):
        tokens = set(tokenize(value))
        if not tokens:
            return []
        if field == "building":
            out = []
            seen_postings = set()
            postings = indexes["building_token"]
            for token in tokens:
                for rec in postings.get(token, []):
                    sig = id(rec)
                    if sig not in seen_postings:
                        seen_postings.add(sig)
                        out.append(rec)
            return out
        out = []
        for r in records:
            row_tokens = set(tokenize(r.get(field, "")))
            if not row_tokens:
                continue
            if tokens.intersection(row_tokens):
                out.append(r)
        return out

    def rows_contains_token(value):
        if not value:
            return []
        out = []
        qtokens = set(tokenize(value))
        if qtokens:
            seen_postings = set()
            postings = indexes["search_token"]
            for token in qtokens:
                for rec in postings.get(token, []):
                    sig = id(rec)
                    if sig not in seen_postings:
                        seen_postings.add(sig)
                        out.append(rec)
            return out
        for r in records:
            rtext = f"{low(r.get('slug_title_tokens', ''))} {low(r.get('project_building_tokens', ''))} {low(r.get('area', ''))} {low(r.get('project', ''))} {low(r.get('building', ''))} {low(r.get('area_tokens', ''))}"
            if qtokens.intersection(tokenize(rtext)):
                out.append(r)
        return out

    def intersection(*groups):
        if not groups:
            return []
        base = {_row_signature_for_candidate(r): r for r in groups[0]}
        if not base:
            return []
        common = set(base.keys())
        for g in groups[1:]:
            if not g:
                return []
            current = {_row_signature_for_candidate(x) for x in g}
            common &= current
        return [base[sig] for sig in common if sig in base]

    candidates = []
    seen = set()
    ordered = []

    def add_rows(rows):
        for r in rows:
            sig = _row_signature_for_candidate(r)
            if sig not in seen:
                seen.add(sig)
                ordered.append(r)

    if qarea and qproj and qbuild:
        add_rows(intersection(rows_eq("area", qarea), rows_contains_tokens("building", qbuild), rows_contains_any_tokens("project", qproj)))
    if qarea and qbuild:
        add_rows(intersection(rows_eq("area", qarea), rows_contains_tokens("building", qbuild)))
    if qarea and qproj:
        add_rows(intersection(rows_eq("area", qarea), rows_eq("project", qproj)))
    if qproj and qbuild:
        add_rows(intersection(rows_eq("project", qproj), rows_contains_tokens("building", qbuild)))
    if direct:
        add_rows(direct)
    if qarea and not ordered:
        add_rows(rows_eq("area", qarea))
    if qproj and not ordered:
        add_rows(rows_eq("project", qproj))
    if qbuild and not ordered:
        add_rows(rows_contains_tokens("building", qbuild))
        add_rows(rows_contains_any_tokens("building", qbuild))

    if ordered:
        return ordered[:2000]

    # fallback by platform + token overlap
    add_rows(plat_rows)
    if len(ordered) < 200:
        add_rows(rows_contains_token(query_text))

    if ordered:
        return ordered[:2000]

    return records[:2000]


def sequence_ratio(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, low(a), low(b)).ratio()


def token_overlap_ratio(a, b):
    a_tokens = set(tokenize(a))
    b_tokens = set(tokenize(b))
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens.intersection(b_tokens)) / max(1, min(len(a_tokens), len(b_tokens)))


def score_record(query, rec):
    score = 0
    breakdown = []

    # identifier-based
    for key in ["permit_number", "property_number", "plot_number", "land_number", "municipality_number", "dewa_number"]:
        qv = low(query.get(key, ""))
        rv = low(rec.get(key, ""))
        if qv and rv and qv == rv:
            score += 45
            breakdown.append(f"{key}:match+45")
            break

    # exact listing URL or ID
    q_lid = low(query.get("listing_id", ""))
    r_lid = low(rec.get("listing_id", ""))
    if q_lid and r_lid and q_lid == r_lid:
        score += 40
        breakdown.append("listing_id_exact:+40")
    q_url = low(query.get("listing_url", ""))
    r_url = low(list_to_text_url(rec))
    if q_url and r_url and (q_url == r_url or q_url in r_url or r_url in q_url):
        score += 40
        breakdown.append("listing_url_match:+40")

    # location signals
    qa = canonical_area(query.get("area", ""))
    ra = canonical_area(rec.get("area", ""))
    if qa and ra:
        if qa == ra:
            score += 10
            breakdown.append("same_area:+10")
        elif sequence_ratio(qa, ra) >= 0.80:
            score += 6
            breakdown.append("area_fuzzy:+6")

    qp = canonical_project(query.get("project", ""))
    rp = canonical_project(rec.get("project", ""))
    qb = canonical_building(query.get("building", ""))
    rb = canonical_building(rec.get("building", ""))
    if qp and rp:
        if qp == rp:
            score += 20
            breakdown.append("same_project:+20")
        elif sequence_ratio(qp, rp) >= 0.72:
            score += 8
            breakdown.append("project_fuzzy:+8")
    if qb and rb:
        if qb == rb:
            score += 20
            breakdown.append("same_building:+20")
            if qa and ra and qa == ra and qb == rb and len(tokenize(qb)) >= 2:
                score += 35
                breakdown.append("same_area_and_building_strong:+35")
        elif sequence_ratio(qb, rb) >= 0.72:
            score += 10
            breakdown.append("building_fuzzy:+10")
        else:
            qb_tokens = set(tokenize(qb))
            rb_tokens = set(tokenize(rb))
            if qb_tokens and rb_tokens:
                overlap = len(qb_tokens.intersection(rb_tokens))
                if overlap >= max(1, len(qb_tokens) * 0.66):
                    score += 12
                    breakdown.append("building_token_overlap:+12")
                elif overlap >= max(1, len(qb_tokens) * 0.33):
                    score += 6
                    breakdown.append("building_token_partial_overlap:+6")

    q_property_type = canonical_property_type(query.get("property_type", ""))
    r_property_type = canonical_property_type(
        " ".join(
            filter(
                None,
                [
                    rec.get("property_type", ""),
                    rec.get("slug_title_tokens", ""),
                    rec.get("project_building_tokens", ""),
                    rec.get("area_tokens", ""),
                    low(rec.get("listing_url", "")),
                ],
            )
        )
    )
    if q_property_type and r_property_type and q_property_type == r_property_type:
        score += 5
        breakdown.append("same_property_type:+5")

    rbeds = ""
    if canonical_unit := canonical_bedrooms(query.get("bedrooms", "")):
        rbeds = canonical_bedrooms(rec.get("bedrooms", ""))
        if canonical_unit and rbeds and canonical_unit == rbeds:
            score += 10
            breakdown.append("same_bedrooms:+10")

    qsize = parse_size_value(query.get("size", ""))
    rsize = rec.get("canonical_size_sqm", "")
    if qsize not in {"", None} and rsize not in {"", None}:
        try:
            qf = float(qsize)
            rf = float(rsize)
            if qf > 0 and rf > 0:
                diff = abs(qf - rf) / qf
                if diff <= 0.05:
                    score += 15
                    breakdown.append("size_within_5%:+15")
                elif diff <= 0.10:
                    score += 8
                    breakdown.append("size_within_10%:+8")
        except Exception:
            pass

    qprice = parse_price_value(query.get("price", ""))
    rprice = rec.get("canonical_price", "")
    if qprice not in {"", None} and rprice not in {"", None}:
        try:
            qpf = float(qprice)
            rpf = float(rprice)
            if qpf > 0 and rpf > 0:
                diff = abs(qpf - rpf) / qpf
                if diff <= 0.05:
                    score += 15
                    breakdown.append("price_within_5%:+15")
                elif diff <= 0.10:
                    score += 10
                    breakdown.append("price_within_10:+10")
                elif diff <= 0.20:
                    score += 6
                    breakdown.append("price_within_20:+6")
        except Exception:
            pass

    qstatus = set(query.get("status_tokens", "").split())
    if qstatus:
        rst = set(rec.get("status_tokens", "").split())
        if qstatus.intersection(rst):
            score += 5
            breakdown.append("status_keyword_match:+5")

    if qa and ra and qa == ra and canonical_unit and rbeds and canonical_unit == rbeds and qsize not in {"", None} and rsize not in {"", None} and qprice not in {"", None} and rprice not in {"", None}:
        try:
            size_diff = abs(float(qsize) - float(rsize)) / max(float(qsize), 1.0)
            price_diff = abs(float(qprice) - float(rprice)) / max(float(qprice), 1.0)
            if size_diff <= 0.10 and price_diff <= 0.10:
                score += 10
                breakdown.append("area_bed_size_price_bundle:+10")
        except Exception:
            pass

    q_units = normalize_unit(query.get("unit", ""))
    r_units = normalize_unit(rec.get("unit", ""))
    if q_units and r_units and q_units == r_units:
        score += 4
        breakdown.append("same_unit:+4")

    # text similarity
    qtext = query.get("_similarity_text", "") or _clean_similarity_text(
        " ".join(
            filter(
                None,
                [
                    query.get("query_text", ""),
                    query.get("slug_title_tokens", ""),
                    query.get("area", ""),
                    query.get("project", ""),
                    query.get("building", ""),
                    query.get("property_type", ""),
                    query.get("bedrooms", ""),
                    query.get("size", ""),
                    query.get("price", ""),
                ],
            )
        )
    )
    rtext = rec.get("_similarity_text", "") or _clean_similarity_text(
        " ".join(
            filter(
                None,
                [
                    rec.get("slug_title_tokens", ""),
                    rec.get("project_building_tokens", ""),
                    rec.get("area", ""),
                    rec.get("project", ""),
                    rec.get("building", ""),
                    rec.get("area_tokens", ""),
                    rec.get("query_text", ""),
                ]
            )
        )
    )
    token_ratio = token_overlap_ratio(qtext, rtext)
    tscore = 0.0
    if token_ratio >= 0.20 or (len(qtext) <= 260 and len(rtext) <= 260):
        tscore = sequence_ratio(qtext, rtext)
    if tscore >= 0.75:
        score += 10
        breakdown.append("text_high:+10")
    elif tscore >= 0.55:
        score += 6
        breakdown.append("text_medium:+6")
    elif token_ratio >= 0.50:
        score += 10
        breakdown.append("text_overlap_50:+10")
    elif tscore >= 0.35 or token_ratio >= 0.30:
        score += 3
        breakdown.append("text_low:+3")

    if low(query.get("source_file", "")) and low(query.get("source_file", "")) == low(rec.get("source_file", "")):
        score += 5
        breakdown.append("same_source_file:+5")
    if low(query.get("source_chat_group", "")) and low(query.get("source_chat_group", "")) == low(rec.get("source_chat_group", "")):
        score += 2
        breakdown.append("same_chat_group:+2")
    if query.get("source_platform") and rec.get("source_platform") and low(query.get("source_platform")) == low(rec.get("source_platform")):
        score += 3
        breakdown.append("same_platform:+3")

    # optional cluster signals from source/date context
    source_row = norm(query.get("row_number", ""))
    if source_row and source_row == norm(rec.get("row_number", "")):
        score += 3
        breakdown.append("same_row:+3")

    return min(100, score), breakdown


def build_record_signature(rec):
    return {
        "resolver_record_id": rec.get("resolver_record_id", ""),
        "area": rec.get("area", ""),
        "project": rec.get("project", ""),
        "building": rec.get("building", ""),
        "unit": rec.get("unit", ""),
        "bedrooms": rec.get("bedrooms", ""),
        "size": rec.get("size", ""),
        "price": rec.get("price", ""),
        "permit_number": rec.get("permit_number", ""),
        "property_number": rec.get("property_number", ""),
        "plot_number": rec.get("plot_number", ""),
        "land_number": rec.get("land_number", ""),
        "source_file": rec.get("source_file", ""),
        "source_sheet": rec.get("source_sheet", ""),
        "row_number": rec.get("row_number", ""),
        "source_platform": rec.get("source_platform", ""),
        "listing_url": list_to_text_url(rec),
        "owner_contact_available": rec.get("owner_contact_available", ""),
    }


def resolve_listing_by_similarity(input_url_or_text):
    raw = norm(input_url_or_text)
    query = parse_input_text(raw)
    query["_similarity_text"] = _clean_similarity_text(
        " ".join(
            filter(
                None,
                [
                    query.get("query_text", ""),
                    query.get("slug_title_tokens", ""),
                    query.get("area", ""),
                    query.get("project", ""),
                    query.get("building", ""),
                    query.get("property_type", ""),
                    query.get("bedrooms", ""),
                    query.get("size", ""),
                    query.get("price", ""),
                ],
            )
        )
    )
    parsed = {
        "platform": query.get("platform", ""),
        "listing_id": query.get("listing_id", ""),
        "transaction": query.get("transaction", ""),
        "property_type": query.get("property_type", ""),
        "area": query.get("area", ""),
        "project": query.get("project", ""),
        "building": query.get("building", ""),
        "unit": query.get("unit", ""),
        "bedrooms": query.get("bedrooms", ""),
        "size": query.get("size", ""),
        "price": query.get("price", ""),
        "status_tokens": query.get("status_tokens", ""),
        "permit_number": query.get("permit_number", ""),
        "property_number": query.get("property_number", ""),
        "plot_number": query.get("plot_number", ""),
        "land_number": query.get("land_number", ""),
        "municipality_number": query.get("municipality_number", ""),
        "dewa_number": query.get("dewa_number", ""),
        "source_platform": query.get("source_platform", ""),
        "source_file": query.get("source_file", ""),
        "source_chat_group": query.get("source_chat_group", ""),
    }

    records = get_prepared_records()
    candidates = candidate_pool(records, query)
    scored = []
    for rec in candidates:
        score, breakdown = score_record(query, rec)
        if score <= 0:
            continue
        effective_score = score
        if is_orphan_url_only_match(query, rec):
            effective_score = min(effective_score, 64)
            breakdown = breakdown + ["orphan_url_only_match_cap:+0"]
        item = {
            "resolver_record_id": rec.get("resolver_record_id", ""),
            **build_record_signature(rec),
            "score": effective_score,
            "score_breakdown": json.dumps(breakdown, ensure_ascii=False),
            "confidence": confidence_from_score(effective_score),
            "status_label": confidence_from_score(effective_score),
        }
        scored.append(item)

    scored.sort(key=lambda r: (r["score"], r["resolver_record_id"]), reverse=True)
    top = scored[:20]
    return {
        "input": raw,
        "parsed": parsed,
        "candidates": top,
        "total_candidates": len(scored),
        "candidate_count_reported": len(top),
        "top_confidence": top[0]["confidence"] if top else "UNRESOLVED",
        "classification": top[0]["confidence"] if top else "UNRESOLVED",
    }


def get_prepared_records():
    global _PREPARED_RECORD_CACHE
    if _PREPARED_RECORD_CACHE is not None:
        return _PREPARED_RECORD_CACHE
    all_records = merge_records(
        load_records_from_db(),
        load_records_from_json(),
        load_records_from_csv(LISTING_IDENTITY_CSV),
        load_records_from_csv(INDEX_CSV),
        load_raw_text_records(),
    )
    _PREPARED_RECORD_CACHE = prepare_records(all_records)
    return _PREPARED_RECORD_CACHE


def pick_url_tests(records, limit=10):
    tests = []
    seen = set()
    preferred = []
    fallback = []
    for r in records:
        for col in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url"):
            u = norm(r.get(col, ""))
            if not u:
                continue
            if u in seen:
                continue
            if not PLATFORM_RE.search(u):
                continue
            if "/leads/" in low(u) or "/transactions/" in low(u):
                continue
            # listing-like or shared short URL fragments
            if any(x in low(u) for x in ["/plp/", "/property/details", "property-details", "details-", "/property-details/", "/for-", "/to-", "/rent/", "/buy/"]):
                preferred.append(u)
            else:
                fallback.append(u)
            seen.add(u)
            break
    for u in preferred:
        if u not in tests:
            tests.append(u)
        if len(tests) >= limit:
            break
    if len(tests) < limit:
        # fill remaining with any valid platform URLs
        for u in fallback:
            if u not in tests:
                tests.append(u)
            if len(tests) >= limit:
                break
    return tests


def pick_text_only_tests(records, limit=10):
    tests = []
    for r in records:
        if any(norm(r.get(k, "")) for k in ("listing_url", "property_finder_url", "bayut_url", "dubizzle_url")):
            continue
        area = r.get("area", "")
        project = r.get("project", "")
        building = r.get("building", "")
        size = r.get("size", "")
        beds = r.get("bedrooms", "")
        price = r.get("price", "")
        if not any([area, project, building, size, beds, price]):
            continue
        fragments = [x for x in [area, project, building, f"{beds} bed", size, price] if x]
        q = " ".join(fragments)
        if q and q not in tests:
            tests.append(q)
        if len(tests) >= limit:
            break
    return tests


def write_candidate_csv(test_results, output_path=OUT_CSV):
    with output_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for test in test_results:
            for cand in test["candidates"]:
                row = {
                    "test_label": test["label"],
                    "rank": cand.get("rank", ""),
                    "resolver_record_id": cand.get("resolver_record_id", ""),
                    "area": cand.get("area", ""),
                    "project": cand.get("project", ""),
                    "building": cand.get("building", ""),
                    "unit": cand.get("unit", ""),
                    "bedrooms": cand.get("bedrooms", ""),
                    "size": cand.get("size", ""),
                    "price": cand.get("price", ""),
                    "permit_number": cand.get("permit_number", ""),
                    "property_number": cand.get("property_number", ""),
                    "plot_number": cand.get("plot_number", ""),
                    "land_number": cand.get("land_number", ""),
                    "source_file": cand.get("source_file", ""),
                    "source_sheet": cand.get("source_sheet", ""),
                    "row_number": cand.get("row_number", ""),
                    "source_platform": cand.get("source_platform", ""),
                    "listing_url": cand.get("listing_url", ""),
                    "score": cand.get("score", ""),
                    "score_breakdown": cand.get("score_breakdown", ""),
                    "confidence": cand.get("confidence", ""),
                    "status_label": cand.get("status_label", ""),
                    "owner_contact_available": cand.get("owner_contact_available", ""),
                    "input": test["input"],
                    "parsed_platform": test["parsed"].get("platform", ""),
                    "parsed_listing_id": test["parsed"].get("listing_id", ""),
                    "parsed_area": test["parsed"].get("area", ""),
                    "parsed_project": test["parsed"].get("project", ""),
                    "parsed_building": test["parsed"].get("building", ""),
                    "parsed_bedrooms": test["parsed"].get("bedrooms", ""),
                    "parsed_size": test["parsed"].get("size", ""),
                    "parsed_price": test["parsed"].get("price", ""),
                }
                w.writerow(row)
    return output_path


def write_test_report(test_results):
    counts = Counter(r["status"] for r in test_results)
    url_tests = [t for t in test_results if t["label"] == "ocean_heights" or t["label"].startswith("url_")]
    text_tests = [t for t in test_results if t["label"].startswith("text_only_")]
    reached_80 = sum(1 for t in url_tests if t["best_score"] >= 80)
    reached_90 = sum(1 for t in url_tests if t["best_score"] >= 90)
    ocean = next((t for t in test_results if t["label"] == "ocean_heights"), None)

    failure = Counter()
    for t in test_results:
        if t["status"] == "UNRESOLVED" and t["best_score"] == 0:
            failure["no_candidate"] += 1
        elif t["status"] == "UNRESOLVED":
            failure["below_65"] += 1
        elif t["status"] == "PARTIAL":
            failure["partially_matched"] += 1

    top_status = "UNRESOLVED"
    if url_tests:
        top_status = url_tests[0]["status"]

    if any(t["best_score"] >= 90 for t in url_tests):
        classification = "LIVE"
    elif any(t["status"] in {"RESOLVED", "LIKELY_MATCH", "PARTIAL"} for t in url_tests):
        classification = "PARTIAL"
    else:
        classification = "FAILED"

    with OUT_REPORT.open("w", encoding="utf-8") as f:
        f.write("# AIOS Listing Similarity Match Report\n\n")
        f.write(f"- total tests: {len(test_results)}\n")
        f.write(f"- url-like tests: {len(url_tests)}\n")
        f.write(f"- text-only tests: {len(text_tests)}\n")
        f.write(f"- classification: {classification}\n")
        f.write(f"- url tests >=80 confidence: {reached_80}\n")
        f.write(f"- url tests >=90 confidence: {reached_90}\n\n")

        if ocean:
            f.write("## Ocean Heights Query\n")
            f.write(f"- input: `{ocean['input']}`\n")
            f.write(f"- parsed: {json.dumps(ocean['parsed'], ensure_ascii=False)}\n")
            f.write(f"- top status: {ocean['status']} score={ocean['best_score']}\n")
            f.write("- Top 5 candidates:\n")
            for c in ocean['top5']:
                f.write(
                    f"  - id={c['resolver_record_id']} area={c['area']} project={c['project']} building={c['building']} bedrooms={c['bedrooms']} size={c['size']} score={c['score']} confidence={c['confidence']} file={c['source_file']}\n"
                )
            f.write("\n")

        f.write("## URL test outcomes\n")
        for t in url_tests:
            f.write(f"- {t['label']} | status={t['status']} | score={t['best_score']}\n")
            for c in t['top5']:
                f.write(
                    f"  - id={c['resolver_record_id']} area={c['area']} project={c['project']} building={c['building']} score={c['score']} conf={c['confidence']} source={c['source_file']}\n"
                )
        f.write("\n## Text-only test outcomes\n")
        for t in text_tests:
            f.write(f"- {t['label']} | status={t['status']} | score={t['best_score']}\n")
        f.write("\n## Failure summary\n")
        for reason, count in sorted(failure.items(), key=lambda x: (-x[1], x[0])):
            f.write(f"- {reason}: {count}\n")
        f.write(f"\n- list file: `{OUT_CSV}`\n")
        f.write(f"- report file: `{OUT_REPORT}`\n")

    return classification, reached_80, reached_90


def run_step8_tests(records):
    tests = []
    # mandatory test
    tests.append(("ocean_heights", "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-dubai-marina-ocean-heights-84894360.html"))

    # URL tests from real corpus URLs
    for idx, url in enumerate(pick_url_tests(records, limit=10), 1):
        if "84894360" in url:
            continue
        tests.append((f"url_{idx}", url))

    # text tests from corpus records without URLs
    for idx, q in enumerate(pick_text_only_tests(records, limit=10), 1):
        tests.append((f"text_only_{idx}", q))

    results = []
    for label, query in tests:
        result = resolve_listing_by_similarity(query)
        if result["candidates"]:
            best = result["candidates"][0]
            status = best["status_label"]
        else:
            best = None
            status = "UNRESOLVED"

        ranked = []
        for i, cand in enumerate(result["candidates"][:5], start=1):
            rec = dict(cand)
            rec["rank"] = i
            ranked.append(rec)

        results.append(
            {
                "label": label,
                "input": result["input"],
                "parsed": result["parsed"],
                "status": status,
                "best_score": best["score"] if best else 0,
                "top5": ranked,
                "candidates": result["candidates"],
            }
        )
    return results


def main(run_tests=False, input_text=None):
    db_records = load_records_from_db()
    json_records = load_records_from_json()
    id_csv = load_records_from_csv(LISTING_IDENTITY_CSV)
    idx_csv = load_records_from_csv(INDEX_CSV)
    records = merge_records(db_records, json_records, id_csv, idx_csv)

    if run_tests:
        test_results = run_step8_tests(records)
        for t in test_results:
            t["candidates"] = [
                {
                    **c,
                    "rank": i + 1,
                }
                for i, c in enumerate(t["candidates"])
            ]

        write_candidate_csv(test_results)
        classification, reached80, reached90 = None, 0, 0
        classification, reached80, reached90 = write_test_report(test_results)

        url_tests = [t for t in test_results if t["label"] == "ocean_heights" or t["label"].startswith("url_")]
        if any(t["best_score"] >= 90 for t in url_tests):
            final_status = "LIVE"
        elif any(t["status"] in {"RESOLVED", "LIKELY_MATCH", "PARTIAL"} for t in url_tests):
            final_status = "PARTIAL"
        else:
            final_status = "FAILED"
        output = {
            "classification": final_status,
            "ocean_result": next((t["status"] for t in test_results if t["label"] == "ocean_heights"), "UNRESOLVED"),
            "candidates_csv": str(OUT_CSV),
            "report": str(OUT_REPORT),
            "url_tests_reached_80": reached80,
            "url_tests_reached_90": reached90,
        }
        return output
    else:
        return resolve_listing_by_similarity(input_text or "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="Optional single URL/text query to resolve")
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    if args.run_tests:
        result = main(run_tests=True)
    else:
        result = main(input_text=args.input or "")
    print(json.dumps(result, ensure_ascii=False, indent=2))
