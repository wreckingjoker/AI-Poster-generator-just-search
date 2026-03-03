# Workflow: Poster Generation — Prompts → Final PNGs

## Objective
Execute the generation pipeline: call Pollinations.ai → validate PNG → overlay logo
→ export with naming convention → update job log → notify UI.

## Run Order
| Step | Tool | Input | Output | Skip If |
|------|------|-------|--------|---------|
| 1 | `generate_variations()` | Prompts (v1–v3) + dimensions | `.tmp/generated/[handle]/[job_id]/poster_raw_v[n].png` | Cached PNGs exist |
| 2 | `batch_overlay()` | Raw PNGs + logo path + position | `.tmp/final_output/[handle]/[job_id]/poster_v[n]_overlaid.png` | Never |
| 3 | `export_final()` | Overlaid PNGs | Named PNGs + `job_summary.json` | Never |
| 4 | `update_job()` | Final paths + metadata | `jobs.csv` status=review | Never |
| 5 | `emit("complete")` | File paths | JSON line to Express stdout | Never |

## Pollinations.ai API Details
- **Endpoint:** `GET https://image.pollinations.ai/prompt/{encoded_prompt}?width=W&height=H&model=flux&nologo=true&seed={seed}`
- **Response:** PNG binary in response body (occasionally returns HTML error pages)
- **Generation time:** 30–90 seconds per image — normal, do not timeout early
- **Cost:** $0.00 — completely free, no API key required
- **Rate limiting:** Add 2-second sleep between requests as a courtesy

### PNG Validation (critical)
Always check response before saving:
```python
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
if response.content[:8] != PNG_MAGIC:
    # Likely an HTML error page — retry
```

### Retry Logic
1. Attempt 1 → if invalid PNG, wait 15 seconds
2. Attempt 2 → if still invalid, wait 15 seconds
3. Attempt 3 → if still failing, raise `GenerationError`

## Logo Overlay Rules
- **NEVER skip logo overlay** — never deliver an un-branded poster
- Logo size: 20% of poster width, proportional height
- Logo padding: 40px from edge
- Default position: `bottom-right` (override from Brand DNA `logo_position`)
- If Brand DNA says `"logo_position": "not visible"`: default to `bottom-right`
- Drop shadow: enabled by default (`LOGO_SHADOW=true` in `.env`)

## Output Naming Convention
```
[client_handle]_[brief_keyword]_[YYYY-MM-DD]_v[n].png
```
Example: `justsearch_summer_sale_2026-02-27_v1.png`

## Cache Check (Before Generation)
Before calling Pollinations, check:
```
.tmp/generated/[handle]/[job_id]/poster_raw_v[n].png
```
If the file exists and has `size > 1024 bytes` → skip generation, use cached file.
This prevents duplicate API calls on re-download requests.

## Quality Gates (all must pass before `status=review`)
- [ ] PNG magic bytes validated for each variation
- [ ] Logo visible and correctly positioned in final output
- [ ] File dimensions match requested size
- [ ] Naming convention applied correctly
- [ ] `job_summary.json` written to output directory
- [ ] `jobs.csv` updated to `status=review`
- [ ] All API calls logged to `api_usage_log.csv`

## Output Locations
```
.tmp/generated/[handle]/[job_id]/
  poster_raw_v1.png        # Raw Pollinations output
  poster_raw_v2.png
  poster_raw_v3.png

.tmp/final_output/[handle]/[job_id]/
  [handle]_[keyword]_[date]_v1.png   # Download-ready with logo
  [handle]_[keyword]_[date]_v2.png
  [handle]_[keyword]_[date]_v3.png
  job_summary.json                    # Full audit record
```

## Error Recovery
| Error | Recovery |
|-------|---------|
| Pollinations returns HTML after 3 retries | Raise `GenerationError`, job=failed, notify user to retry |
| Network timeout (>120s) | Same as above — log attempt, retry |
| Logo not found | Raise `LogoNotFoundError`, instruct user to upload logo via UI |
| Disk full / permission error | Log OS error, set job=failed |
