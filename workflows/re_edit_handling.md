# Workflow: Re-Edit Handling — Client Change Requests

## Objective
Process client re-edit requests efficiently: change only what changed, reuse all cached
assets, create a child job linked to the parent, minimize cost and time.

## What Triggers a Re-Edit
Client reviews variations and requests changes such as:
- Color change: "Make it darker" / "Use our green instead"
- Tone change: "More luxury, less playful"
- Layout change: "I want a different arrangement"
- Variation selection: "I like v2 but with the logo from v1"
- Product focus: "Focus on the shoes, not the bag"
- Offer text: "Change '50% off' to 'Buy 1 Get 1'"

## Run Order
| Step | Action | Tool | Notes |
|------|--------|------|-------|
| 1 | Create child job | `job_tracker.create_job(parent_job_id=original_id)` | Links to parent for audit |
| 2 | Parse re-edit request | `parse_brief(text, mode="re_edit")` | Only changed fields |
| 3 | Load original brief | `.tmp/prompts/[parent_job_id]_brief.json` | Merge with changes |
| 4 | Merge briefs | Overlay changed fields only | Do NOT rebuild Brand DNA |
| 5 | Identify affected variations | Determine which v1/v2/v3 need regeneration | Compare diffs |
| 6 | Rebuild affected prompts | `build_prompt()` for affected indices | Use original Brand DNA |
| 7 | Regenerate only affected variations | `generate_single()` | Do NOT regenerate all |
| 8 | Re-overlay logo | `overlay_logo()` on new generations | |
| 9 | Export with re-edit suffix | `export_final(re_edit_n=m)` | `_re1.png`, `_re2.png` |
| 10 | Update parent job | `update_job(parent_id, re_edit_count=m)` | Increment counter |

## What Does NOT Get Rebuilt
- **Brand DNA** — never re-scraped or re-analyzed for a re-edit
- **Unaffected variations** — if only v1 changed, v2 and v3 stay unchanged
- **Cached scrape data** — Instagram images already downloaded

## Re-Edit Naming Convention
```
[handle]_[keyword]_[date]_v[n]_re[m].png
```
Examples:
- `brand_summer_sale_2026-02-27_v1_re1.png` — first re-edit of v1
- `brand_summer_sale_2026-02-27_v2_re2.png` — second re-edit of v2

## Identifying What Changed
| Change Type | Fields Affected | Variations to Regenerate |
|------------|----------------|------------------------|
| Color change | `color_override` | All 3 (colors run through all prompts) |
| Tone change | `tone_override` | All 3 |
| Product/offer text | `offer_text`, `product_name` | All 3 |
| Layout only | `layout_pattern` in brief | v2 (layout variation) only |
| Just v2 recompose | User specifies "just v2" | v2 only |
| Logo position | `logo_position` in client config | Re-overlay only, no regeneration |

## Cost Tracking
- Re-edits are child jobs: `parent_job_id` links them to the original
- Each re-edit increments `re_edit_count` on the parent job in `jobs.csv`
- Pollinations calls = $0.00 regardless
- Gemini calls = $0.00 (not used in re-edits — Brand DNA is reused)

## Limiting Re-Edit Cycles
After 3 re-edits on the same job, flag for human designer review:
- The automation may not be capturing the client's brand correctly
- Consider manually updating Brand DNA with correct values
- Check if Brand DNA `confidence_score` was low (< 0.5)
