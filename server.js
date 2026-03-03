/**
 * server.js
 * Just Search AI Poster Generation — Express web server
 * Handles logo uploads, spawns Python pipeline, streams status, serves downloads.
 */

const express    = require('express');
const multer     = require('multer');
const { spawn }  = require('child_process');
const path       = require('path');
const fs         = require('fs');
const { v4: uuidv4 } = require('uuid');

const app     = express();
const PORT    = process.env.PORT || 3000;
const BASE_DIR = __dirname;

// ── Middleware ──────────────────────────────────────────────────────────────
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(BASE_DIR, 'public')));

// Serve final output files (thumbnails + downloads)
app.use('/outputs', express.static(path.join(BASE_DIR, '.tmp', 'final_output')));

// ── Logo upload storage (Multer) ────────────────────────────────────────────
const logoStorage = multer.diskStorage({
    destination: (req, file, cb) => {
        // Extract handle from the multipart form body
        const rawHandle = req.body.handle || 'unknown';
        const handle = rawHandle.replace(/^@/, '').replace(/[^a-z0-9_.]/gi, '').toLowerCase();
        const dir = path.join(BASE_DIR, 'clients', handle);
        fs.mkdirSync(dir, { recursive: true });
        cb(null, dir);
    },
    filename: (req, file, cb) => {
        // Always save as logo.png regardless of original name
        cb(null, 'logo.png');
    }
});

const upload = multer({
    storage: logoStorage,
    fileFilter: (req, file, cb) => {
        if (file.mimetype.startsWith('image/')) {
            cb(null, true);
        } else {
            cb(new Error('Logo must be an image file (PNG recommended)'));
        }
    },
    limits: { fileSize: 5 * 1024 * 1024 }  // 5MB max
});

// ── In-memory job state ─────────────────────────────────────────────────────
// jobs.csv is the persistent source of truth; this Map tracks ACTIVE jobs
const activeJobs = new Map();  // job_id → { status, messages, pid, files, error }

// ── Utility ─────────────────────────────────────────────────────────────────
function generateJobId() {
    const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const suffix = uuidv4().replace(/-/g, '').slice(0, 6).toUpperCase();
    return `JS-${today}-${suffix}`;
}

function ensureJobsCsv() {
    const csvPath = path.join(BASE_DIR, 'jobs.csv');
    if (!fs.existsSync(csvPath)) {
        const headers = 'job_id,client_handle,brief_summary,poster_size,brand_dna_version,prompt_used,variations,status,re_edit_count,total_cost_usd,created_at,approved_at,parent_job_id,output_paths\n';
        fs.writeFileSync(csvPath, headers, 'utf8');
    }
}

function readJobsCsv() {
    ensureJobsCsv();
    const csvPath = path.join(BASE_DIR, 'jobs.csv');
    const content = fs.readFileSync(csvPath, 'utf8').trim();
    const lines = content.split('\n').filter(l => l.trim());
    if (lines.length < 2) return [];
    const headers = lines[0].split(',');
    return lines.slice(1).reverse().map(line => {
        const values = line.split(',');
        return Object.fromEntries(headers.map((h, i) => [h.trim(), (values[i] || '').trim()]));
    });
}

function findOutputFile(jobId, filename) {
    // Security: sanitize filename to prevent path traversal
    const safe = path.basename(filename);
    const searchBase = path.join(BASE_DIR, '.tmp', 'final_output');
    if (!fs.existsSync(searchBase)) return null;
    // Walk: .tmp/final_output/[any_handle]/[jobId]/[filename]
    for (const handle of fs.readdirSync(searchBase)) {
        const candidate = path.join(searchBase, handle, jobId, safe);
        if (fs.existsSync(candidate)) return candidate;
    }
    return null;
}

// ── Routes ──────────────────────────────────────────────────────────────────

/**
 * POST /api/jobs
 * Start a new poster generation job.
 * Body (multipart/form-data):
 *   handle     — Instagram handle (required)
 *   brief      — Poster brief text (required)
 *   size       — Poster size key: 4:5 | 1:1 | story | landscape (default: 4:5)
 *   variations — Number of variations 1-3 (default: 3)
 *   logo       — Logo image file (optional if logo exists for handle)
 */
app.post('/api/jobs', upload.single('logo'), (req, res) => {
    const { handle, brief, size = '4:5', variations = '3' } = req.body;

    if (!handle || !handle.trim()) {
        return res.status(400).json({ error: 'Instagram handle is required' });
    }
    if (!brief || brief.trim().length < 10) {
        return res.status(400).json({ error: 'Poster brief must be at least 10 characters' });
    }

    const jobId        = generateJobId();
    const cleanHandle  = handle.replace(/^@/, '').toLowerCase();
    const logoPath     = req.file
        ? req.file.path
        : path.join(BASE_DIR, 'clients', cleanHandle, 'logo.png');
    const nVariations  = Math.min(Math.max(parseInt(variations) || 3, 1), 3);

    // Pre-register job in memory
    activeJobs.set(jobId, {
        status:   'pending',
        messages: [],
        pid:      null,
        files:    [],
        error:    null,
        handle:   cleanHandle,
        created:  new Date().toISOString(),
    });

    // Respond immediately — client will poll for status
    res.json({ job_id: jobId, status: 'pending' });

    // ── Spawn Python pipeline ───────────────────────────────────────────────
    const pythonArgs = [
        path.join(BASE_DIR, 'tools', 'orchestrate.py'),
        '--handle', handle,
        '--brief',  brief,
        '--job_id', jobId,
        '--logo_path', logoPath,
        '--size',   size,
        '--variations', String(nVariations),
    ];

    const child = spawn('python', pythonArgs, {
        cwd: BASE_DIR,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });

    const job = activeJobs.get(jobId);
    job.pid = child.pid;

    // Buffer for incomplete JSON lines
    let stdoutBuffer = '';

    child.stdout.on('data', (data) => {
        stdoutBuffer += data.toString();
        const lines = stdoutBuffer.split('\n');
        // Keep last partial line in buffer
        stdoutBuffer = lines.pop();

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) continue;
            try {
                const msg = JSON.parse(trimmed);
                job.messages.push(msg);
                console.log(`[job ${jobId}] stage=${msg.stage} status=${msg.status}`);

                if (msg.stage === 'complete') {
                    job.status = 'review';
                    job.files  = msg.files || [];
                } else if (msg.stage === 'error') {
                    job.status = 'failed';
                    job.error  = msg.message;
                } else {
                    job.status = `${msg.stage}:${msg.status}`;
                }
            } catch (_) {
                // Non-JSON stdout line (e.g. instaloader progress) — ignore
            }
        }
    });

    child.stderr.on('data', (data) => {
        // Python tracebacks — print to server console AND accumulate
        const text = data.toString();
        console.error(`[job ${jobId} stderr]`, text.trim());
        job.stderr = (job.stderr || '') + text;
    });

    child.on('close', (code) => {
        // Process any remaining buffer content
        if (stdoutBuffer.trim()) {
            try {
                const msg = JSON.parse(stdoutBuffer.trim());
                job.messages.push(msg);
            } catch (_) {}
        }

        if (job.status !== 'review' && job.status !== 'failed') {
            job.status = code === 0 ? 'review' : 'failed';
        }
        console.log(`[server] Job ${jobId} finished with exit code ${code}`);
    });

    child.on('error', (err) => {
        job.status = 'failed';
        job.error  = `Failed to start Python process: ${err.message}. Ensure Python is installed and in PATH.`;
        console.error(`[server] Failed to spawn Python for job ${jobId}:`, err);
    });
});

/**
 * GET /api/jobs/:id
 * Poll job status. Returns current state, messages, and download file paths.
 */
app.get('/api/jobs/:id', (req, res) => {
    const job = activeJobs.get(req.params.id);
    if (!job) {
        // Try to find in CSV for completed jobs from previous sessions
        const jobs = readJobsCsv();
        const csvJob = jobs.find(j => j.job_id === req.params.id);
        if (csvJob) {
            return res.json({
                job_id:   req.params.id,
                status:   csvJob.status,
                messages: [],
                files:    [],
                error:    null,
                from_csv: true,
            });
        }
        return res.status(404).json({ error: 'Job not found' });
    }

    res.json({
        job_id:   req.params.id,
        status:   job.status,
        messages: job.messages,
        files:    job.files,
        filenames: job.files.map(f => path.basename(f)),
        error:    job.error,
        stderr:   job.stderr || null,
        handle:   job.handle,
        created:  job.created,
    });
});

/**
 * GET /api/jobs
 * List all jobs from jobs.csv (newest first).
 */
app.get('/api/jobs', (req, res) => {
    try {
        const jobs = readJobsCsv();
        res.json(jobs);
    } catch (err) {
        res.status(500).json({ error: `Could not read job log: ${err.message}` });
    }
});

/**
 * GET /api/download/:jobId/:filename
 * Download a specific output file by job ID and filename.
 * Uses path.basename() to prevent path traversal attacks.
 */
app.get('/api/download/:jobId/:filename', (req, res) => {
    const { jobId, filename } = req.params;
    const found = findOutputFile(jobId, filename);
    if (!found) {
        return res.status(404).json({ error: 'File not found' });
    }
    res.download(found, path.basename(filename));
});

/**
 * PATCH /api/jobs/:id/approve
 * Mark a job as approved by the client.
 */
app.patch('/api/jobs/:id/approve', (req, res) => {
    const job = activeJobs.get(req.params.id);
    if (job) job.status = 'approved';
    // The Python job_tracker will also update the CSV
    res.json({ job_id: req.params.id, status: 'approved' });
});

/**
 * GET /api/health
 * Simple health check.
 */
app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', time: new Date().toISOString() });
});

// ── Error handler ───────────────────────────────────────────────────────────
app.use((err, req, res, next) => {
    if (err instanceof multer.MulterError) {
        if (err.code === 'LIMIT_FILE_SIZE') {
            return res.status(400).json({ error: 'Logo file must be under 5MB' });
        }
    }
    console.error('[server] Error:', err.message);
    res.status(500).json({ error: err.message });
});

// ── Start ───────────────────────────────────────────────────────────────────
ensureJobsCsv();

app.listen(PORT, () => {
    console.log(`\n╔══════════════════════════════════════════════╗`);
    console.log(`║  Just Search — AI Poster Generator           ║`);
    console.log(`║  Running at http://localhost:${PORT}           ║`);
    console.log(`╚══════════════════════════════════════════════╝\n`);
});
