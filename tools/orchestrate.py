"""
tools/orchestrate.py
End-to-end pipeline runner. Called by the Express web server via child_process.spawn().

Emits JSON lines to stdout so Express can stream status updates to the UI.

Usage:
    python tools/orchestrate.py \\
        --handle @clienthandle \\
        --brief "50% off summer sale, 4:5 format" \\
        --job_id JS-20260227-ABC123 \\
        --logo_path "clients/clienthandle/logo.png" \\
        --size 4:5 \\
        --variations 3

stdout JSON line format:
    {"stage": "scraping", "status": "started", "job_id": "JS-..."}
    {"stage": "complete", "status": "done", "files": ["path1", "path2"]}
    {"stage": "error", "message": "...", "stage_failed": "scraping"}
"""

import argparse
import concurrent.futures
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

_SCRAPE_TIMEOUT = 90  # seconds before giving up on Instagram scraping

# Ensure tools/ is on path for relative imports
TOOLS_DIR = Path(__file__).resolve().parent
BASE_DIR  = TOOLS_DIR.parent
sys.path.insert(0, str(TOOLS_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from job_tracker       import create_job, update_job, log_api_call
from parse_brief       import parse_brief, save_brief, DIMENSION_MAP
from scrape_instagram  import scrape_profile, is_cache_fresh, load_cached_scrape, PrivateAccountError, ProfileNotFoundError
from extract_brand_dna import extract_brand_dna, is_brand_dna_fresh, load_brand_dna
from build_prompt      import build_all_prompts
from generate_poster   import generate_variations, GenerationError
from overlay_logo      import batch_overlay, resolve_logo, LogoNotFoundError
from export_png        import export_final


def emit(data: dict) -> None:
    """Write a JSON line to stdout. Express reads these for real-time status updates."""
    print(json.dumps(data, ensure_ascii=False), flush=True)


def _default_brand_dna(handle: str) -> dict:
    """Minimal brand DNA used when Instagram scraping is unavailable."""
    return {
        "client_handle":    f"@{handle}",
        "analyzed_on":      date.today().isoformat(),
        "primary_colors":   None,
        "accent_colors":    None,
        "background_style": "clean minimal",
        "tone":             "vibrant playful",
        "typography_style": "bold sans-serif",
        "layout_pattern":   "centered product",
        "logo_position":    "bottom-right",
        "common_themes":    ["product", "brand"],
        "sample_post_urls": [],
        "confidence_score": 0.1,
        "needs_review":     True,
        "flags":            ["no_instagram_data"],
    }


def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full poster generation pipeline."""
    job_id  = args.job_id
    handle  = args.handle.lstrip("@").lower()
    n_vars  = min(int(args.variations), 3)

    # ── Stage 1: Parse brief ─────────────────────────────────────────────────
    try:
        emit({"stage": "parse_brief", "status": "started", "job_id": job_id})
        brief = parse_brief(args.brief)
        # Honor the explicit size selection from the UI if present
        if args.size and args.size in DIMENSION_MAP:
            brief["poster_size"] = args.size
            brief["dimensions"]  = DIMENSION_MAP[args.size]
        save_brief(brief, job_id)
        update_job(job_id,
                   brief_summary=brief["offer_text"][:200],
                   poster_size=brief["poster_size"],
                   status="generating")
        emit({"stage": "parse_brief", "status": "done",
              "brief_keyword": brief["brief_keyword"],
              "dimensions": list(brief["dimensions"])})
    except ValueError as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": str(e), "stage_failed": "parse_brief", "job_id": job_id})
        sys.exit(1)

    # ── Stage 2: Instagram scraping (cache-aware, non-fatal) ────────────────
    _empty_scrape = {"handle": handle, "image_paths": [], "post_metadata": [], "post_count": 0}
    try:
        fresh, _ = is_cache_fresh(handle)
        if fresh:
            emit({"stage": "scraping", "status": "skipped", "reason": "cache_fresh"})
            scrape_result = load_cached_scrape(handle)
        else:
            emit({"stage": "scraping", "status": "started"})
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(scrape_profile, handle, job_id)
                try:
                    scrape_result = _future.result(timeout=_SCRAPE_TIMEOUT)
                    emit({"stage": "scraping", "status": "done",
                          "posts_found": scrape_result["post_count"]})
                except concurrent.futures.TimeoutError:
                    emit({"stage": "scraping", "status": "skipped",
                          "reason": "timeout",
                          "message": f"Scraping timed out after {_SCRAPE_TIMEOUT}s — continuing with default style"})
                    scrape_result = _empty_scrape

    except (PrivateAccountError, ProfileNotFoundError) as e:
        emit({"stage": "scraping", "status": "skipped",
              "reason": "account_issue", "message": str(e)})
        scrape_result = _empty_scrape

    except Exception as e:
        emit({"stage": "scraping", "status": "skipped",
              "reason": "error", "message": f"Scraping failed: {e}"})
        scrape_result = _empty_scrape

    # ── Stage 3: Brand DNA extraction (cache-aware, non-fatal) ──────────────
    try:
        if is_brand_dna_fresh(handle):
            emit({"stage": "brand_analysis", "status": "skipped", "reason": "cache_fresh"})
            brand_dna = load_brand_dna(handle)
        elif not scrape_result.get("image_paths"):
            emit({"stage": "brand_analysis", "status": "skipped",
                  "reason": "no_images", "message": "No Instagram images — using default brand style"})
            brand_dna = _default_brand_dna(handle)
        else:
            emit({"stage": "brand_analysis", "status": "started",
                  "images_to_analyze": len(scrape_result["image_paths"])})
            brand_dna = extract_brand_dna(handle, scrape_result, job_id)
            emit({"stage": "brand_analysis", "status": "done",
                  "confidence": brand_dna.get("confidence_score"),
                  "tone": brand_dna.get("tone"),
                  "needs_review": brand_dna.get("needs_review", False)})

    except Exception as e:
        emit({"stage": "brand_analysis", "status": "skipped",
              "reason": "error", "message": f"Brand analysis failed: {e} — using default style"})
        brand_dna = _default_brand_dna(handle)

    # Safety net: brand_dna must never be None at this point
    if not brand_dna:
        emit({"stage": "brand_analysis", "status": "skipped",
              "reason": "null_dna", "message": "brand_dna was None — using defaults"})
        brand_dna = _default_brand_dna(handle)

    # ── Stage 4: Prompt engineering ──────────────────────────────────────────
    try:
        emit({"stage": "prompt_engineering", "status": "started"})
        prompts = build_all_prompts(brand_dna, brief, job_id, n_vars)
        emit({"stage": "prompt_engineering", "status": "done",
              "count": len(prompts),
              "preview": prompts[0][:100] + "..." if prompts else ""})

    except Exception as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": f"Prompt engineering failed: {e}",
              "stage_failed": "prompt_engineering", "job_id": job_id})
        sys.exit(1)

    # ── Stage 5: Poster generation ───────────────────────────────────────────
    try:
        width, height = brief["dimensions"]
        emit({"stage": "generation", "status": "started", "variations": n_vars,
              "width": width, "height": height})
        gen_results = generate_variations(prompts, width, height, handle, job_id)
        emit({"stage": "generation", "status": "done", "count": len(gen_results)})

    except GenerationError as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": str(e), "stage_failed": "generation", "job_id": job_id})
        sys.exit(1)

    except Exception as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": f"Image generation failed: {e}",
              "stage_failed": "generation", "job_id": job_id})
        sys.exit(1)

    # ── Stage 6: Logo overlay ────────────────────────────────────────────────
    try:
        emit({"stage": "logo_overlay", "status": "started"})

        # Resolve logo path
        if args.logo_path and Path(args.logo_path).exists():
            logo_path = Path(args.logo_path)
        else:
            logo_path = resolve_logo(handle)

        generated_paths = [Path(r["output_path"]) for r in gen_results]
        logo_position   = brand_dna.get("logo_position") or "bottom-right"

        # Normalize logo_position — fall back if it's "not visible"
        if logo_position == "not visible":
            logo_position = "bottom-right"

        overlaid_paths = batch_overlay(generated_paths, logo_path, logo_position, job_id, handle)
        emit({"stage": "logo_overlay", "status": "done", "position": logo_position})

    except LogoNotFoundError as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": str(e), "stage_failed": "logo_overlay", "job_id": job_id})
        sys.exit(1)

    except Exception as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": f"Logo overlay failed: {e}",
              "stage_failed": "logo_overlay", "job_id": job_id})
        sys.exit(1)

    # ── Stage 7: Export final PNGs ───────────────────────────────────────────
    try:
        emit({"stage": "export", "status": "started"})
        created_at = datetime.now(timezone.utc).isoformat()

        job_summary_data = {
            "job_id":       job_id,
            "client_handle": handle,
            "created_at":   created_at,
            "brief_summary": brief.get("offer_text", ""),
            "poster_size":  brief.get("poster_size", "4:5"),
            "brand_dna":    brand_dna,
            "prompts":      prompts,
            "gen_results":  gen_results,
        }

        final_paths = export_final(
            overlaid_paths,
            handle,
            brief["brief_keyword"],
            job_id,
            job_summary_data,
        )

        emit({"stage": "export", "status": "done", "count": len(final_paths)})

    except Exception as e:
        update_job(job_id, status="failed")
        emit({"stage": "error", "message": f"Export failed: {e}",
              "stage_failed": "export", "job_id": job_id})
        sys.exit(1)

    # ── Stage 8: Update job log ──────────────────────────────────────────────
    update_job(
        job_id,
        status="review",
        brand_dna_version=brand_dna.get("analyzed_on", ""),
        prompt_used=prompts[0][:500] if prompts else "",
        variations=str(n_vars),
        output_paths=json.dumps([str(p) for p in final_paths]),
        approved_at="",
    )

    # ── Done ─────────────────────────────────────────────────────────────────
    emit({
        "stage":      "complete",
        "status":     "done",
        "job_id":     job_id,
        "files":      [str(p) for p in final_paths],
        "filenames":  [Path(p).name for p in final_paths],
        "variations": n_vars,
        "handle":     handle,
    })


def main():
    parser = argparse.ArgumentParser(description="Just Search AI Poster Generator Pipeline")
    parser.add_argument("--handle",     required=True,  help="Client Instagram handle (with or without @)")
    parser.add_argument("--brief",      required=True,  help="Raw poster brief text from the UI")
    parser.add_argument("--job_id",     required=True,  help="Job ID (generated by server.js)")
    parser.add_argument("--logo_path",  default="",     help="Path to client logo PNG")
    parser.add_argument("--size",       default="4:5",  help="Poster size key (4:5|1:1|story|landscape)")
    parser.add_argument("--variations", default="3",    help="Number of variations to generate (1-3)")

    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()
