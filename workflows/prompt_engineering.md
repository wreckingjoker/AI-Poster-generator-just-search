# Workflow: Prompt Engineering — Brand DNA + Brief → Generation Prompt

## Objective
Construct 2–3 distinct, precise Pollinations.ai Flux prompts that produce
brand-accurate poster variations with minimal re-edit cycles.

## Prompt Architecture (6 components, always in this order)
```
[STYLE DIRECTIVE] [SUBJECT] [BRAND AESTHETIC] [COLOR PALETTE] [BACKGROUND + LAYOUT] [TECHNICAL SPEC]
```

### Full Template
```
Professional high-quality marketing poster, showcasing [product_name],
[TONE_STYLE_MAP[tone]] aesthetic,
color palette of [primary_color_1] and [primary_color_2] with [accent_color] accents,
[BACKGROUND_STYLE_MAP[background_style]] background,
[layout_pattern] composition, [typography_style] typography feel,
commercial advertising photography, sharp focus, studio lighting,
no text overlays, no watermarks, no logos,
[width]x[height] format
```

### Maximum Length: 480 characters
Flux performs best under 500 characters. Truncate by shortening the middle
section — always preserve the technical spec at the end.

## Tone-to-Style Mapping
| Brand DNA Tone | Prompt Aesthetic |
|----------------|-----------------|
| luxury minimal | ultra-clean minimalist luxury, premium brand, elegant negative space |
| vibrant playful | bold colorful energetic, fun and youthful, dynamic composition |
| corporate clean | professional business, structured clean layout, confidence-inspiring |
| warm lifestyle | warm golden tones, authentic human moments, approachable brand story |
| bold energetic | high contrast dramatic, impact-first design, strong visual weight |
| soft feminine | pastel harmonious tones, graceful soft focus, delicate brand presence |

## 3-Variation Differentiation Strategy
| Variation | Layout Strategy | Color Strategy | Focus |
|-----------|----------------|---------------|-------|
| v1 | Brand DNA layout (default) | Primary colors lead | Standard composition |
| v2 | Alternative layout (opposite of v1) | Same colors | Different angle/arrangement |
| v3 | Close-up detail focus | Accent colors lead (swap roles) | Macro/intimate shot |

### Layout Alternatives
| v1 Layout | v2 Alternative |
|-----------|---------------|
| centered product | left-aligned composition |
| left-aligned text | right-aligned composition |
| right-aligned text | centered composition |
| full bleed image | layered composition with focal hierarchy |
| split layout | centered product focus |

## Rules
1. **NEVER include words/text to appear in the image** — Flux handles text poorly
2. **NEVER include the brand name** — logo overlay handles all branding
3. **Always end with technical spec** — dimensions + "no watermarks, no logos"
4. **`tone_override` from the brief always beats `tone` from Brand DNA**
5. **`color_override` from brief adds to prompt** — insert after palette line
6. **Null Brand DNA fields** — use sensible defaults from TONE_STYLE_MAP rather than including null strings

## Output Files
- `.tmp/prompts/[job_id]_v1_prompt.txt`
- `.tmp/prompts/[job_id]_v2_prompt.txt`
- `.tmp/prompts/[job_id]_v3_prompt.txt`

## Example Prompts

### v1 (luxury fashion client, summer sale)
```
Professional high-quality marketing poster, showcasing Summer Dresses,
ultra-clean minimalist luxury, premium brand, elegant negative space,
color palette of #1A1A2E and #E94560 with #F5F5F5 accents,
deep rich gradient background, centered product composition,
product closeup visual style, bold sans-serif typography feel,
commercial advertising photography, sharp focus, studio lighting,
no text overlays, no watermarks, no logos, 1080x1350 format
```

### v2 (same client, layout variant)
```
Professional high-quality marketing poster, showcasing Summer Dresses,
ultra-clean minimalist luxury, premium brand,
color palette of #1A1A2E and #E94560 with #F5F5F5 accents,
deep rich gradient background, left-aligned composition, strong leading lines,
bold sans-serif typography feel, commercial advertising photography, sharp focus,
no text overlays, no watermarks, no logos, 1080x1350 format
```

### v3 (accent-color-led, macro)
```
Professional high-quality marketing poster, showcasing Summer Dresses,
ultra-clean minimalist luxury, color palette of #F5F5F5 and #E94560 with #1A1A2E accents,
deep rich gradient background, close-up detail focus, macro product photography,
intimate composition, bold sans-serif typography feel,
commercial advertising photography, sharp focus, no text overlays, no logos, 1080x1350 format
```

## Saving Prompts
All prompts are saved to `.tmp/prompts/` for:
- Audit trail (what was generated and why)
- Re-edit base (modify only changed fields, not rebuild entire prompt)
- Self-improvement (compare approved vs rejected prompts over time)
