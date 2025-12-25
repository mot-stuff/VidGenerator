// Dashboard wizard (multi-user) - vanilla JS for production reliability

const STORAGE_KEY = 'bb_wizard_state_v1';

function loadState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveState(state) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

function defaultState() {
  return {
    step: 1,
    textMode: 'single', // single | batch
    singleText: '',
    texts: [],
    splitScreen: false,
    videos: { video1: null, video2: null }, // file_id values
  };
}

function qs(sel) {
  return document.querySelector(sel);
}

function qsa(sel) {
  return Array.from(document.querySelectorAll(sel));
}

function setHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle('hidden', hidden);
}

function updateStatus(message, isError = false) {
  const statusText = qs('#statusText');
  const statusDot = qs('.status-dot');
  if (statusText) statusText.textContent = message;
  if (!statusDot) return;
  if (isError) statusDot.style.backgroundColor = '#dc2626';
  else if (message.includes('✅')) statusDot.style.backgroundColor = '#16a34a';
  else if (message.includes('🔄') || message.includes('🚀')) statusDot.style.backgroundColor = '#2563eb';
  else statusDot.style.backgroundColor = '#6b7280';
}

async function parseApiResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  const text = await response.text();
  if (contentType.includes('application/json')) {
    try {
      return { ok: response.ok, status: response.status, data: JSON.parse(text), raw: text };
    } catch {
      return { ok: false, status: response.status, data: null, raw: text || '' };
    }
  }
  return { ok: response.ok, status: response.status, data: null, raw: text || '' };
}

function validateStep1(state) {
  const items = state.textMode === 'single' ? [state.singleText.trim()].filter(Boolean) : state.texts;
  return items.length > 0;
}

function validateStep2(state) {
  if (!state.videos.video1) return false;
  if (state.splitScreen && !state.videos.video2) return false;
  return true;
}

function renderTextList(state) {
  const list = qs('#textList');
  const count = qs('#textCount');
  if (!list || !count) return;

  const items = state.texts;
  count.textContent = String(items.length);

  if (items.length === 0) {
    list.innerHTML = '<div class="wizard-empty">No items yet</div>';
    return;
  }

  list.innerHTML = items
    .map((t, idx) => {
      const safe = String(t).replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return `
        <div class="wizard-list-item">
          <div class="wizard-list-text">${safe}</div>
          <button class="btn btn-secondary wizard-small" type="button" data-remove-text="${idx}">Remove</button>
        </div>
      `;
    })
    .join('');
}

function renderWizard(state) {
  // Stepper
  qsa('.wizard-step').forEach((btn) => {
    const step = Number(btn.getAttribute('data-step'));
    btn.classList.toggle('active', step === state.step);
    btn.classList.toggle('done', step < state.step);
  });

  // Panels
  setHidden(qs('#step1Panel'), state.step !== 1);
  setHidden(qs('#step2Panel'), state.step !== 2);
  setHidden(qs('#step3Panel'), state.step !== 3);

  // Buttons
  const backBtn = qs('#backBtn');
  const nextBtn = qs('#nextBtn');
  if (backBtn) backBtn.disabled = state.step <= 1;
  if (nextBtn) nextBtn.textContent = state.step >= 3 ? 'Done' : 'Next';

  // Text mode sections
  const modeSingle = state.textMode === 'single';
  setHidden(qs('#batchSection'), modeSingle);

  // Split screen UI
  const splitEl = qs('#splitScreen');
  if (splitEl) splitEl.checked = Boolean(state.splitScreen);
  const video2Section = qs('#video2Section');
  if (video2Section) video2Section.style.display = state.splitScreen ? 'block' : 'none';

  // Inputs
  const textInput = qs('#textInput');
  if (textInput && textInput.value !== state.singleText) textInput.value = state.singleText;

  // Radios
  qsa('input[name="textMode"]').forEach((r) => {
    r.checked = r.value === state.textMode;
  });

  // Summary
  const summary = qs('#wizardSummary');
  if (summary) {
    const textCount = state.textMode === 'single' ? (state.singleText.trim() ? 1 : 0) : state.texts.length;
    const v1 = state.videos.video1 ? 'uploaded' : 'missing';
    const v2 = state.splitScreen ? (state.videos.video2 ? 'uploaded' : 'missing') : 'n/a';
    summary.innerHTML = `
      <div class="wizard-summary-row"><div>Text items</div><div>${textCount}</div></div>
      <div class="wizard-summary-row"><div>Split screen</div><div>${state.splitScreen ? 'yes' : 'no'}</div></div>
      <div class="wizard-summary-row"><div>Video 1</div><div>${v1}</div></div>
      <div class="wizard-summary-row"><div>Video 2</div><div>${v2}</div></div>
    `;
  }

  // Text list
  renderTextList(state);
}

async function uploadVideo(state, videoType) {
  const input = qs(`#${videoType}`);
  if (!input || !input.files || !input.files[0]) return state;
  const file = input.files[0];

  const formData = new FormData();
  formData.append('video', file);
  formData.append('type', videoType);

  updateStatus(`Uploading ${videoType}...`);

  const response = await fetch('/api/upload_video', { method: 'POST', body: formData });
  const parsed = await parseApiResponse(response);

  if (!parsed.ok || !parsed.data || !parsed.data.success) {
    const msg =
      parsed.data && parsed.data.error
        ? parsed.data.error
        : parsed.raw
          ? parsed.raw.slice(0, 200)
          : 'No response body';
    updateStatus(`Upload failed (${parsed.status}): ${msg}`, true);
    return state;
  }

  const infoDiv = qs(`#${videoType}Info`);
  if (infoDiv) {
    infoDiv.textContent = `✅ ${file.name}`;
    infoDiv.classList.remove('hidden');
  }

  state.videos[videoType] = parsed.data.file_id;
  updateStatus(`✅ ${videoType} uploaded`);
  return state;
}

async function uploadCSVToTexts(state) {
  const input = qs('#csvFile');
  if (!input || !input.files || !input.files[0]) return state;
  const file = input.files[0];

  const formData = new FormData();
  formData.append('csv', file);

  updateStatus('Processing CSV/TXT...');

  const response = await fetch('/api/upload_csv', { method: 'POST', body: formData });
  const parsed = await parseApiResponse(response);

  if (!parsed.ok || !parsed.data || !parsed.data.success) {
    const msg =
      parsed.data && parsed.data.error
        ? parsed.data.error
        : parsed.raw
          ? parsed.raw.slice(0, 200)
          : 'No response body';
    updateStatus(`CSV failed (${parsed.status}): ${msg}`, true);
    return state;
  }

  const texts = Array.isArray(parsed.data.texts) ? parsed.data.texts : [];
  state.texts = texts.filter((t) => String(t || '').trim().length > 0).slice(0, 500);

  const infoDiv = qs('#csvInfo');
  if (infoDiv) {
    infoDiv.textContent = `✅ ${state.texts.length} items loaded`;
    infoDiv.classList.remove('hidden');
  }

  updateStatus(`✅ Loaded ${state.texts.length} items`);
  return state;
}

function renderJobs(jobs) {
  const fileList = qs('#fileList');
  if (!fileList) return;

  if (!Array.isArray(jobs) || jobs.length === 0) {
    fileList.innerHTML =
      '<div style="padding: 20px; text-align: center; color: #6b7280;">No jobs yet</div>';
    return;
  }

  fileList.innerHTML = jobs
    .map((job) => {
      const status = job.status || 'unknown';
      const created = job.created_at ? new Date(job.created_at).toLocaleString() : '';
      const err = job.error_message ? String(job.error_message) : '';
      const color =
        status === 'completed' ? '#16a34a' : status === 'failed' ? '#dc2626' : status === 'processing' ? '#2563eb' : '#ca8a04';
      const download = job.can_download
        ? `<a href="/api/download/${job.id}" class="btn btn-secondary wizard-small" download>Download</a>`
        : '';
      return `
        <div class="file-item">
          <div>
            <div class="file-name">${String(job.filename || '')}</div>
            <div class="file-meta">
              Status: <span style="color:${color}">${status}</span> | Created: ${created}
              ${err ? `<br>Error: ${String(err).replace(/</g, '&lt;').replace(/>/g, '&gt;')}` : ''}
            </div>
          </div>
          <div>${download}</div>
        </div>
      `;
    })
    .join('');
}

let jobsPollTimer = null;
let jobsPollDelayMs = 2000;
let lastJobsJson = '';
let jobsPollingEnabled = true;

async function fetchAndRenderJobs() {
  if (!jobsPollingEnabled) return;
  try {
    const r = await fetch('/api/jobs', { cache: 'no-store' });
    const parsed = await parseApiResponse(r);
    if (!parsed.ok || !Array.isArray(parsed.data)) return;

    const json = JSON.stringify(parsed.data);
    if (json !== lastJobsJson) {
      lastJobsJson = json;
      renderJobs(parsed.data);
    }

    const hasActive = parsed.data.some((j) => j.status === 'processing' || j.status === 'pending');
    if (hasActive) jobsPollDelayMs = 2000;
    else jobsPollDelayMs = Math.min(30000, Math.max(8000, jobsPollDelayMs + 4000));
  } catch {
    jobsPollDelayMs = Math.min(30000, Math.max(8000, jobsPollDelayMs + 4000));
  } finally {
    if (jobsPollTimer) clearTimeout(jobsPollTimer);
    jobsPollTimer = setTimeout(fetchAndRenderJobs, jobsPollDelayMs);
  }
}

async function startGeneration(state) {
  if (!validateStep1(state)) {
    updateStatus('Add at least one text item', true);
    return;
  }
  if (!validateStep2(state)) {
    updateStatus('Upload required video(s) first', true);
    return;
  }

  const isBatch = state.textMode === 'batch';
  updateStatus(isBatch ? '🔄 Starting batch...' : '🚀 Starting generation...');

  if (!isBatch) {
    const payload = {
      text: state.singleText.trim(),
      video_file_id: state.videos.video1,
      video2_file_id: state.videos.video2,
      split_screen_enabled: state.splitScreen,
    };
    const r = await fetch('/api/generate_video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const parsed = await parseApiResponse(r);
    if (!parsed.ok || !parsed.data || !parsed.data.success) {
      const msg = parsed.data && parsed.data.error ? parsed.data.error : parsed.raw ? parsed.raw.slice(0, 200) : 'No response body';
      updateStatus(`❌ Generation failed (${parsed.status}): ${msg}`, true);
      return;
    }
    updateStatus('✅ Video generation started');
    return;
  }

  const payload = {
    texts: state.texts,
    video_file_id: state.videos.video1,
    video2_file_id: state.videos.video2,
    split_screen_enabled: state.splitScreen,
  };
  const r = await fetch('/api/generate_batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const parsed = await parseApiResponse(r);
  if (!parsed.ok || !parsed.data || !parsed.data.success) {
    const msg = parsed.data && parsed.data.error ? parsed.data.error : parsed.raw ? parsed.raw.slice(0, 200) : 'No response body';
    updateStatus(`❌ Batch failed (${parsed.status}): ${msg}`, true);
    return;
  }
  updateStatus('✅ Batch started');
}

document.addEventListener('DOMContentLoaded', () => {
  let state = loadState() || defaultState();

  const stepper = qs('#wizardStepper');
  const backBtn = qs('#backBtn');
  const nextBtn = qs('#nextBtn');
  const refreshJobsBtn = qs('#refreshJobsBtn');
  const addToBatchBtn = qs('#addToBatchBtn');
  const clearTextsBtn = qs('#clearTextsBtn');
  const csvFile = qs('#csvFile');
  const generateBtn = qs('#generateBtn');

  renderWizard(state);

  if (stepper) {
    stepper.addEventListener('click', (e) => {
      const btn = e.target.closest('.wizard-step');
      if (!btn) return;
      const step = Number(btn.getAttribute('data-step'));
      if (![1, 2, 3].includes(step)) return;
      state.step = step;
      saveState(state);
      renderWizard(state);
    });
  }

  qsa('input[name="textMode"]').forEach((r) => {
    r.addEventListener('change', () => {
      state.textMode = r.value;
      saveState(state);
      renderWizard(state);
    });
  });

  const textInput = qs('#textInput');
  if (textInput) {
    textInput.addEventListener('input', () => {
      state.singleText = textInput.value;
      saveState(state);
    });
  }

  if (addToBatchBtn) {
    addToBatchBtn.addEventListener('click', () => {
      const t = (qs('#textInput')?.value || '').trim();
      if (!t) {
        updateStatus('Enter text first', true);
        return;
      }
      state.texts = [t, ...state.texts].slice(0, 500);
      state.textMode = 'batch';
      saveState(state);
      renderWizard(state);
    });
  }

  if (clearTextsBtn) {
    clearTextsBtn.addEventListener('click', () => {
      state.texts = [];
      saveState(state);
      renderWizard(state);
    });
  }

  const textList = qs('#textList');
  if (textList) {
    textList.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-remove-text]');
      if (!btn) return;
      const idx = Number(btn.getAttribute('data-remove-text'));
      if (!Number.isFinite(idx)) return;
      state.texts.splice(idx, 1);
      saveState(state);
      renderWizard(state);
    });
  }

  if (csvFile) {
    csvFile.addEventListener('change', async () => {
      state.textMode = 'batch';
      state = await uploadCSVToTexts(state);
      saveState(state);
      renderWizard(state);
    });
  }

  const splitEl = qs('#splitScreen');
  if (splitEl) {
    splitEl.addEventListener('change', () => {
      state.splitScreen = Boolean(splitEl.checked);
      if (!state.splitScreen) state.videos.video2 = null;
      saveState(state);
      renderWizard(state);
    });
  }

  const v1 = qs('#video1');
  if (v1) {
    v1.addEventListener('change', async () => {
      state = await uploadVideo(state, 'video1');
      saveState(state);
      renderWizard(state);
    });
  }

  const v2 = qs('#video2');
  if (v2) {
    v2.addEventListener('change', async () => {
      state = await uploadVideo(state, 'video2');
      saveState(state);
      renderWizard(state);
    });
  }

  if (backBtn) {
    backBtn.addEventListener('click', () => {
      state.step = Math.max(1, state.step - 1);
      saveState(state);
      renderWizard(state);
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      if (state.step === 1 && !validateStep1(state)) {
        updateStatus('Add at least one text item', true);
        return;
      }
      if (state.step === 2 && !validateStep2(state)) {
        updateStatus('Upload required video(s) first', true);
        return;
      }
      state.step = Math.min(3, state.step + 1);
      saveState(state);
      renderWizard(state);
    });
  }

  if (generateBtn) {
    generateBtn.addEventListener('click', async () => {
      await startGeneration(state);
      jobsPollDelayMs = 2000;
      fetchAndRenderJobs();
    });
  }

  if (refreshJobsBtn) {
    refreshJobsBtn.addEventListener('click', async () => {
      jobsPollDelayMs = 2000;
      await fetchAndRenderJobs();
    });
  }

  // Start polling jobs with backoff
  fetchAndRenderJobs();

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      jobsPollDelayMs = Math.min(30000, Math.max(10000, jobsPollDelayMs));
      return;
    }
    jobsPollDelayMs = 2000;
    fetchAndRenderJobs();
  });
});


