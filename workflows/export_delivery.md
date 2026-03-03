# Workflow: Export & Delivery — Final PNG Download

## Objective
Make completed poster PNGs available for download via the web UI with correct
naming, metadata, and client-facing presentation.

## File Locations
| File | Location | Purpose |
|------|----------|---------|
| Final PNGs | `.tmp/final_output/[handle]/[job_id]/[filename].png` | Client deliverables |
| Job summary | `.tmp/final_output/[handle]/[job_id]/job_summary.json` | Audit record |
| Download URL | `GET /api/download/[job_id]/[filename]` | Served by Express |
| Thumbnail URL | `/outputs/[handle]/[job_id]/[filename]` | Served as static file |

## Delivery Steps
| Step | Action | Who |
|------|--------|-----|
| 1 | Pipeline emits `{"stage":"complete","files":[...]}` | `orchestrate.py` |
| 2 | Express sets `job.status = "review"` | `server.js` |
| 3 | UI polls and detects `status === "review"` | `app.js` |
| 4 | UI renders thumbnail grid with download buttons | `app.js` |
| 5 | User downloads preferred variation(s) | Browser |
| 6 | User marks job approved | UI button → `PATCH /api/jobs/:id/approve` |
| 7 | `jobs.csv` updated to `status=approved` | `job_tracker.update_job()` |

## Naming Convention
```
[client_handle_no_at]_[brief_keyword]_[YYYY-MM-DD]_v[n].png
```
- `client_handle`: @ stripped, lowercase, alphanumeric + underscore only
- `brief_keyword`: 1–2 word slug from the offer text (e.g. "summer_sale")
- `YYYY-MM-DD`: Generation date
- `v[n]`: Variation number (v1, v2, v3)

Examples:
```
justsearch_summer_sale_2026-02-27_v1.png
clientbrand_product_launch_2026-03-15_v2.png
```

## `job_summary.json` Contents
```json
{
  "job_id": "JS-20260227-ABC123",
  "client_handle": "justsearch",
  "created_at": "2026-02-27T10:30:00Z",
  "brief_summary": "50% off summer collection",
  "poster_size": "4:5",
  "brand_dna_version": "2026-02-27",
  "brand_dna_confidence": 0.85,
  "prompts_used": ["v1 prompt...", "v2 prompt...", "v3 prompt..."],
  "seeds_used": [123456, 789012, 345678],
  "output_files": ["justsearch_summer_sale_2026-02-27_v1.png", "..."],
  "generation_cost_usd": 0.00,
  "gemini_calls_made": 12,
  "image_dimensions": {"width": 1080, "height": 1350}
}
```

## Quality Checklist (Before Marking Delivered)
- [ ] PNG opens correctly (not corrupted)
- [ ] Dimensions match requested size (e.g. 1080×1350 for 4:5)
- [ ] Client logo is visible and correctly positioned
- [ ] Logo is not covering key design elements
- [ ] Filename follows naming convention exactly
- [ ] `job_summary.json` written and readable
- [ ] `jobs.csv` row updated to `status=review`

## File Retention Policy
- `.tmp/` is **regeneratable** — do not treat as permanent storage
- For permanent archiving: copy approved files to a permanent folder manually
- `jobs.csv` and `.tmp/brand_dna/` should be backed up periodically
- **Never send un-overlaid files** from `.tmp/generated/` to clients

## Handling Download Failures
| Situation | Resolution |
|-----------|-----------|
| File not found (404) | Check `.tmp/final_output/[handle]/[job_id]/` — job may still be running |
| File appears corrupted | Delete from `.tmp/generated/` and re-run generation stage only |
| Wrong dimensions | Check `brief["dimensions"]` was correctly parsed — re-run if needed |
| Logo missing from output | `LogoNotFoundError` should have been caught earlier — check logo path |
