"""
tools/extract_brand_dna.py
Feed scraped Instagram images to Google Gemini 1.5 Flash for brand analysis.
Aggregate per-image results into a single Brand DNA JSON.
"""

import base64
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from job_tracker import log_api_call

BASE_DIR      = Path(__file__).resolve().parent.parent
BRAND_DNA_DIR = BASE_DIR / ".tmp" / "brand_dna"

load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL          = "gemini-1.5-flash"

BRAND_DNA_SCHEMA = {
    "client_handle":    None,
    "analyzed_on":      None,
    "primary_colors":   None,
    "accent_colors":    None,
    "background_style": None,
    "tone":             None,
    "typography_style": None,
    "layout_pattern":   None,
    "logo_position":    None,
    "common_themes":    None,
    "sample_post_urls": None,
    "confidence_score": None,
}

GEMINI_VISION_PROMPT = """You are a brand identity analyst for a digital marketing agency.
Analyze this Instagram post image and extract visual brand attributes.

Return ONLY valid JSON with these exact fields (no markdown, no explanation, no code blocks):
{
  "primary_colors": ["#HEX1", "#HEX2"],
  "accent_colors": ["#HEX3"],
  "background_style": "dark gradient|solid white|solid black|textured|lifestyle photo|product flat lay|colorful gradient",
  "tone": "luxury minimal|vibrant playful|corporate clean|warm lifestyle|bold energetic|soft feminine",
  "typography_style": "bold sans-serif|elegant serif|handwritten accent|mixed|not visible",
  "layout_pattern": "centered product|left-aligned text|right-aligned text|full bleed image|split layout|text overlay",
  "logo_position": "top-center|top-left|top-right|bottom-center|bottom-left|bottom-right|not visible",
  "themes": ["product closeup", "lifestyle", "seasonal offer", "team/people", "text-only", "event", "food", "fashion", "beauty"],
  "dominant_feeling": "one sentence describing the emotional impact"
}

Rules:
- Extract ACTUAL hex colors visible in the image. Do not guess brand defaults.
- Only list color values you can see — typical posts have 2-3 dominant colors.
- If typography is not visible, use "not visible".
- Only include themes that clearly apply to this specific image.
- If you cannot determine a field with confidence, use null.
- Return raw JSON only — no markdown, no backticks, no explanation."""


def _setup_gemini() -> genai.GenerativeModel:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_key_here":
        raise ValueError(
            "GEMINI_API_KEY not set. Get a free key at https://aistudio.google.com/app/apikey "
            "and add it to your .env file."
        )
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel(MODEL)


def _load_image_as_base64(image_path: Path) -> tuple[str, str] | None:
    """Load image as base64. Returns (base64_data, mime_type) or None on failure."""
    try:
        suffix = image_path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
        mime_type = mime_map.get(suffix, "image/jpeg")
        data = image_path.read_bytes()
        if len(data) > 20 * 1024 * 1024:  # 20MB limit for inline Gemini
            print(f"[dna] Skipping {image_path.name}: too large ({len(data)//1024}KB)")
            return None
        return base64.b64encode(data).decode("utf-8"), mime_type
    except Exception as e:
        print(f"[dna] Failed to load {image_path}: {e}")
        return None


def _extract_json_from_response(text: str) -> dict | None:
    """Parse JSON from Gemini response, handling markdown code blocks."""
    # Strip markdown code blocks if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    text = text.rstrip("`").strip()

    # Find JSON object
    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def analyze_single_image(image_path: Path, model: genai.GenerativeModel) -> dict | None:
    """
    Send one image to Gemini vision. Returns parsed analysis dict or None on failure.
    """
    img_data = _load_image_as_base64(image_path)
    if not img_data:
        return None

    b64_data, mime_type = img_data
    image_part = {"mime_type": mime_type, "data": b64_data}

    try:
        response = model.generate_content(
            [GEMINI_VISION_PROMPT, image_part],
            generation_config={"temperature": 0.1, "max_output_tokens": 1024},
        )
        raw_text = response.text
        result = _extract_json_from_response(raw_text)
        if result is None:
            print(f"[dna] Could not parse JSON from Gemini for {image_path.name}")
            return None
        return result

    except Exception as e:
        print(f"[dna] Gemini call failed for {image_path.name}: {e}")
        return None


def normalize_hex(color: str) -> str | None:
    """Normalize hex color string. Returns None if invalid."""
    color = color.strip().upper()
    if not color.startswith("#"):
        color = "#" + color
    if re.match(r"^#[0-9A-F]{6}$", color):
        return color
    if re.match(r"^#[0-9A-F]{3}$", color):
        # Expand shorthand
        return "#" + "".join(c * 2 for c in color[1:])
    return None


def aggregate_brand_dna(
    analyses: list[dict],
    client_handle: str,
    post_urls: list[str],
) -> dict:
    """
    Merge per-image analysis dicts into one Brand DNA JSON.
    Uses Counter-based frequency voting for all categorical fields.
    """
    valid = [a for a in analyses if a is not None]

    if not valid:
        raise ValueError("No valid image analyses — cannot produce Brand DNA")

    confidence = len(valid) / max(len(analyses), 1)

    # Aggregate colors
    all_primary = []
    all_accent = []
    for a in valid:
        for c in (a.get("primary_colors") or []):
            n = normalize_hex(c)
            if n:
                all_primary.append(n)
        for c in (a.get("accent_colors") or []):
            n = normalize_hex(c)
            if n:
                all_accent.append(n)

    primary_counter = Counter(all_primary)
    top_primary = [c for c, _ in primary_counter.most_common(2)]

    # Accent = colors not already in primary, top 2
    accent_counter = Counter(c for c in all_accent if c not in top_primary)
    top_accent = [c for c, _ in accent_counter.most_common(2)]

    def most_common_value(field: str) -> str | None:
        values = [a.get(field) for a in valid if a.get(field)]
        if not values:
            return None
        return Counter(values).most_common(1)[0][0]

    # Aggregate themes
    all_themes = []
    for a in valid:
        themes = a.get("themes") or []
        all_themes.extend(themes)
    theme_counter = Counter(all_themes)
    common_themes = [t for t, _ in theme_counter.most_common(5)]

    brand_dna = {
        "client_handle":    f"@{client_handle}",
        "analyzed_on":      date.today().isoformat(),
        "primary_colors":   top_primary if top_primary else None,
        "accent_colors":    top_accent if top_accent else None,
        "background_style": most_common_value("background_style"),
        "tone":             most_common_value("tone"),
        "typography_style": most_common_value("typography_style"),
        "layout_pattern":   most_common_value("layout_pattern"),
        "logo_position":    most_common_value("logo_position"),
        "common_themes":    common_themes if common_themes else None,
        "sample_post_urls": post_urls[:3],
        "confidence_score": round(confidence, 2),
    }

    if confidence < 0.4:
        brand_dna["needs_review"] = True
        brand_dna["flags"] = ["insufficient_data"]

    # Ensure null fields are never silently filled with guesses
    for key, value in brand_dna.items():
        if value == [] or value == "":
            brand_dna[key] = None

    return brand_dna


def extract_brand_dna(
    client_handle: str,
    scrape_result: dict,
    job_id: str,
) -> dict:
    """
    Main entry point. Analyzes all scraped images with Gemini, aggregates Brand DNA.
    Saves to .tmp/brand_dna/[handle]_brand_dna.json and returns the dict.
    """
    handle = client_handle.lstrip("@").lower()
    image_paths = [Path(p) for p in scrape_result.get("image_paths", [])]
    post_urls = [m.get("url", "") for m in scrape_result.get("post_metadata", [])]

    if not image_paths:
        raise ValueError(f"No images to analyze for @{handle}")

    print(f"[dna] Analyzing {len(image_paths)} images for @{handle} via Gemini...")

    model = _setup_gemini()
    analyses = []
    valid_count = 0

    for i, img_path in enumerate(image_paths):
        if not img_path.exists():
            print(f"[dna] Image not found: {img_path}")
            analyses.append(None)
            continue

        print(f"[dna] Analyzing image {i+1}/{len(image_paths)}: {img_path.name}")
        result = analyze_single_image(img_path, model)
        analyses.append(result)

        if result:
            valid_count += 1

        # Log each Gemini call
        log_api_call(
            job_id=job_id,
            service="gemini",
            model_or_endpoint=MODEL,
            call_type="vision_analysis",
            units_used=1,
            estimated_cost_usd=0.00,  # Free tier
            notes=f"Image {i+1}/{len(image_paths)}: {img_path.name}",
        )

    if valid_count < 3:
        print(f"[dna] Warning: only {valid_count} valid analyses. Brand DNA may be unreliable.")

    brand_dna = aggregate_brand_dna(analyses, handle, post_urls)

    # Save to cache
    BRAND_DNA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = BRAND_DNA_DIR / f"{handle}_brand_dna.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(brand_dna, f, indent=2, ensure_ascii=False)

    print(f"[dna] Brand DNA saved to {out_path} (confidence: {brand_dna['confidence_score']})")
    return brand_dna


def is_brand_dna_fresh(handle: str) -> bool:
    """Check if a Brand DNA cache exists and is less than CACHE_DAYS old."""
    from datetime import timedelta
    cache_days = int(os.getenv("BRAND_DNA_CACHE_DAYS", "7"))
    handle = handle.lstrip("@").lower()
    dna_path = BRAND_DNA_DIR / f"{handle}_brand_dna.json"

    if not dna_path.exists():
        return False

    try:
        with open(dna_path, "r", encoding="utf-8") as f:
            dna = json.load(f)
        analyzed_on = date.fromisoformat(dna["analyzed_on"])
        age = date.today() - analyzed_on
        return age.days < cache_days
    except (KeyError, ValueError, json.JSONDecodeError):
        return False


def load_brand_dna(handle: str) -> dict | None:
    """Load cached Brand DNA for a handle, or return None if not found."""
    handle = handle.lstrip("@").lower()
    dna_path = BRAND_DNA_DIR / f"{handle}_brand_dna.json"
    if not dna_path.exists():
        return None
    with open(dna_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    print("extract_brand_dna.py — run via orchestrate.py or with a scrape result dict.")
    print("Example: python orchestrate.py --handle @testhandle --brief 'Test' ...")
