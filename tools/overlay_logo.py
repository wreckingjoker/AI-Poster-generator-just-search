"""
tools/overlay_logo.py
Composite the client logo onto generated poster images using Pillow.
Supports 6 position options, proportional resizing, and optional drop shadow.
"""

import os
import sys
from pathlib import Path

from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR       = Path(__file__).resolve().parent.parent
FINAL_OUT_DIR  = BASE_DIR / ".tmp" / "final_output"

LOGO_SIZE_RATIO = 0.20  # Logo width = 20% of poster width
LOGO_PADDING_PX = 40    # Minimum margin from edge


class LogoNotFoundError(Exception):
    """Raised when client logo file is missing."""
    pass


def calculate_position(
    poster_w: int, poster_h: int,
    logo_w: int, logo_h: int,
    position: str,
) -> tuple[int, int]:
    """
    Calculate (x, y) pixel position for logo placement.
    Supports: top-center, top-left, top-right,
              bottom-center, bottom-left, bottom-right
    """
    pos_map = {
        "top-center":    ((poster_w - logo_w) // 2, LOGO_PADDING_PX),
        "top-left":      (LOGO_PADDING_PX, LOGO_PADDING_PX),
        "top-right":     (poster_w - logo_w - LOGO_PADDING_PX, LOGO_PADDING_PX),
        "bottom-center": ((poster_w - logo_w) // 2, poster_h - logo_h - LOGO_PADDING_PX),
        "bottom-left":   (LOGO_PADDING_PX, poster_h - logo_h - LOGO_PADDING_PX),
        "bottom-right":  (poster_w - logo_w - LOGO_PADDING_PX, poster_h - logo_h - LOGO_PADDING_PX),
    }

    if position not in pos_map:
        print(f"[overlay] Unknown position '{position}' — defaulting to bottom-right")
        position = "bottom-right"

    return pos_map[position]


def load_logo(logo_path: Path, target_width: int) -> Image.Image:
    """
    Load client logo, resize proportionally to LOGO_SIZE_RATIO * poster width.
    Converts to RGBA to preserve transparency.
    """
    if not logo_path.exists():
        raise LogoNotFoundError(
            f"Logo not found at: {logo_path}\n"
            f"Upload a logo via the web UI or place logo.png in clients/{logo_path.parent.name}/"
        )

    logo = Image.open(logo_path).convert("RGBA")

    new_width = int(target_width * LOGO_SIZE_RATIO)
    aspect = logo.height / logo.width
    new_height = int(new_width * aspect)

    logo = logo.resize((new_width, new_height), Image.LANCZOS)
    return logo


def add_drop_shadow(logo_img: Image.Image, blur_radius: int = 5) -> Image.Image:
    """
    Add a soft drop shadow behind the logo for visibility on any background.
    Returns a new RGBA image with shadow composited beneath the logo.
    """
    # Create shadow: black version of logo, blurred
    shadow = Image.new("RGBA", logo_img.size, (0, 0, 0, 0))
    # Extract alpha channel and create a black silhouette
    r, g, b, a = logo_img.split()
    black_fill = Image.new("RGBA", logo_img.size, (0, 0, 0, 180))
    shadow = Image.composite(black_fill, shadow, a)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))

    # Create canvas slightly larger to accommodate shadow offset
    offset = blur_radius * 2
    canvas_size = (logo_img.width + offset, logo_img.height + offset)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))

    # Paste shadow with offset, then logo on top
    canvas.paste(shadow, (offset // 2, offset // 2), shadow)
    canvas.paste(logo_img, (0, 0), logo_img)

    return canvas


def overlay_logo(
    poster_path: Path,
    logo_path: Path,
    position: str,
    output_path: Path,
    add_shadow: bool = True,
) -> Path:
    """
    Main function. Composites logo onto poster and saves result.

    Args:
        poster_path: Path to generated poster PNG
        logo_path: Path to client logo (PNG with transparency preferred)
        position: One of top/bottom + center/left/right
        output_path: Where to save the composited image
        add_shadow: Whether to add a soft drop shadow behind logo

    Returns output_path.
    """
    if not poster_path.exists():
        raise FileNotFoundError(f"Poster not found: {poster_path}")

    poster = Image.open(poster_path).convert("RGBA")
    poster_w, poster_h = poster.size

    logo = load_logo(logo_path, poster_w)

    if add_shadow and os.getenv("LOGO_SHADOW", "true").lower() != "false":
        logo = add_drop_shadow(logo)

    logo_w, logo_h = logo.size
    x, y = calculate_position(poster_w, poster_h, logo_w, logo_h, position)

    # Paste logo using its alpha channel as mask
    poster.paste(logo, (x, y), logo)

    # Convert back to RGB for PNG output (removes double alpha)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    poster.convert("RGB").save(output_path, "PNG", optimize=True)

    print(f"[overlay] Logo ({position}) applied -> {output_path}")
    return output_path


def batch_overlay(
    generated_paths: list[Path],
    logo_path: Path,
    position: str,
    job_id: str,
    client_handle: str,
) -> list[Path]:
    """
    Apply logo overlay to all generated variations.
    Saves results to .tmp/final_output/[handle]/[job_id]/
    Returns list of output paths.
    """
    handle  = client_handle.lstrip("@").lower()
    out_dir = FINAL_OUT_DIR / handle / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    overlaid_paths = []
    for i, gen_path in enumerate(generated_paths, start=1):
        out_path = out_dir / f"poster_v{i}_overlaid.png"
        result = overlay_logo(gen_path, logo_path, position, out_path)
        overlaid_paths.append(result)

    print(f"[overlay] Completed {len(overlaid_paths)} overlays")
    return overlaid_paths


def resolve_logo(handle: str) -> Path:
    """Find logo for a client handle. Checks clients/[handle]/logo.png"""
    handle = handle.lstrip("@").lower()
    candidates = [
        BASE_DIR / "clients" / handle / "logo.png",
        BASE_DIR / "clients" / handle / "logo.jpg",
        BASE_DIR / "clients" / handle / "logo.jpeg",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise LogoNotFoundError(
        f"No logo found for @{handle}. "
        f"Upload via the web UI or place logo.png in clients/{handle}/"
    )


if __name__ == "__main__":
    from PIL import Image as PILImage
    # Create a test poster and overlay a test logo
    test_poster = BASE_DIR / ".tmp" / "test_poster_overlay.png"
    test_output = BASE_DIR / ".tmp" / "test_output_overlay.png"

    PILImage.new("RGB", (1080, 1350), color=(30, 60, 120)).save(test_poster)
    print(f"Created test poster at {test_poster}")

    # Find any existing client logo to test with
    for logo in (BASE_DIR / "clients").rglob("logo.png"):
        print(f"Testing with logo: {logo}")
        result = overlay_logo(test_poster, logo, "bottom-right", test_output)
        print(f"Output: {result}")
        break
    else:
        print("No client logo found for testing. Add one to clients/[handle]/logo.png")
