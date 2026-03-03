/* ============================================================
   Just Search — AI Poster Generator
   app.js  —  Vanilla JS frontend logic
   ============================================================ */

'use strict';

/* ── Module-level state ──────────────────────────────────────── */
let currentJobId   = null;
let pollInterval   = null;
let currentHandle  = null;

/* ── Stage → step index map (0-based, 7 total steps) ─────────── */
const STAGE_STEP = {
  'parse_brief':        0,
  'scraping':           1,
  'brand_analysis':     2,
  'prompt_engineering': 3,
  'generation':         4,
  'logo_overlay':       5,
  'export':             6,
};

/* ── Human-readable stage messages ──────────────────────────── */
function getStageMessage(status, handle) {
  const h = handle ? `@${handle.replace(/^@/, '')}` : '';

  const map = {
    'parse_brief:started':        'Step 1: Parsing brief...',
    'scraping:started':           `Step 2: Scraping Instagram (${h})...`,
    'scraping:skipped':           'Step 2: Using cached profile data',
    'brand_analysis:started':     'Step 3: Analyzing brand identity...',
    'brand_analysis:skipped':     'Step 3: Using cached brand analysis',
    'prompt_engineering:started': 'Step 4: Engineering prompts...',
    'generation:started':         'Step 5: Generating poster variations...',
    'logo_overlay:started':       'Step 6: Applying logo overlay...',
    'export:started':             'Step 7: Exporting final PNGs...',
    'complete:done':               '✓ Done! Your posters are ready.',
    'error':                       '✗ Error occurred.',
  };

  return map[status] || status;
}

/* ============================================================
   SUBMIT FORM
   ============================================================ */
async function submitForm(e) {
  e.preventDefault();

  // Clear previous results / state
  clearResults();
  stopPolling();

  const form      = document.getElementById('poster-form');
  const submitBtn = document.getElementById('submit-btn');

  // Basic validation
  const handle = document.getElementById('instagram-handle').value.trim();
  const brief  = document.getElementById('poster-brief').value.trim();

  if (!handle) { showToast('Please enter a client Instagram handle.', 'warning'); return; }
  if (!brief)  { showToast('Please enter a poster brief.', 'warning');            return; }

  currentHandle = handle.replace(/^@/, '');

  // Build FormData
  const fd = new FormData(form);

  // Disable form while running
  submitBtn.disabled = true;
  submitBtn.textContent = 'Submitting…';

  try {
    const res  = await fetch('/api/jobs', { method: 'POST', body: fd });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.error || data.message || `Server error ${res.status}`);
    }

    const jobId = data.job_id || data.id || data.jobId;
    if (!jobId) throw new Error('No job ID returned from server.');

    currentJobId = jobId;

    // Show status card
    document.getElementById('job-id-value').textContent = jobId;
    showSection('status-section');
    updateStatusText('Initialising job…');

    showToast(`Job ${jobId} started!`, 'info');

    // Begin polling
    pollJobStatus(jobId);

  } catch (err) {
    console.error('submitForm error:', err);
    showToast(`Failed to submit job: ${err.message}`, 'error');
    submitBtn.disabled  = false;
    submitBtn.innerHTML = 'Generate Posters &#10022;';
  }
}

/* ============================================================
   POLL JOB STATUS
   ============================================================ */
function pollJobStatus(jobId) {
  stopPolling(); // safety: clear any existing interval

  pollInterval = setInterval(async () => {
    try {
      const res  = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`);
      const data = await res.json();
      console.log('[poll]', data.status, data);

      if (!res.ok) {
        throw new Error(data.error || `Server error ${res.status}`);
      }

      handleJobUpdate(data);

    } catch (err) {
      console.error('pollJobStatus error:', err);
      // Don't stop polling on transient network errors — just log
    }
  }, 3000);
}

/* ── Handle a status payload from the server ─────────────────── */
function handleJobUpdate(data) {
  const status   = data.status   || '';
  const stage    = data.stage    || '';
  const messages = data.messages || data.log || [];

  // Update progress bar from message history
  if (messages.length) {
    updateProgressBar(messages);
  } else if (stage) {
    // Fallback: use stage field directly
    updateProgressBarFromStage(stage, status);
  }

  // Update live status text
  const stageKey = stage ? `${stage}:${status}` : status;
  const msg      = getStageMessage(stageKey, currentHandle);
  const isError  = status === 'error' || status === 'failed' || stage === 'error';
  const isDone   = status === 'complete' || status === 'done' || status === 'review' || stageKey === 'complete:done';
  updateStatusText(msg, isError ? 'error' : isDone ? 'done' : '');

  if (isDone) {
    stopPolling();
    finishJob(data);
    return;
  }

  if (isError) {
    stopPolling();
    const errorMsg = data.error || data.message || 'Unknown error';
    // Find which stage failed from messages
    const errMsg = messages.find(m => typeof m === 'object' && m.stage === 'error');
    const failedAt = errMsg && errMsg.stage_failed ? ` (failed at: ${errMsg.stage_failed})` : '';
    const stderrHint = data.stderr ? `\n\nPython traceback:\n${data.stderr.slice(-800)}` : '';
    updateStatusText(`✗ Error: ${errorMsg}${failedAt}`, 'error');
    console.error('[job error]', errorMsg, stderrHint || '');
    showToast(`Job failed: ${errorMsg}`, 'error');

    // Re-enable form
    const submitBtn = document.getElementById('submit-btn');
    submitBtn.disabled  = false;
    submitBtn.innerHTML = 'Generate Posters &#10022;';
    return;
  }
}

/* ── Finish / success ─────────────────────────────────────────── */
function finishJob(data) {
  // Mark all steps done
  updateProgressBarAllDone();
  updateStatusText('✓ Done! Your posters are ready.', 'done');

  showToast('Posters generated successfully!', 'success');

  // Render results
  renderResults(data);

  // Hide status cancel button, keep status bar visible
  document.getElementById('cancel-btn').classList.add('hidden');

  // Refresh history
  loadJobHistory();

  // Re-enable form
  const submitBtn = document.getElementById('submit-btn');
  submitBtn.disabled  = false;
  submitBtn.innerHTML = 'Generate Posters &#10022;';
}

/* ============================================================
   PROGRESS BAR
   ============================================================ */

/**
 * updateProgressBar(messages)
 * messages: array of strings or objects like { stage, status, message }
 * Parses each message to determine the furthest step reached.
 */
function updateProgressBar(messages) {
  let maxStep  = -1;
  let lastStage = null;
  let lastStatus = null;

  messages.forEach(m => {
    // Support string messages OR objects
    const text  = typeof m === 'string' ? m : (m.message || m.text || JSON.stringify(m));
    const stage  = typeof m === 'object' ? (m.stage  || '') : '';
    const status = typeof m === 'object' ? (m.status || '') : '';

    // Try object stage field first
    if (stage && STAGE_STEP[stage] !== undefined) {
      const stepIdx = STAGE_STEP[stage];
      if (stepIdx > maxStep) { maxStep = stepIdx; lastStage = stage; lastStatus = status; }
    }

    // Otherwise parse string message for known stage names
    for (const [stageName, stepIdx] of Object.entries(STAGE_STEP)) {
      if (text.includes(stageName)) {
        if (stepIdx > maxStep) { maxStep = stepIdx; lastStage = stageName; lastStatus = status || 'started'; }
      }
    }
  });

  if (maxStep >= 0) {
    setActiveStep(maxStep);
  }
}

function updateProgressBarFromStage(stage, status) {
  const stepIdx = STAGE_STEP[stage];
  if (stepIdx !== undefined) {
    setActiveStep(stepIdx);
  }
}

function updateProgressBarAllDone() {
  const totalSteps = 7;
  for (let i = 0; i < totalSteps; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) {
      el.classList.remove('active');
      el.classList.add('done');
    }
  }
  setTrackWidth(100);
}

/**
 * setActiveStep(stepIndex)
 * Mark steps 0..(stepIndex-1) as done, stepIndex as active, rest as pending.
 */
function setActiveStep(stepIndex) {
  const totalSteps = 7;

  for (let i = 0; i < totalSteps; i++) {
    const el = document.getElementById(`step-${i}`);
    if (!el) continue;

    el.classList.remove('active', 'done');

    if (i < stepIndex) {
      el.classList.add('done');
    } else if (i === stepIndex) {
      el.classList.add('active');
    }
  }

  // Fill track: percentage based on completed + half of current
  const pct = totalSteps <= 1 ? 0 : (stepIndex / (totalSteps - 1)) * 100;
  setTrackWidth(pct);
}

function setTrackWidth(pct) {
  const track = document.getElementById('progress-track');
  if (track) track.style.width = `${Math.min(100, Math.max(0, pct))}%`;
}

/* ============================================================
   STATUS TEXT
   ============================================================ */
function updateStatusText(message, type) {
  const el = document.getElementById('status-text');
  if (!el) return;
  el.textContent  = message;
  el.className    = 'status-text';
  if (type === 'error') el.classList.add('error-text');
  if (type === 'done')  el.classList.add('done-text');
}

/* ============================================================
   RENDER RESULTS
   ============================================================ */
function renderResults(data) {
  const grid   = document.getElementById('results-grid');
  // Prefer filenames (basenames only) over files (may be full absolute paths)
  const rawFiles = data.filenames || data.files || data.outputs || data.posters || [];
  const files  = rawFiles.map(f => (typeof f === 'string' ? f.split(/[\\/]/).pop() : f));
  const handle = data.handle || currentHandle || 'unknown';
  const jobId  = data.job_id || data.id || data.jobId || currentJobId;

  grid.innerHTML = '';

  if (!files.length) {
    grid.innerHTML = '<p style="color: var(--muted-text); font-size:0.9rem;">No output files found.</p>';
    showSection('results-section');
    return;
  }

  files.forEach((file, idx) => {
    // Support string filenames or objects { filename, ... }
    const filename  = typeof file === 'string' ? file : (file.filename || file.name || `poster_${idx + 1}.png`);
    const thumbSrc  = `/outputs/${encodeURIComponent(handle)}/${encodeURIComponent(jobId)}/${encodeURIComponent(filename)}`;
    const dlHref    = `/api/download/${encodeURIComponent(jobId)}/${encodeURIComponent(filename)}`;
    const varNum    = idx + 1;

    const card = document.createElement('div');
    card.className = 'poster-card';
    card.innerHTML = `
      <div class="poster-thumb-wrap">
        <a href="${thumbSrc}" target="_blank" rel="noopener" aria-label="View variation ${varNum} full size">
          <img
            class="poster-thumb"
            src="${thumbSrc}"
            alt="Poster variation ${varNum}"
            loading="lazy"
            onerror="this.style.opacity='0.4'; this.alt='Preview unavailable';"
          />
          <div class="poster-thumb-overlay">
            <div class="thumb-zoom-icon">&#128269;</div>
          </div>
        </a>
        <div class="variation-badge">V${varNum}</div>
      </div>
      <div class="poster-card-body">
        <div class="poster-filename">${escapeHtml(filename)}</div>
        <a
          class="btn btn-download"
          href="${dlHref}"
          download="${escapeHtml(filename)}"
          title="Download ${escapeHtml(filename)}"
        >
          &#8595; Download PNG
        </a>
      </div>
    `;

    grid.appendChild(card);
  });

  // Populate brand DNA if present
  if (data.brand_dna || data.brandDna) {
    renderBrandDna(data.brand_dna || data.brandDna);
  }

  showSection('results-section');
}

/* ── Brand DNA accordion content ────────────────────────────── */
function renderBrandDna(dna) {
  const grid = document.getElementById('brand-dna-grid');
  if (!grid || !dna) return;

  const entries = typeof dna === 'object' ? Object.entries(dna) : [];
  if (!entries.length) return;

  grid.innerHTML = entries.map(([key, val]) => `
    <div class="dna-item">
      <div class="dna-item-label">${escapeHtml(key.replace(/_/g, ' '))}</div>
      <div class="dna-item-value">${escapeHtml(String(val))}</div>
    </div>
  `).join('');
}

/* ============================================================
   APPROVE JOB
   ============================================================ */
async function approveJob(jobId) {
  try {
    const res  = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/approve`, { method: 'PATCH' });
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);

    showToast('Job marked as approved!', 'success');
    loadJobHistory();

    const approveBtn = document.getElementById('approve-btn');
    if (approveBtn) {
      approveBtn.textContent = '✓ Approved';
      approveBtn.disabled    = true;
      approveBtn.style.opacity = '0.7';
    }
  } catch (err) {
    console.error('approveJob error:', err);
    showToast(`Could not approve job: ${err.message}`, 'error');
  }
}

/* Helper called from HTML onclick (uses currentJobId) */
function approveCurrentJob() {
  if (!currentJobId) {
    showToast('No active job to approve.', 'warning');
    return;
  }
  approveJob(currentJobId);
}

/* ============================================================
   CANCEL JOB
   ============================================================ */
async function cancelJob() {
  if (!currentJobId) return;

  stopPolling();

  try {
    await fetch(`/api/jobs/${encodeURIComponent(currentJobId)}/cancel`, { method: 'PATCH' });
  } catch (err) {
    /* ignore — we still reset the UI */
  }

  showToast('Job cancelled.', 'warning');
  hideSection('status-section');

  const submitBtn = document.getElementById('submit-btn');
  submitBtn.disabled  = false;
  submitBtn.innerHTML = 'Generate Posters &#10022;';

  currentJobId  = null;
  loadJobHistory();
}

/* ============================================================
   JOB HISTORY
   ============================================================ */
async function loadJobHistory() {
  const tbody = document.getElementById('history-tbody');
  if (!tbody) return;

  try {
    const res  = await fetch('/api/jobs');
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);

    const jobs = Array.isArray(data) ? data : (data.jobs || data.data || []);

    if (!jobs.length) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8">
            <div class="history-empty">
              <div class="history-empty-icon">&#128196;</div>
              <span>No jobs yet — submit your first brief above.</span>
            </div>
          </td>
        </tr>`;
      return;
    }

    // Sort newest first
    jobs.sort((a, b) => {
      const ta = new Date(a.created_at || a.createdAt || a.timestamp || 0).getTime();
      const tb = new Date(b.created_at || b.createdAt || b.timestamp || 0).getTime();
      return tb - ta;
    });

    tbody.innerHTML = jobs.map(job => {
      const id      = job.job_id  || job.id     || job.jobId  || '—';
      const handle  = job.handle  || job.instagram_handle     || '—';
      const brief   = job.brief   || job.brief_text           || '—';
      const size    = job.size    || job.poster_size           || '—';
      const vars    = job.variations || job.num_variations     || '—';
      const status  = job.status  || 'unknown';
      const created = job.created_at || job.createdAt || job.timestamp || '';
      const dateStr = created ? formatDate(created) : '—';
      const files   = job.files   || job.outputs || [];

      return `
        <tr>
          <td class="td-handle">@${escapeHtml(String(handle).replace(/^@/, ''))}</td>
          <td class="td-id">${escapeHtml(id)}</td>
          <td class="td-brief" title="${escapeHtml(brief)}">${escapeHtml(brief)}</td>
          <td>${escapeHtml(String(size))}</td>
          <td>${escapeHtml(String(vars))}</td>
          <td>${renderStatusBadge(status)}</td>
          <td style="white-space:nowrap;">${escapeHtml(dateStr)}</td>
          <td>
            ${renderHistoryActions(job, id, status, files, handle)}
          </td>
        </tr>`;
    }).join('');

  } catch (err) {
    console.error('loadJobHistory error:', err);
    tbody.innerHTML = `
      <tr>
        <td colspan="8">
          <div class="history-empty">
            <div class="history-empty-icon">&#9888;</div>
            <span>Could not load history: ${escapeHtml(err.message)}</span>
          </div>
        </td>
      </tr>`;
  }
}

function renderStatusBadge(status) {
  const s = String(status).toLowerCase();
  let cls  = 'badge-pending';
  let dot  = true;

  if (s === 'running' || s === 'processing' || s === 'started') cls = 'badge-running';
  else if (s === 'complete' || s === 'completed' || s === 'done') cls = 'badge-complete';
  else if (s === 'approved') cls = 'badge-approved';
  else if (s === 'error' || s === 'failed') cls = 'badge-error';

  return `<span class="badge ${cls}"><span class="badge-dot"></span>${escapeHtml(status)}</span>`;
}

function renderHistoryActions(job, id, status, files, handle) {
  const s = String(status).toLowerCase();
  let html = '';

  // Re-open / view results
  if (s === 'complete' || s === 'completed' || s === 'done' || s === 'review' || s === 'approved') {
    html += `<button class="btn btn-outline" style="font-size:0.78rem; padding:5px 10px;"
               onclick="restoreResults(${JSON.stringify(JSON.stringify(job))})">
               &#128065; View
             </button> `;
  }

  // Approve
  if (s === 'complete' || s === 'completed' || s === 'done' || s === 'review') {
    html += `<button class="btn btn-primary" style="font-size:0.78rem; padding:5px 10px;"
               onclick="approveJob('${escapeHtml(id)}')">
               &#10003; Approve
             </button>`;
  }

  if (!html) html = '<span style="color:var(--muted-text);font-size:0.8rem;">—</span>';
  return html;
}

/* Restore results from history row */
function restoreResults(jobJsonStr) {
  try {
    const job = JSON.parse(jobJsonStr);
    currentJobId  = job.job_id  || job.id     || job.jobId;
    currentHandle = (job.client_handle || job.handle || job.instagram_handle || '').replace(/^@/, '');

    // Parse output_paths from CSV (JSON string of full paths) into filenames
    if (!job.filenames && !job.files && job.output_paths) {
      try {
        const paths = JSON.parse(job.output_paths);
        job.filenames = paths.map(p => p.split(/[\\/]/).pop());
      } catch (_) {}
    }

    renderResults(job);
    showSection('results-section');
    document.getElementById('results-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    showToast('Could not restore results.', 'error');
  }
}

/* ============================================================
   TOAST NOTIFICATIONS
   ============================================================ */
function showToast(message, type) {
  // type: 'success' | 'error' | 'info' | 'warning'
  const t     = type || 'info';
  const icons = { success: '&#10003;', error: '&#10007;', info: '&#9432;', warning: '&#9888;' };
  const icon  = icons[t] || '&#9432;';

  const container = document.getElementById('toast-container');
  if (!container) return;

  const el = document.createElement('div');
  el.className  = `toast toast-${t}`;
  el.innerHTML  = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-body">${escapeHtml(String(message))}</span>
  `;

  container.appendChild(el);

  // Auto-dismiss after 4 seconds
  const timeout = setTimeout(() => dismissToast(el), 4000);

  el.addEventListener('click', () => { clearTimeout(timeout); dismissToast(el); });
}

function dismissToast(el) {
  if (!el || el.classList.contains('removing')) return;
  el.classList.add('removing');
  el.addEventListener('animationend', () => el.remove(), { once: true });
}

/* ============================================================
   UTILITIES
   ============================================================ */
function showSection(id)  { const el = document.getElementById(id); if (el) el.classList.remove('hidden'); }
function hideSection(id)  { const el = document.getElementById(id); if (el) el.classList.add('hidden');    }

function clearResults() {
  const grid = document.getElementById('results-grid');
  if (grid) grid.innerHTML = '';

  const dnaGrid = document.getElementById('brand-dna-grid');
  if (dnaGrid) dnaGrid.innerHTML = '<p style="color:var(--muted-text);font-size:0.875rem;grid-column:1/-1;">No brand data available for this job.</p>';

  hideSection('results-section');

  // Reset progress bar
  for (let i = 0; i < 7; i++) {
    const el = document.getElementById(`step-${i}`);
    if (el) { el.classList.remove('active', 'done'); }
  }
  setTrackWidth(0);

  // Reset approve button
  const approveBtn = document.getElementById('approve-btn');
  if (approveBtn) {
    approveBtn.innerHTML = '&#10003; Mark as Approved';
    approveBtn.disabled  = false;
    approveBtn.style.opacity = '1';
  }

  // Reset cancel button
  const cancelBtn = document.getElementById('cancel-btn');
  if (cancelBtn) cancelBtn.classList.remove('hidden');

  // Reset job id badge
  const jobIdVal = document.getElementById('job-id-value');
  if (jobIdVal) jobIdVal.textContent = '—';

  updateStatusText('Initialising…');
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

function scrollToHistory() {
  const el = document.getElementById('history-section');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function toggleAccordion(btn) {
  const accordion = btn.closest('.accordion');
  if (!accordion) return;
  const isOpen = accordion.classList.contains('open');
  accordion.classList.toggle('open', !isOpen);
  btn.setAttribute('aria-expanded', String(!isOpen));
}

function formatDate(dateStr) {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#39;');
}

/* ============================================================
   INITIALISE
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // Bind form submit
  const form = document.getElementById('poster-form');
  if (form) form.addEventListener('submit', submitForm);

  // Auto-load job history
  loadJobHistory();
});
