# Workflow: Brand Analysis — Instagram Scrape → Brand DNA

## Objective
Extract a structured Brand DNA JSON from a client's public Instagram profile
by scraping their last 12 posts and analyzing each image with Google Gemini 1.5 Flash.

## Cache Check (ALWAYS run first)
1. Check `.tmp/brand_dna/[handle]_brand_dna.json` — does it exist?
2. Check `analyzed_on` date — if **less than 7 days ago**, SKIP all scraping and Gemini calls
3. Load cached Brand DNA and pass to prompt engineering stage

## Stage A: Instagram Scraping
| Step | Tool | Input | Output | Skip If |
|------|------|-------|--------|---------|
| 1 | `is_cache_fresh()` | Client handle | `(bool, path)` | Never |
| 2 | `scrape_profile()` | Handle + job_id | `.tmp/scraped_raw/[handle]/` | Cache < 7 days |
| 3 | Save `metadata.json` | Post data | `.tmp/scraped_raw/[handle]/metadata.json` | Using cache |

### Scraping Rules
- Backend: **Apify Instagram Scraper actor** (`apify/instagram-scraper`) — requires `APIFY_API_TOKEN` in `.env`
- Always scrape the **last 12 posts** — do not over-scrape (`resultsLimit: 12`)
- Rate limiting and bot detection are fully managed by Apify — no manual sleep/backoff needed
- On `PrivateAccountError` (0 items returned): stop immediately, emit error, ask client for manual images
- On `ProfileNotFoundError`: emit error with clear message

## Stage B: Brand DNA Extraction
| Step | Tool | Input | Output | Skip If |
|------|------|-------|--------|---------|
| 1 | `analyze_single_image()` | Each image + Gemini model | Per-image analysis dict | Never |
| 2 | `aggregate_brand_dna()` | All analyses + handle + post URLs | Brand DNA dict | Never |
| 3 | Save Brand DNA JSON | Brand DNA dict | `.tmp/brand_dna/[handle]_brand_dna.json` | Never |

### Gemini API Usage
- **Model:** `gemini-1.5-flash` (free tier: 1,500 req/day)
- **Calls per analysis:** 1 per image × up to 12 images = max 12 Gemini calls
- **All calls must be logged** to `.tmp/api_usage_log.csv` via `log_api_call()`
- If daily quota is exhausted: pause job, notify user, do not retry automatically

### Brand DNA Aggregation Rules
- `primary_colors`: Top 2 most frequent hex colors across all images
- `accent_colors`: Top 2 colors NOT already in primary_colors
- `background_style`, `tone`, `layout_pattern`: Most frequent valid value (majority vote)
- `typography_style`: Most frequent non-null value
- `logo_position`: Most frequent non-"not visible" value
- `common_themes`: Union of all themes, sorted by frequency (top 5)
- `confidence_score`: `valid_analyses / total_images` — penalize null responses

### Brand DNA Quality Rules
- **NEVER hallucinate field values** — if a field cannot be determined, mark it `null`
- If `confidence_score < 0.4`: add `"needs_review": true` and `"flags": ["insufficient_data"]`
- Minimum 3 valid image analyses required — if fewer, log a warning
- Gemini returns invalid JSON: log raw response, skip that image, continue with rest

## Brand DNA Schema
```json
{
  "client_handle": "@clientname",
  "analyzed_on": "YYYY-MM-DD",
  "primary_colors": ["#HEX1", "#HEX2"],
  "accent_colors": ["#HEX3"],
  "background_style": "dark gradient | solid white | textured | ...",
  "tone": "luxury minimal | vibrant playful | corporate clean | warm lifestyle | ...",
  "typography_style": "bold sans-serif | elegant serif | not visible | ...",
  "layout_pattern": "centered product | left-aligned text | full bleed image | ...",
  "logo_position": "top-center | bottom-right | not visible | ...",
  "common_themes": ["product closeup", "lifestyle", "seasonal offer"],
  "sample_post_urls": ["https://..."],
  "confidence_score": 0.85
}
```

## Edge Cases
| Situation | Action |
|-----------|--------|
| Profile is private | Raise `PrivateAccountError` → emit error → ask client for manual images |
| Profile not found | Raise `ProfileNotFoundError` → emit error with clear message |
| Fewer than 3 posts | Set `confidence_score` ≤ 0.3, flag `needs_review: true` |
| All images fail Gemini | Raise `ValueError` → set job status=failed |
| Gemini key not set | Raise `ValueError` with link to get free key |
| Apify token not set | Raise `ValueError` with link to get free token (apify.com) |
| Client posted many new posts since last analysis | Delete `.tmp/brand_dna/[handle]_brand_dna.json` manually and rerun |

## Output
- `.tmp/scraped_raw/[handle]/` — downloaded post images + metadata.json
- `.tmp/brand_dna/[handle]_brand_dna.json` — Brand DNA (cached for 7 days)
- `api_usage_log.csv` — Gemini call records (cost: $0.00 on free tier)
