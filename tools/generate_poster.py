"""
tools/generate_poster.py
Generate marketing poster images via infip.pro Inference API (flux-schnell).
OpenAI-compatible API — returns JSON with image URL, then image is downloaded.
Free tier: requires a free API key (INFIP_API_KEY in .env).
Model: flux-schnell — free tier, fast generation.
Rate limits: 30 req/min, 1000 req/day on free tier.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from job_tracker import log_api_call

BASE_DIR       = Path(__file__).resolve().parent.parent
GENERATED_DIR  = BASE_DIR / ".tmp" / "generated"

load_dotenv(BASE_DIR / ".env")

INFIP_API_KEY     = os.getenv("INFIP_API_KEY", "")
INFIP_API_URL     = "https://api.infip.pro/v1/images/generations"
IMAGE_MODEL       = "flux-schnell"
REQUEST_TIMEOUT   = 120    # seconds
DOWNLOAD_TIMEOUT  = 60     # seconds for downloading the image URL
RETRY_ATTEMPTS    = 3
RETRY_DELAY       = 20     # seconds between retries
PNG_MAGIC         = b'\x89PNG\r\n\x1a\n'
INTER_REQUEST_SLEEP = 3    # polite delay between variations

# Size strings in WxH format for the infip.pro API
# Uses standard DALL-E-compatible sizes supported by infip.pro
_SIZE_MAP = {
    "portrait":  "1024x1792",   # 9:16 portrait
    "square":    "1024x1024",   # 1:1 square
    "story":     "1024x1792",   # 9:16 story (same as portrait)
    "landscape": "1792x1024",   # 16:9 landscape
}


class GenerationError(Exception):
    """Raised when infip.pro API fails after all retries."""
    pass


def is_valid_image(data: bytes) -> bool:
    """Check if bytes are a valid PNG or JPEG."""
    if len(data) < 8:
        return False
    if data[:8] == PNG_MAGIC:
        return True
    if data[:2] == b'\xff\xd8':
        return True
    return False


def _map_size(width: int, height: int) -> str:
    """
    Map arbitrary poster dimensions to supported size string for infip.pro.
    Returns size string like "1024x1024".
    """
    if width > height:
        return _SIZE_MAP["landscape"]
    elif width == height:
        return _SIZE_MAP["square"]
    else:
        ratio = height / width
        if ratio >= 1.7:
            return _SIZE_MAP["story"]
        return _SIZE_MAP["portrait"]


def _map_size_tuple(width: int, height: int) -> tuple[int, int]:
    """Return the mapped dimensions as a tuple (for metadata)."""
    size_str = _map_size(width, height)
    w, h = size_str.split("x")
    return int(w), int(h)


def generate_single(
    prompt: str,
    width: int,
    height: int,
    output_path: Path,
    job_id: str,
) -> dict:
    """
    Call infip.pro API (flux-schnell), download and save PNG to output_path.

    Returns metadata dict with output_path, size, prompt, dimensions, attempts.
    Raises GenerationError if all retries exhausted.
    """
    if not INFIP_API_KEY or INFIP_API_KEY == "your_infip_api_key_here":
        raise ValueError(
            "INFIP_API_KEY is not set in .env. "
            "Get your free key at: https://infip.pro/api-keys"
        )

    size_str = _map_size(width, height)
    os.makedirs(str(output_path.parent), exist_ok=True)

    print(f"[gen] Generating {size_str} poster via infip.pro ({IMAGE_MODEL})...")
    print(f"[gen] Prompt ({len(prompt)} chars): {prompt[:80]}...")

    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            print(f"[gen] Attempt {attempt}/{RETRY_ATTEMPTS}...")

            response = requests.post(
                INFIP_API_URL,
                headers={
                    "Authorization": f"Bearer {INFIP_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model":           IMAGE_MODEL,
                    "prompt":          prompt,
                    "n":               1,
                    "size":            size_str,
                    "response_format": "url",
                },
                timeout=REQUEST_TIMEOUT,
            )

            # ── Handle API error responses ───────────────────────────────────
            if response.status_code == 401:
                raise GenerationError(
                    "infip.pro: Invalid API key — check INFIP_API_KEY in .env. "
                    "Get your free key at https://infip.pro/api-keys"
                )

            if response.status_code == 429:
                raise GenerationError(
                    "infip.pro: Rate limit hit (30 req/min, 1000 req/day). "
                    "Wait a minute and retry."
                )

            if response.status_code == 503:
                last_error = "infip.pro: Service unavailable (503)"
                print(f"[gen] {last_error}")
                if attempt < RETRY_ATTEMPTS:
                    print(f"[gen] Waiting {RETRY_DELAY}s before retry...")
                    time.sleep(RETRY_DELAY)
                continue

            if response.status_code != 200:
                raise GenerationError(
                    f"infip.pro API returned HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )

            # ── Parse JSON response ──────────────────────────────────────────
            try:
                body = response.json()
            except Exception:
                raise GenerationError(
                    f"infip.pro returned non-JSON response: {response.text[:200]}"
                )

            if "error" in body:
                err_msg = body["error"] if isinstance(body["error"], str) else str(body["error"])
                last_error = f"infip.pro error: {err_msg}"
                print(f"[gen] {last_error}")
                if attempt < RETRY_ATTEMPTS:
                    print(f"[gen] Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                continue

            data = body.get("data", [])
            if not data or not data[0].get("url"):
                raise GenerationError(
                    f"infip.pro returned no image URL. Response: {str(body)[:200]}"
                )

            image_url = data[0]["url"]
            print(f"[gen] Downloading image from URL...")

            # ── Download the image ───────────────────────────────────────────
            img_response = requests.get(image_url, timeout=DOWNLOAD_TIMEOUT)
            if img_response.status_code != 200:
                raise GenerationError(
                    f"Failed to download image from URL (HTTP {img_response.status_code})"
                )

            image_data = img_response.content

            if not is_valid_image(image_data):
                snippet = image_data[:200].decode("utf-8", errors="replace")
                raise GenerationError(
                    f"Downloaded content is not a valid image. Got: {snippet[:150]}"
                )

            # Save the image
            output_path.write_bytes(image_data)
            print(f"[gen] Saved to {output_path} ({len(image_data)//1024}KB)")

            log_api_call(
                job_id=job_id,
                service="infip",
                model_or_endpoint=IMAGE_MODEL,
                call_type="image_generation",
                units_used=1,
                estimated_cost_usd=0.00,
                notes=f"size={size_str}, attempt={attempt}",
            )

            return {
                "output_path":     str(output_path),
                "size":            size_str,
                "prompt":          prompt,
                "width":           width,
                "height":          height,
                "file_size_bytes": len(image_data),
                "attempts":        attempt,
            }

        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_error = f"Network error: {e}"
            print(f"[gen] Attempt {attempt} failed: {last_error}")
        except GenerationError as e:
            last_error = str(e)
            print(f"[gen] Attempt {attempt} failed: {last_error}")
            # Don't retry hard errors (bad key, rate limit)
            if "Invalid API key" in last_error or "Rate limit" in last_error:
                break
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            print(f"[gen] Attempt {attempt} failed: {last_error}")

        if attempt < RETRY_ATTEMPTS:
            print(f"[gen] Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    raise GenerationError(
        f"Failed to generate poster after {RETRY_ATTEMPTS} attempts. "
        f"Last error: {last_error}"
    )


def generate_variations(
    prompts: list[str],
    width: int,
    height: int,
    client_handle: str,
    job_id: str,
) -> list[dict]:
    """
    Generate 2–3 poster variations. Saves to .tmp/generated/[handle]/[job_id]/
    Returns list of metadata dicts.
    """
    handle  = client_handle.lstrip("@").lower()
    out_dir = GENERATED_DIR / handle / job_id
    os.makedirs(str(out_dir), exist_ok=True)

    results = []

    for i, prompt in enumerate(prompts, start=1):
        out_path = out_dir / f"poster_raw_v{i}.png"

        # Use cached image if already generated
        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"[gen] v{i} already exists — using cached: {out_path}")
            size_str = _map_size(width, height)
            results.append({
                "output_path":     str(out_path),
                "size":            size_str,
                "prompt":          prompt,
                "width":           width,
                "height":          height,
                "file_size_bytes": out_path.stat().st_size,
                "attempts":        0,
            })
            continue

        result = generate_single(prompt, width, height, out_path, job_id)
        results.append(result)

        if i < len(prompts):
            print(f"[gen] Waiting {INTER_REQUEST_SLEEP}s before next generation...")
            time.sleep(INTER_REQUEST_SLEEP)

    print(f"[gen] Generated {len(results)} poster variation(s)")
    return results


if __name__ == "__main__":
    test_prompt = (
        "Professional marketing poster for a summer fashion collection. "
        "Display the text \"SUMMER SALE — 50% OFF\" prominently in bold. "
        "Luxury minimal aesthetic, dark gradient background, centered composition. "
        "Studio-quality lighting, commercial advertising quality."
    )
    result = generate_single(
        test_prompt, 1080, 1350,
        Path(".tmp/test_poster.png"),
        "TEST-001"
    )
    print("Generated:", result)
