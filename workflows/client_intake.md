# Workflow: Client Intake — Parsing Poster Briefs

## Objective
Convert a raw poster brief received via the web UI into a structured job record,
validate all inputs, and hand off to the brand analysis stage.

## Required Inputs
| Field | Source | Required |
|-------|--------|---------|
| Client Instagram handle | Web UI form | Yes |
| Raw brief text | Web UI textarea | Yes (≥10 chars) |
| Poster size | UI dropdown | No (default: 4:5) |
| Number of variations | UI select | No (default: 3) |
| Client logo | File upload or existing in clients/[handle]/ | Yes |

## Run Order
| Step | Tool/Action | Input | Output | Skip If |
|------|-------------|-------|--------|---------|
| 1 | Validate inputs | UI form data | 400 error or pass | Never |
| 2 | `parse_brief.py` → `parse_brief()` | Raw brief text | `brief` dict | Never |
| 3 | `save_brief()` | `brief` dict | `.tmp/prompts/[job_id]_brief.json` | Never |
| 4 | `job_tracker.py` → `create_job()` | Parsed fields | `jobs.csv` new row | Never |
| 5 | Confirm logo exists | `clients/[handle]/logo.png` | Logo path | Logo already in place |

## Edge Cases
| Situation | Action |
|-----------|--------|
| Brief under 10 characters | Return HTTP 400: "Please describe the poster in at least one sentence" |
| No logo uploaded, none cached | Return error: "Upload a client logo before generating" |
| Logo file > 5MB | Reject at Multer upload: "Logo must be under 5MB" |
| Handle not specified | Return HTTP 400: "Instagram handle is required" |
| Handle for a private account | Accept at intake — handle PrivateAccountError in Stage 2 (scraping) |
| Size not specified | Default to 4:5 (1080×1350) — most common Instagram format |
| Variations > 3 | Cap at 3 silently — never over-generate |

## What `parse_brief.py` Extracts
```json
{
  "offer_text":       "50% off summer collection",
  "product_name":     "Summer Dresses",
  "poster_size":      "4:5",
  "dimensions":       [1080, 1350],
  "deadline":         "2026-06-30",
  "brief_keyword":    "summer_sale",
  "tone_override":    "luxury minimal",
  "color_override":   null,
  "raw_brief":        "Original text as typed by user",
  "parse_confidence": 0.85
}
```

## Output
- `jobs.csv` — new row with `status=pending`
- `.tmp/prompts/[job_id]_brief.json` — structured brief for pipeline use

## Notes
- The `brief_keyword` field drives the output filename convention
- `tone_override` in the brief always overrides the Brand DNA tone
- `parse_confidence` < 0.5 means critical fields were missing — review output carefully
