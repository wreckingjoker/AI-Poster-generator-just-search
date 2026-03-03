# Just Search — AI Poster Generator

Automated Instagram-to-poster pipeline. Scrapes a client's Instagram, extracts their brand identity, and generates 2–3 ready-to-download poster variations using AI.

---

## How to Launch

### Option A — Double-click (easiest)
Double-click **`start.bat`** in Windows Explorer.

A console window will open and your browser will automatically go to `http://localhost:3000`.

### Option B — Terminal
```bash
node server.js
```
Then open `http://localhost:3000` in your browser.

To stop the server, close the console window or press `Ctrl + C`.

---

## How to Use

1. **Instagram Handle** — Enter the client's handle, e.g. `@brandname`
2. **Poster Brief** — Describe the poster in plain text:
   > "50% off summer sale, luxury feel, featuring our new dress collection"
3. **Poster Size** — Choose the format (default: Instagram Post 4:5 — 1080×1350)
4. **Variations** — How many poster options to generate (1–3, default: 3)
5. **Client Logo** — Upload a PNG logo (transparent background recommended). Logos are remembered per client handle.
6. Click **Generate Posters ✦** and wait 2–3 minutes

Progress updates appear live on the page. When done, download buttons appear for each variation.

---

## Where Files Are Saved

| Location | Contents |
|----------|---------|
| `.tmp/final_output/[handle]/[job_id]/` | Download-ready PNG posters |
| `.tmp/brand_dna/[handle]_brand_dna.json` | Extracted brand identity (cached 7 days) |
| `.tmp/scraped_raw/[handle]/` | Downloaded Instagram images |
| `jobs.csv` | Log of all jobs |

---

## Troubleshooting

**"Failed to start Python process"**
Python is not in your system PATH. Open a terminal and run `python --version` to check. If not found, install Python from python.org and add it to PATH.

**"Port 3000 is already in use"**
Another process is using port 3000. Either close it, or change the port in `.env`:
```
PORT=3001
```
Then visit `http://localhost:3001`.

**"Instagram profile is private"**
The automation can only scrape public profiles. Ask the client to either make their account temporarily public or manually upload 5–10 of their branded images.

**Brand DNA looks wrong / confidence score low**
The client's Instagram may have too few posts or inconsistent branding. You can delete `.tmp/brand_dna/[handle]_brand_dna.json` and re-run to force a fresh analysis.

**Logo not showing on poster**
Make sure the logo was uploaded via the form, or place it at `clients/[handle]/logo.png` (PNG with transparent background works best).
