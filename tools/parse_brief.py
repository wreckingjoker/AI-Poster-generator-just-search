"""
tools/parse_brief.py
Converts raw freeform poster brief text into a structured dict.
No API calls — purely deterministic text parsing.
"""

import json
import re
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DIMENSION_MAP = {
    "4:5":       (1080, 1350),
    "1:1":       (1080, 1080),
    "story":     (1080, 1920),
    "landscape": (1200, 628),
}

SIZE_KEYWORDS = {
    "4:5": ["4:5", "post", "feed", "portrait"],
    "1:1": ["1:1", "square"],
    "story": ["story", "9:16", "reel", "stories"],
    "landscape": ["landscape", "16:9", "cover", "banner"],
}

TONE_KEYWORDS = {
    "luxury minimal":  ["luxury", "minimal", "minimalist", "premium", "elegant", "high-end"],
    "vibrant playful": ["vibrant", "playful", "fun", "bold", "colorful", "energetic", "youthful"],
    "corporate clean": ["corporate", "professional", "clean", "business", "formal"],
    "warm lifestyle":  ["warm", "lifestyle", "authentic", "cozy", "approachable"],
    "bold energetic":  ["dramatic", "energetic", "dynamic", "impact", "powerful"],
    "soft feminine":   ["soft", "feminine", "pastel", "gentle", "delicate", "graceful"],
}


def slugify_keyword(text: str) -> str:
    """Convert 'Summer Sale 2025!' -> 'summer_sale'. Max 2 meaningful words."""
    text = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
    words = [w for w in text.split() if len(w) > 2 and w not in {
        "the", "and", "for", "our", "with", "this", "that", "from", "off",
        "get", "all", "new", "use", "now", "are", "has", "its"
    }]
    return "_".join(words[:2]) if words else "poster"


def detect_poster_size(raw_text: str) -> tuple[str, tuple[int, int]]:
    """
    Parse size from brief text. Returns (size_key, (width, height)).
    Defaults to 4:5 (1080x1350) if not specified.
    """
    text_lower = raw_text.lower()
    for size_key, keywords in SIZE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return size_key, DIMENSION_MAP[size_key]
    return "4:5", DIMENSION_MAP["4:5"]


def detect_tone_override(raw_text: str) -> str | None:
    """Extract explicit tone/style preference from brief. Returns None if not found."""
    text_lower = raw_text.lower()
    for tone, keywords in TONE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return tone
    return None


def extract_offer_text(raw_text: str) -> str:
    """Extract the main offer/message from the brief."""
    patterns = [
        r"offer[:\s]+(.+?)(?:\.|,|$)",
        r"([0-9]+%\s*off[^,.\n]*)",
        r"(sale[^,.\n]*)",
        r"(deal[^,.\n]*)",
        r"(launch[^,.\n]*)",
        r"(promotion[^,.\n]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:200]
    # Fallback: use first sentence
    sentences = re.split(r"[.!?]", raw_text)
    return sentences[0].strip()[:200] if sentences else raw_text[:200]


def extract_product_name(raw_text: str) -> str | None:
    """Try to extract a product name from the brief."""
    patterns = [
        r"product[:\s]+([^,.\n]+)",
        r"for\s+(?:our\s+)?([A-Z][a-zA-Z\s]{2,30}(?:Collection|Range|Line|Product|Service))",
        r"featuring\s+([^,.\n]+)",
        r"promoting\s+([^,.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]
    return None


def extract_deadline(raw_text: str) -> str | None:
    """Extract deadline date if mentioned."""
    patterns = [
        r"by\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"deadline[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"before\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}",
        r"(tomorrow|today|urgent|asap)",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_color_override(raw_text: str) -> str | None:
    """Extract explicit color requests."""
    patterns = [
        r"(?:use|make it|color[s]?|with)[:\s]+([a-zA-Z]+(?:\s+and\s+[a-zA-Z]+)?)\s+(?:color|colours?|theme|tones?)",
        r"(#[0-9a-fA-F]{3,6})",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def parse_brief(raw_text: str, mode: str = "new") -> dict:
    """
    Converts raw poster brief text from the UI into a structured dict.

    mode: "new" (full parse) | "re_edit" (only changed fields)

    Returns:
    {
        "offer_text": str,
        "product_name": str | None,
        "poster_size": str,
        "dimensions": (int, int),
        "deadline": str | None,
        "brief_keyword": str,
        "tone_override": str | None,
        "color_override": str | None,
        "raw_brief": str,
        "parse_confidence": float
    }
    """
    if not raw_text or len(raw_text.strip()) < 10:
        raise ValueError(
            "Brief too short — please describe the poster in at least one sentence "
            "(minimum 10 characters)."
        )

    raw_text = raw_text.strip()

    offer_text    = extract_offer_text(raw_text)
    product_name  = extract_product_name(raw_text)
    size_key, dims = detect_poster_size(raw_text)
    deadline      = extract_deadline(raw_text)
    tone_override = detect_tone_override(raw_text)
    color_override = extract_color_override(raw_text)
    brief_keyword = slugify_keyword(offer_text or raw_text)

    # Confidence: higher when more fields are deterministically found
    found_fields = sum([
        bool(offer_text),
        bool(product_name),
        bool(tone_override),
        bool(deadline),
    ])
    parse_confidence = min(0.4 + (found_fields * 0.15), 1.0)

    result = {
        "offer_text":       offer_text,
        "product_name":     product_name,
        "poster_size":      size_key,
        "dimensions":       dims,
        "deadline":         deadline,
        "brief_keyword":    brief_keyword,
        "tone_override":    tone_override,
        "color_override":   color_override,
        "raw_brief":        raw_text,
        "parse_confidence": round(parse_confidence, 2),
    }

    return result


def save_brief(brief: dict, job_id: str) -> Path:
    """Save parsed brief to .tmp/prompts/[job_id]_brief.json."""
    out_dir = BASE_DIR / ".tmp" / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}_brief.json"

    # Convert tuple to list for JSON serialization
    brief_serializable = dict(brief)
    if isinstance(brief_serializable.get("dimensions"), tuple):
        brief_serializable["dimensions"] = list(brief_serializable["dimensions"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(brief_serializable, f, indent=2, ensure_ascii=False)

    return out_path


if __name__ == "__main__":
    import sys
    test_brief = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else (
        "50% off summer collection sale, luxury minimal feel, 4:5 format, "
        "featuring our new dress line, deadline by end of June"
    )
    result = parse_brief(test_brief)
    print(json.dumps(result, indent=2))
