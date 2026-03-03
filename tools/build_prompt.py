"""
tools/build_prompt.py
Convert Brand DNA + parsed brief into precise prompt strings for nano-banana (Gemini image generation).
Gemini understands natural language and can accurately render text on images.
No API calls — purely deterministic prompt construction.
"""

import json
import textwrap
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

MAX_PROMPT_CHARS = 1400  # Gemini handles detailed natural language prompts well

TONE_STYLE_MAP = {
    "luxury minimal":  "ultra-clean minimalist luxury, premium brand, elegant negative space, sophisticated",
    "vibrant playful": "bold colorful energetic, fun and youthful, dynamic composition, eye-catching",
    "corporate clean": "professional business, structured clean layout, confidence-inspiring, trustworthy",
    "warm lifestyle":  "warm golden tones, authentic human moments, approachable brand story, inviting",
    "bold energetic":  "high contrast dramatic, impact-first design, strong visual weight, powerful",
    "soft feminine":   "pastel harmonious tones, graceful soft focus, delicate brand presence, gentle",
    None:              "modern professional design, clean aesthetic, commercial quality",
}

BACKGROUND_STYLE_MAP = {
    "dark gradient":   "deep rich gradient background, dramatic depth and atmosphere",
    "solid white":     "crisp white background, clean product-first presentation",
    "solid black":     "bold black background, luxury high-contrast",
    "textured":        "subtle textured background, artisan quality feel",
    "lifestyle photo": "real environment contextual setting, immersive lifestyle scene",
    "product flat lay":"flat lay arrangement, overhead perspective, styled product display",
    "colorful gradient":"vibrant gradient background, energetic color wash",
    None:              "clean professional background",
}

LAYOUT_ALTERNATIVES = {
    "centered product":     "left-aligned composition, strong leading lines",
    "left-aligned text":    "right-aligned composition, balanced visual weight",
    "right-aligned text":   "centered composition, symmetrical layout",
    "full bleed image":     "layered composition with clear focal hierarchy",
    "split layout":         "centered product focus, hero image composition",
    "text overlay":         "product-forward minimal layout",
}


def apply_color_description(primary: list, accent: list) -> str:
    """Format colors into a prompt-friendly description."""
    parts = []
    if primary:
        if len(primary) >= 2:
            parts.append(f"color palette of {primary[0]} and {primary[1]}")
        else:
            parts.append(f"color palette of {primary[0]}")
    if accent and len(accent) >= 1:
        parts.append(f"with {accent[0]} accent tones")
    return ", ".join(parts) if parts else "harmonious brand color palette"


def get_variation_layout(brand_dna: dict, variation_index: int) -> str:
    """Returns layout description that differs per variation."""
    base_layout = brand_dna.get("layout_pattern") or "centered product"

    if variation_index == 1:
        return base_layout
    elif variation_index == 2:
        return LAYOUT_ALTERNATIVES.get(base_layout, "diagonal dynamic composition")
    else:  # v3
        return "close-up detail focus, macro product photography, intimate composition"


def get_variation_color_role(brand_dna: dict, variation_index: int) -> tuple[list, list]:
    """For v3, swap primary and accent color roles."""
    primary = brand_dna.get("primary_colors") or []
    accent  = brand_dna.get("accent_colors") or []

    if variation_index == 3 and accent:
        return accent, primary  # Swap roles
    return primary, accent


def build_prompt(brand_dna: dict, brief: dict, variation_index: int = 1) -> str:
    """
    Constructs a natural language prompt for nano-banana (Gemini image generation).

    Gemini understands full sentences and can accurately render text inside images,
    so the offer text is included as a display instruction rather than blocked.

    variation_index:
        1 = Standard — faithful to Brand DNA layout
        2 = Alternative layout variant
        3 = Accent color-led, close-up focus variant

    Returns the prompt string (max MAX_PROMPT_CHARS chars).
    """
    # --- Extract brand data ---
    tone       = brand_dna.get("tone")
    bg_style   = brand_dna.get("background_style")
    layout     = get_variation_layout(brand_dna, variation_index)
    typography = brand_dna.get("typography_style") or "modern sans-serif"
    themes     = brand_dna.get("common_themes") or []

    primary_colors, accent_colors = get_variation_color_role(brand_dna, variation_index)

    # --- Extract brief data ---
    offer_text   = brief.get("offer_text") or ""
    product_name = brief.get("product_name") or ""
    width, height = brief.get("dimensions", (1080, 1350))

    effective_tone = brief.get("tone_override") or tone

    # --- Build components ---
    subject    = product_name if product_name else (offer_text[:80] if offer_text else "a premium product")
    aesthetic  = TONE_STYLE_MAP.get(effective_tone, TONE_STYLE_MAP[None])
    background = BACKGROUND_STYLE_MAP.get(bg_style, BACKGROUND_STYLE_MAP[None])
    color_desc = apply_color_description(primary_colors, accent_colors)
    theme_str  = f" with a {themes[0]} visual theme" if themes else ""

    # Offer text block — Gemini can accurately render text on images
    offer_block = ""
    if offer_text:
        offer_block = (
            f"Display the following promotional text prominently and legibly on the poster "
            f"using large bold {typography}: \"{offer_text}\". "
        )

    # Assemble as natural language instructions
    prompt = (
        f"Create a professional marketing poster for {subject}{theme_str}. "
        f"Visual style: {aesthetic}. "
        f"Use a {color_desc}. "
        f"Background: {background}. "
        f"Composition: {layout} layout. "
        f"{offer_block}"
        f"Typography style: {typography}. "
        f"Studio-quality lighting, sharp focus, photorealistic commercial advertising quality. "
        f"Do not include any additional logos, watermarks, or brand marks. "
        f"Optimised for {width}x{height} pixel format."
    )

    # Trim if over limit, preserving the technical tail
    if len(prompt) > MAX_PROMPT_CHARS:
        tech_suffix = f" Studio lighting, sharp focus, commercial quality. {width}x{height} format."
        prompt = prompt[:MAX_PROMPT_CHARS - len(tech_suffix)] + tech_suffix

    return prompt


def save_prompt(prompt: str, job_id: str, variation_index: int) -> Path:
    """Save prompt to .tmp/prompts/[job_id]_v[n]_prompt.txt"""
    out_dir = BASE_DIR / ".tmp" / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}_v{variation_index}_prompt.txt"
    out_path.write_text(prompt, encoding="utf-8")
    return out_path


def build_all_prompts(brand_dna: dict, brief: dict, job_id: str, n_variations: int = 3) -> list[str]:
    """Build and save all variation prompts. Returns list of prompt strings."""
    prompts = []
    for i in range(1, min(n_variations, 3) + 1):
        prompt = build_prompt(brand_dna, brief, i)
        save_prompt(prompt, job_id, i)
        prompts.append(prompt)
        print(f"[prompt] v{i} ({len(prompt)} chars): {prompt[:80]}...")
    return prompts


if __name__ == "__main__":
    # Test with a mock Brand DNA
    mock_dna = {
        "client_handle": "@testbrand",
        "analyzed_on": "2026-02-27",
        "primary_colors": ["#1A1A2E", "#E94560"],
        "accent_colors": ["#F5F5F5"],
        "background_style": "dark gradient",
        "tone": "luxury minimal",
        "typography_style": "bold sans-serif",
        "layout_pattern": "centered product",
        "logo_position": "bottom-right",
        "common_themes": ["product closeup", "lifestyle"],
        "confidence_score": 0.85,
    }
    mock_brief = {
        "offer_text": "50% off summer collection",
        "product_name": "Summer Dresses",
        "dimensions": (1080, 1350),
        "tone_override": None,
    }
    for i in range(1, 4):
        p = build_prompt(mock_dna, mock_brief, i)
        print(f"\nVariation {i} ({len(p)} chars):\n{p}")
