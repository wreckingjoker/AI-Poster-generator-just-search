"""
tools/export_png.py
Apply naming convention, write job_summary.json, prepare download-ready PNGs.
"""

import json
import re
import shutil
from datetime import date
from pathlib import Path

BASE_DIR       = Path(__file__).resolve().parent.parent
FINAL_OUT_DIR  = BASE_DIR / ".tmp" / "final_output"


def make_filename(
    client_handle: str,
    brief_keyword: str,
    date_str: str,
    variation_n: int,
    re_edit_n: int = 0,
) -> str:
    """
    Implements naming convention:
    [handle]_[keyword]_[YYYY-MM-DD]_v[n].png
    or for re-edits: [handle]_[keyword]_[YYYY-MM-DD]_v[n]_re[m].png

    Example: justsearch_summer_sale_2026-02-27_v1.png
    """
    handle  = client_handle.lstrip("@").lower()
    handle  = re.sub(r"[^a-z0-9_]", "", handle)
    keyword = re.sub(r"[^a-z0-9_]", "", brief_keyword.lower())
    date_s  = re.sub(r"[^0-9\-]", "", date_str)

    if re_edit_n > 0:
        return f"{handle}_{keyword}_{date_s}_v{variation_n}_re{re_edit_n}.png"
    return f"{handle}_{keyword}_{date_s}_v{variation_n}.png"


def export_final(
    overlaid_paths: list[Path],
    client_handle: str,
    brief_keyword: str,
    job_id: str,
    job_summary_data: dict,
    re_edit_n: int = 0,
) -> list[str]:
    """
    Copy overlaid files with proper naming convention.
    Writes job_summary.json to same directory.
    Returns list of final file paths for the web UI download links.
    """
    handle  = client_handle.lstrip("@").lower()
    today   = date.today().isoformat()
    out_dir = FINAL_OUT_DIR / handle / job_id
    out_dir.mkdir(parents=True, exist_ok=True)

    final_paths = []

    for i, overlaid_path in enumerate(overlaid_paths, start=1):
        filename = make_filename(handle, brief_keyword, today, i, re_edit_n)
        dest     = out_dir / filename

        if overlaid_path != dest:
            shutil.copy2(overlaid_path, dest)

        final_paths.append(str(dest))
        print(f"[export] Exported: {filename}")

    # Write job_summary.json
    summary_path = write_job_summary(job_summary_data, final_paths, out_dir)
    print(f"[export] Job summary: {summary_path}")

    return final_paths


def write_job_summary(
    job_data: dict,
    final_output_files: list[str],
    output_dir: Path,
) -> Path:
    """
    Writes job_summary.json to the output directory.
    Contains all metadata needed for audit and reproduction.
    """
    gen_results = job_data.get("gen_results", [])
    brand_dna   = job_data.get("brand_dna", {})
    prompts     = job_data.get("prompts", [])

    summary = {
        "job_id":             job_data.get("job_id"),
        "client_handle":      job_data.get("client_handle"),
        "created_at":         job_data.get("created_at"),
        "brief_summary":      job_data.get("brief_summary"),
        "poster_size":        job_data.get("poster_size"),
        "brand_dna_version":  brand_dna.get("analyzed_on"),
        "brand_dna_confidence": brand_dna.get("confidence_score"),
        "prompts_used":       prompts,
        "seeds_used":         [r.get("seed") for r in gen_results],
        "output_files":       [Path(p).name for p in final_output_files],
        "generation_cost_usd": 0.00,  # Pollinations is free
        "gemini_calls_made":  len(gen_results),
        "image_dimensions":   {
            "width":  gen_results[0].get("width")  if gen_results else None,
            "height": gen_results[0].get("height") if gen_results else None,
        },
    }

    out_path = output_dir / "job_summary.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return out_path


if __name__ == "__main__":
    # Test filename convention
    tests = [
        ("@justsearch", "summer_sale", "2026-02-27", 1, 0),
        ("@BrandName!", "launch event", "2026-02-27", 2, 0),
        ("@brand",      "promo",       "2026-02-27", 1, 2),
    ]
    for args in tests:
        print(make_filename(*args))
