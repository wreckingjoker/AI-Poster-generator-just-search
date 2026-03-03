"""
tools/scrape_instagram.py
Scrape the last N posts from a public Instagram profile using Apify Instagram Scraper.
Respects 7-day cache to avoid redundant scraping.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from apify_client import ApifyClient

sys.path.insert(0, str(Path(__file__).parent))
from job_tracker import log_api_call

BASE_DIR   = Path(__file__).resolve().parent.parent
SCRAPE_DIR = BASE_DIR / ".tmp" / "scraped_raw"

load_dotenv(BASE_DIR / ".env")

MAX_POSTS   = int(os.getenv("MAX_POSTS_PER_CLIENT", "12"))
CACHE_DAYS  = int(os.getenv("BRAND_DNA_CACHE_DAYS", "7"))
APIFY_TOKEN = os.getenv("APIFY_API_TOKEN", "")

APIFY_ACTOR_ID = "apify/instagram-scraper"


class PrivateAccountError(Exception):
    """Raised when the target Instagram profile is private."""
    pass


class ProfileNotFoundError(Exception):
    """Raised when the Instagram profile handle is not found."""
    pass


def clean_handle(handle: str) -> str:
    """Strip @ and lowercase."""
    return handle.lstrip("@").lower().strip()


def sanitize_filename(name: str) -> str:
    """Replace characters invalid in Windows filenames."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)


def is_cache_fresh(handle: str) -> tuple[bool, Path | None]:
    """
    Check .tmp/scraped_raw/[handle]/metadata.json for a recent scrape.
    Returns (is_fresh, metadata_path).
    """
    handle = clean_handle(handle)
    metadata_path = SCRAPE_DIR / handle / "metadata.json"

    if not metadata_path.exists():
        return False, None

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        scraped_at = datetime.fromisoformat(meta["scraped_at"])
        age = datetime.now(timezone.utc) - scraped_at
        if age < timedelta(days=CACHE_DAYS):
            return True, metadata_path
    except (KeyError, ValueError, json.JSONDecodeError):
        pass

    return False, None


def load_cached_scrape(handle: str) -> dict:
    """Load and return cached scrape metadata."""
    handle = clean_handle(handle)
    metadata_path = SCRAPE_DIR / handle / "metadata.json"
    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["from_cache"] = True
    return data


def _download_image(url: str, dest_path: Path) -> bool:
    """Download a single image from a URL to dest_path. Returns True on success."""
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"[scrape] Warning: failed to download image from {url}: {e}")
        return False


def scrape_profile(handle: str, job_id: str, max_posts: int = None, cache_days: int = None) -> dict:
    """
    Main entry point. Downloads last max_posts images from a public Instagram profile
    using the Apify Instagram Scraper actor.

    Returns:
    {
        "handle": str,
        "image_dir": str,
        "image_paths": [str],
        "post_metadata": [dict],
        "post_count": int,
        "scraped_at": str,
        "from_cache": bool
    }
    """
    handle = clean_handle(handle)
    effective_max  = max_posts  if max_posts  is not None else MAX_POSTS
    effective_days = cache_days if cache_days is not None else CACHE_DAYS

    # Check cache first
    metadata_path = SCRAPE_DIR / handle / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            scraped_at = datetime.fromisoformat(meta["scraped_at"])
            age = datetime.now(timezone.utc) - scraped_at
            if age < timedelta(days=effective_days):
                print(f"[scrape] Using cached data for @{handle} (< {effective_days} days old)")
                meta["from_cache"] = True
                return meta
        except (KeyError, ValueError, json.JSONDecodeError):
            pass

    # Validate Apify token
    if not APIFY_TOKEN or APIFY_TOKEN == "your_token_here":
        raise ValueError(
            "APIFY_API_TOKEN is not set in .env. "
            "Get your free token at https://apify.com -> Settings -> Integrations -> API tokens."
        )

    print(f"[scrape] Scraping @{handle} via Apify (last {effective_max} posts)...")

    dest_dir = SCRAPE_DIR / handle
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Run Apify Instagram Scraper actor
    client = ApifyClient(APIFY_TOKEN)
    run_input = {
        "directUrls": [f"https://www.instagram.com/{handle}/"],
        "resultsType": "posts",
        "resultsLimit": effective_max,
        "addParentData": False,
    }

    try:
        print(f"[scrape] Starting Apify actor run...")
        run = client.actor(APIFY_ACTOR_ID).call(run_input=run_input)
    except Exception as e:
        err_msg = str(e).lower()
        if "not found" in err_msg or "does not exist" in err_msg:
            raise ProfileNotFoundError(f"Instagram profile @{handle} not found.")
        raise RuntimeError(f"Apify actor run failed: {e}")

    if not run or run.get("status") not in ("SUCCEEDED",):
        status = run.get("status", "UNKNOWN") if run else "NO_RUN"
        raise RuntimeError(f"Apify actor run did not succeed (status: {status}).")

    # Fetch dataset items
    dataset_id = run.get("defaultDatasetId")
    items = list(client.dataset(dataset_id).iterate_items())

    if not items:
        # Private accounts or non-existent profiles return 0 items
        # Check run log for hints
        raise PrivateAccountError(
            f"No posts returned for @{handle}. The account may be private or does not exist. "
            "Ask the client to provide reference images manually."
        )

    print(f"[scrape] Apify returned {len(items)} posts for @{handle}.")

    image_paths = []
    post_metadata = []
    downloaded = 0

    for i, item in enumerate(items[:effective_max]):
        # Collect image URLs — carousel posts have `images`, single posts use `displayUrl`
        img_urls = item.get("images") or []
        if not img_urls and item.get("displayUrl"):
            img_urls = [item["displayUrl"]]

        # Use the first image (primary) for brand analysis
        primary_url = img_urls[0] if img_urls else None
        if not primary_url:
            print(f"[scrape] Skipping post {i+1}: no image URL found.")
            continue

        shortcode = sanitize_filename(item.get("shortCode", f"post_{i+1}"))
        ext = ".jpg"
        dest_path = dest_dir / f"{downloaded+1:02d}_{shortcode}{ext}"

        if _download_image(primary_url, dest_path):
            image_paths.append(str(dest_path))
            post_metadata.append({
                "shortcode": item.get("shortCode", ""),
                "url": item.get("url", f"https://www.instagram.com/p/{item.get('shortCode', '')}/"),
                "likes": item.get("likesCount", 0),
                "caption": (item.get("caption") or "")[:500],
                "timestamp": item.get("timestamp", ""),
                "index": downloaded + 1,
            })
            downloaded += 1
            print(f"[scrape] Downloaded post {downloaded}/{effective_max}: {item.get('shortCode', i+1)}")

    scraped_at = datetime.now(timezone.utc).isoformat()

    result = {
        "handle": handle,
        "image_dir": str(dest_dir),
        "image_paths": image_paths,
        "post_metadata": post_metadata,
        "post_count": downloaded,
        "scraped_at": scraped_at,
        "from_cache": False,
    }

    # Save metadata for caching
    with open(dest_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # Log the scrape call
    log_api_call(
        job_id=job_id,
        service="apify",
        model_or_endpoint=f"instagram.com/@{handle}",
        call_type="profile_scrape",
        units_used=downloaded,
        estimated_cost_usd=0.00,
        notes=f"Apify Instagram Scraper: {downloaded} posts from @{handle}",
    )

    print(f"[scrape] Done. {downloaded} images saved to {dest_dir}")
    return result


if __name__ == "__main__":
    handle = sys.argv[1] if len(sys.argv) > 1 else "instagram"
    try:
        result = scrape_profile(handle, "TEST-001")
        print(f"\nResult: {result['post_count']} posts scraped")
        print(f"Images: {result['image_paths'][:3]}")
    except PrivateAccountError as e:
        print(f"Private account: {e}")
    except ProfileNotFoundError as e:
        print(f"Not found: {e}")
    except ValueError as e:
        print(f"Config error: {e}")
