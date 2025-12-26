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
    bgMusic: { enabled: false, volume: 0.15, fileId: null },
    splitScreen: false,
    videos: { video1: null, video2: null }, // file_id values
    videoSources: { video1: 'upload', video2: 'upload' }, // upload | preset
    presetIds: { video1: 'minecraft_parkour', video2: 'minecraft_parkour' },
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

function getUserTier() {
  const el = qs('#userPlan');
  return el ? String(el.dataset.tier || '').trim().toLowerCase() : '';
}

function isProUser() {
  return getUserTier() === 'pro';
}

function getMaxStep() {
  return isProUser() ? 4 : 3;
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
  const v1Ok = state.videoSources?.video1 === 'preset' || Boolean(state.videos.video1);
  if (!v1Ok) return false;
  if (state.splitScreen) {
    const v2Ok = state.videoSources?.video2 === 'preset' || Boolean(state.videos.video2);
    if (!v2Ok) return false;
  }
  return true;
}

function getPresetConfig() {
  const el = qs('#presetConfig');
  const v1 = el ? String(el.dataset.video1Path || '').trim() : '';
  const v2 = el ? String(el.dataset.video2Path || '').trim() : '';
  const soap = el ? String(el.dataset.soapPath || '').trim() : '';
  return { video1Path: v1, video2Path: v2, soapPath: soap };
}

function normalizeState(state) {
  if (!state.videoSources) state.videoSources = { video1: 'upload', video2: 'upload' };
  if (!state.videoSources.video1) state.videoSources.video1 = 'upload';
  if (!state.videoSources.video2) state.videoSources.video2 = 'upload';
  if (!state.videos) state.videos = { video1: null, video2: null };
  if (!state.presetIds) state.presetIds = { video1: 'minecraft_parkour', video2: 'minecraft_parkour' };
  if (!state.presetIds.video1) state.presetIds.video1 = 'minecraft_parkour';
  if (!state.presetIds.video2) state.presetIds.video2 = 'minecraft_parkour';
  if (!state.bgMusic) state.bgMusic = { enabled: false, volume: 0.15, fileId: null };
  if (typeof state.bgMusic.enabled !== 'boolean') state.bgMusic.enabled = Boolean(state.bgMusic.enabled);
  {
    const v = Number(state.bgMusic.volume);
    state.bgMusic.volume = Number.isFinite(v) ? Math.max(0, Math.min(0.4, v)) : 0.15;
  }
  if (!state.bgMusic.fileId) state.bgMusic.fileId = null;
  return state;
}

function presetLabelFromId(id) {
  if (id === 'minecraft_parkour') return 'Minecraft Parkour';
  if (id === 'soap_cutting') return 'Soap Cutting';
  return 'Preset';
}

function isPresetAvailable(presetId, cfg, slot) {
  const pid = String(presetId || '').trim();
  if (pid === 'soap_cutting') return Boolean(cfg.soapPath);
  if (pid === 'minecraft_parkour') {
    return slot === 'video2' ? Boolean(cfg.video2Path || cfg.video1Path) : Boolean(cfg.video1Path);
  }
  return false;
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
  state = normalizeState(state);
  const maxStep = getMaxStep();
  if (state.step > maxStep) state.step = maxStep;

  // Stepper
  qsa('.wizard-step').forEach((btn) => {
    const step = Number(btn.getAttribute('data-step'));
    btn.classList.toggle('active', step === state.step);
    btn.classList.toggle('done', step < state.step);
  });

  // Panels
  const panels = [
    { step: 1, el: qs('#step1Panel') },
    { step: 2, el: qs('#step2Panel') },
    { step: 3, el: qs('#step3Panel') },
    { step: 4, el: qs('#step4Panel') },
  ];

  panels.forEach(({ step, el }) => {
    if (!el) return;
    const isActive = step === state.step;
    if (isActive) {
      // animate in
      el.classList.add('is-enter');
      el.classList.remove('hidden');
      requestAnimationFrame(() => {
        requestAnimationFrame(() => el.classList.remove('is-enter'));
      });
    } else {
      el.classList.add('hidden');
      el.classList.remove('is-enter');
    }
  });

  // Buttons
  const backBtn = qs('#backBtn');
  const nextBtn = qs('#nextBtn');
  if (backBtn) backBtn.disabled = state.step <= 1;
  if (nextBtn) nextBtn.textContent = state.step >= maxStep ? 'Done' : 'Next';

  // Text mode sections
  const modeSingle = state.textMode === 'single';
  setHidden(qs('#batchSection'), modeSingle);

  // Split screen UI
  const splitEl = qs('#splitScreen');
  if (splitEl) splitEl.checked = Boolean(state.splitScreen);
  const video2Section = qs('#video2Section');
  if (video2Section) video2Section.style.display = state.splitScreen ? 'block' : 'none';

  // Video sources
  qsa('input[name="video1Source"]').forEach((r) => {
    r.checked = r.value === state.videoSources.video1;
  });
  qsa('input[name="video2Source"]').forEach((r) => {
    r.checked = r.value === state.videoSources.video2;
  });

  const presetCfg = getPresetConfig();
  const v1Input = qs('#video1');
  const v2Input = qs('#video2');
  const v1Info = qs('#video1Info');
  const v2Info = qs('#video2Info');
  const v1PresetRow = qs('#video1PresetRow');
  const v2PresetRow = qs('#video2PresetRow');
  const v1PresetSelect = qs('#video1PresetSelect');
  const v2PresetSelect = qs('#video2PresetSelect');

  const v1UsingPreset = state.videoSources.video1 === 'preset';
  const v2UsingPreset = state.videoSources.video2 === 'preset';

  // Disable preset choice if not configured (UI-only; backend is authoritative)
  const v1PresetRadios = qsa('input[name="video1Source"][value="preset"]');
  v1PresetRadios.forEach((r) => (r.disabled = !(presetCfg.video1Path || presetCfg.soapPath)));
  const v2PresetRadios = qsa('input[name="video2Source"][value="preset"]');
  v2PresetRadios.forEach((r) => (r.disabled = !(presetCfg.video2Path || presetCfg.video1Path || presetCfg.soapPath)));

  if (v1PresetSelect) v1PresetSelect.value = state.presetIds.video1 || 'minecraft_parkour';
  if (v2PresetSelect) v2PresetSelect.value = state.presetIds.video2 || 'minecraft_parkour';

  if (v1PresetSelect) {
    Array.from(v1PresetSelect.options).forEach((opt) => {
      opt.disabled = !isPresetAvailable(opt.value, presetCfg, 'video1');
    });
  }
  if (v2PresetSelect) {
    Array.from(v2PresetSelect.options).forEach((opt) => {
      opt.disabled = !isPresetAvailable(opt.value, presetCfg, 'video2');
    });
  }

  setHidden(v1PresetRow, !v1UsingPreset);
  setHidden(v2PresetRow, !v2UsingPreset);

  setHidden(v1Input, v1UsingPreset);
  setHidden(v2Input, v2UsingPreset);

  if (v1Input) v1Input.disabled = v1UsingPreset;
  if (v2Input) v2Input.disabled = v2UsingPreset;

  if (v1UsingPreset) {
    if (v1Info) {
      v1Info.textContent = isPresetAvailable(state.presetIds.video1, presetCfg, 'video1')
        ? `✅ Preset: ${presetLabelFromId(state.presetIds.video1)}`
        : 'Preset not configured';
      v1Info.classList.remove('hidden');
    }
  } else {
    if (v1Info && !state.videos.video1) v1Info.classList.add('hidden');
  }

  if (state.splitScreen) {
    if (v2UsingPreset) {
      if (v2Info) {
        v2Info.textContent = isPresetAvailable(state.presetIds.video2, presetCfg, 'video2')
          ? `✅ Preset: ${presetLabelFromId(state.presetIds.video2)}`
          : 'Preset not configured';
        v2Info.classList.remove('hidden');
      }
    } else {
      if (v2Info && !state.videos.video2) v2Info.classList.add('hidden');
    }
  }

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
    const v1 =
      state.videoSources.video1 === 'preset'
        ? presetLabelFromId(state.presetIds.video1)
        : state.videos.video1
          ? 'uploaded'
          : 'missing';
    const v2 = state.splitScreen
      ? state.videoSources.video2 === 'preset'
        ? presetLabelFromId(state.presetIds.video2)
        : state.videos.video2
          ? 'uploaded'
          : 'missing'
      : 'n/a';
    summary.innerHTML = `
      <div class="wizard-summary-row"><div>Audio items</div><div>${textCount}</div></div>
      <div class="wizard-summary-row"><div>Background music</div><div>${state.bgMusic.enabled ? `on (${Math.round(state.bgMusic.volume * 100)}%)` : 'off'}</div></div>
      <div class="wizard-summary-row"><div>Split screen</div><div>${state.splitScreen ? 'yes' : 'no'}</div></div>
      <div class="wizard-summary-row"><div>Video 1</div><div>${v1}</div></div>
      <div class="wizard-summary-row"><div>Video 2</div><div>${v2}</div></div>
    `;
  }

  // Background music UI
  const bgEnabled = qs('#bgMusicEnabled');
  const bgControls = qs('#bgMusicControls');
  const bgVol = qs('#bgMusicVolume');
  const bgVolLabel = qs('#bgMusicVolumeLabel');
  const bgInfo = qs('#bgMusicInfo');
  if (bgEnabled) bgEnabled.checked = Boolean(state.bgMusic.enabled);
  setHidden(bgControls, !state.bgMusic.enabled);
  if (bgVol) bgVol.value = String(Math.round(state.bgMusic.volume * 100));
  if (bgVolLabel) bgVolLabel.textContent = `${Math.round(state.bgMusic.volume * 100)}%`;
  if (bgInfo) {
    if (state.bgMusic.enabled && state.bgMusic.fileId) bgInfo.classList.remove('hidden');
    else bgInfo.classList.add('hidden');
  }

  // Text list
  renderTextList(state);
}

async function validateUploadedVideos(state) {
  state = normalizeState(state);
  const v1 = state.videoSources.video1 === 'upload' ? state?.videos?.video1 || null : null;
  const v2 = state.videoSources.video2 === 'upload' ? state?.videos?.video2 || null : null;
  if (!v1 && !v2) return state;

  try {
    const r = await fetch('/api/validate_uploads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video1: v1, video2: v2 }),
    });
    const parsed = await parseApiResponse(r);
    if (!parsed.ok || !parsed.data || !parsed.data.success) return state;

    const v1Exists = Boolean(parsed.data.video1_exists);
    const v2Exists = Boolean(parsed.data.video2_exists);

    if (!v1Exists && state.videos.video1) {
      state.videos.video1 = null;
      const info = qs('#video1Info');
      if (info) info.classList.add('hidden');
    }
    if (!v2Exists && state.videos.video2) {
      state.videos.video2 = null;
      const info = qs('#video2Info');
      if (info) info.classList.add('hidden');
    }
  } catch {
    return state;
  }

  return state;
}

async function uploadVideo(state, videoType) {
  state = normalizeState(state);
  if (state.videoSources && state.videoSources[videoType] === 'preset') return state;
  const input = qs(`#${videoType}`);
  if (!input || !input.files || !input.files[0]) return state;
  const file = input.files[0];

  const progressWrap = qs(`#${videoType}UploadProgress`);
  const progressFill = qs(`#${videoType}UploadProgressFill`);
  const infoDiv = qs(`#${videoType}Info`);

  if (progressFill) progressFill.style.width = '0%';
  if (progressWrap) progressWrap.classList.remove('hidden');
  if (infoDiv) infoDiv.classList.add('hidden');

  updateStatus(`Uploading ${videoType}...`);

  const formData = new FormData();
  formData.append('video', file);
  formData.append('type', videoType);

  const result = await new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload_video', true);

    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable) return;
      const pct = Math.max(0, Math.min(100, Math.round((evt.loaded / evt.total) * 100)));
      if (progressFill) progressFill.style.width = `${pct}%`;
    };

    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText || '{}');
      } catch {
        data = null;
      }
      resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, data, raw: xhr.responseText || '' });
    };

    xhr.onerror = () => resolve({ status: 0, ok: false, data: null, raw: '' });
    xhr.send(formData);
  });

  if (!result.ok || !result.data || !result.data.success) {
    const msg = result.data && result.data.error ? result.data.error : result.raw ? result.raw.slice(0, 200) : 'No response body';
    updateStatus(`Upload failed (${result.status}): ${msg}`, true);
    if (progressWrap) progressWrap.classList.add('hidden');
    return state;
  }

  if (progressFill) progressFill.style.width = '100%';
  if (progressWrap) setTimeout(() => progressWrap.classList.add('hidden'), 350);

  if (infoDiv) {
    infoDiv.textContent = `✅ ${file.name}`;
    infoDiv.classList.remove('hidden');
  }

  state.videos[videoType] = result.data.file_id;
  updateStatus(`✅ ${videoType} uploaded`);
  return state;
}

async function uploadBgMusic(state) {
  state = normalizeState(state);
  const input = qs('#bgMusicFile');
  if (!input || !input.files || !input.files[0]) return state;
  const file = input.files[0];

  const progressWrap = qs('#bgMusicUploadProgress');
  const progressFill = qs('#bgMusicUploadProgressFill');
  const infoDiv = qs('#bgMusicInfo');

  if (progressFill) progressFill.style.width = '0%';
  if (progressWrap) progressWrap.classList.remove('hidden');
  if (infoDiv) infoDiv.classList.add('hidden');

  updateStatus('Uploading background music...');

  const formData = new FormData();
  formData.append('audio', file);

  const result = await new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload_audio', true);

    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable) return;
      const pct = Math.max(0, Math.min(100, Math.round((evt.loaded / evt.total) * 100)));
      if (progressFill) progressFill.style.width = `${pct}%`;
    };

    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText || '{}');
      } catch {
        data = null;
      }
      resolve({ status: xhr.status, ok: xhr.status >= 200 && xhr.status < 300, data, raw: xhr.responseText || '' });
    };

    xhr.onerror = () => resolve({ status: 0, ok: false, data: null, raw: '' });
    xhr.send(formData);
  });

  if (!result.ok || !result.data || !result.data.success) {
    const msg = result.data && result.data.error ? result.data.error : result.raw ? result.raw.slice(0, 200) : 'No response body';
    updateStatus(`Upload failed (${result.status}): ${msg}`, true);
    if (progressWrap) progressWrap.classList.add('hidden');
    return state;
  }

  if (progressFill) progressFill.style.width = '100%';
  if (progressWrap) setTimeout(() => progressWrap.classList.add('hidden'), 350);

  state.bgMusic.fileId = result.data.file_id;

  if (infoDiv) {
    infoDiv.textContent = `✅ ${file.name}`;
    infoDiv.classList.remove('hidden');
  }

  updateStatus('✅ Background music uploaded');
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
      const stage = job.stage ? String(job.stage) : '';
      const p = Math.max(0, Math.min(1, Number(job.progress ?? 0)));
      const pct = Math.round(p * 100);
      const created = job.created_at ? new Date(job.created_at).toLocaleString() : '';
      const err = job.error_message ? String(job.error_message) : '';
      const color =
        status === 'completed' ? '#16a34a' : status === 'failed' ? '#dc2626' : status === 'processing' ? '#2563eb' : '#ca8a04';
      const download = job.can_download
        ? `<a href="/api/download/${job.id}?delete=1" class="btn btn-secondary wizard-small" download>Download</a>`
        : '';
      const cancel =
        status === 'processing' || status === 'pending'
          ? `<button class="btn btn-secondary wizard-small" type="button" data-cancel-job="${job.id}">Stop</button>`
          : '';
      const progressBar =
        status === 'processing' || status === 'pending'
          ? `
            <div class="progress" style="margin-top:8px;">
              <div class="progress-fill" style="width:${pct}%;"></div>
            </div>
            <div class="progress-meta">${pct}%${stage ? ` • ${stage}` : ''}</div>
          `
          : '';
      return `
        <div class="file-item">
          <div>
            <div class="file-name">${String(job.filename || '')}</div>
            <div class="file-meta">
              Status: <span style="color:${color}">${status}</span> | Created: ${created}
              ${err ? `<br>Error: ${String(err).replace(/</g, '&lt;').replace(/>/g, '&gt;')}` : ''}
            </div>
            ${progressBar}
          </div>
          <div class="wizard-actions" style="gap:8px;">${cancel}${download}</div>
        </div>
      `;
    })
    .join('');
}

let jobsClickBound = false;
function bindJobsClickHandlers() {
  if (jobsClickBound) return;
  const fileList = qs('#fileList');
  if (!fileList) return;
  jobsClickBound = true;

  fileList.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-cancel-job]');
    if (!btn) return;
    const id = Number(btn.getAttribute('data-cancel-job'));
    if (!Number.isFinite(id)) return;
    btn.disabled = true;
    try {
      await fetch(`/api/jobs/cancel/${id}`, { method: 'POST' });
      updateStatus('🛑 Job cancelled');
      jobsPollDelayMs = 2000;
      fetchAndRenderJobs();
    } catch {
      updateStatus('Failed to cancel job', true);
    } finally {
      btn.disabled = false;
    }
  });
}

let jobsPollTimer = null;
let jobsPollDelayMs = 2000;
let lastJobsJson = '';
let jobsPollingEnabled = true;
let lastJobsData = [];

function isAutoDownloadEnabled() {
  const raw = sessionStorage.getItem('autoDownloadEnabled');
  if (raw === null) return false;
  return raw === '1';
}

function setAutoDownloadEnabled(enabled) {
  sessionStorage.setItem('autoDownloadEnabled', enabled ? '1' : '0');
}

function getAutoDownloadedJobIds() {
  try {
    const raw = sessionStorage.getItem('autoDownloadedJobIds');
    const arr = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(arr) ? arr.map((x) => String(x)) : []);
  } catch {
    return new Set();
  }
}

function persistAutoDownloadedJobIds(set) {
  try {
    const arr = Array.from(set).slice(-200);
    sessionStorage.setItem('autoDownloadedJobIds', JSON.stringify(arr));
  } catch {
    // ignore
  }
}

let autoDownloadInFlight = false;
function triggerDownload(url) {
  // Use an iframe download trigger. In practice this is more reliable than an <a>.click()
  // for script-initiated downloads behind auth.
  const iframe = document.createElement('iframe');
  iframe.style.display = 'none';
  iframe.src = url;
  document.body.appendChild(iframe);
  setTimeout(() => iframe.remove(), 5000);
}

function maybeAutoDownload(jobs) {
  if (!isAutoDownloadEnabled()) return;
  if (autoDownloadInFlight) return;
  if (!Array.isArray(jobs)) return;

  const done = getAutoDownloadedJobIds();
  const next = jobs.find((j) => j && j.can_download && j.id != null && !done.has(String(j.id)));
  if (!next) return;

  autoDownloadInFlight = true;
  done.add(String(next.id));
  persistAutoDownloadedJobIds(done);

  try {
    triggerDownload(`/api/download/${next.id}`);
  } catch {
    // ignore
  } finally {
    setTimeout(() => {
      autoDownloadInFlight = false;
    }, 1500);
  }
}

async function fetchAndRenderJobs() {
  if (!jobsPollingEnabled) return;
  try {
    const r = await fetch('/api/jobs', { cache: 'no-store' });
    const parsed = await parseApiResponse(r);
    if (!parsed.ok || !Array.isArray(parsed.data)) return;

    lastJobsData = parsed.data;
    const json = JSON.stringify(parsed.data);
    if (json !== lastJobsJson) {
      lastJobsJson = json;
      renderJobs(parsed.data);
    }
    maybeAutoDownload(parsed.data);

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
  state = normalizeState(state);
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

  const usePresetVideo1 = state.videoSources.video1 === 'preset';
  const usePresetVideo2 = state.videoSources.video2 === 'preset';
  const video1PresetId = usePresetVideo1 ? String(state.presetIds.video1 || 'minecraft_parkour') : null;
  const video2PresetId = usePresetVideo2 ? String(state.presetIds.video2 || 'minecraft_parkour') : null;
  const bgMusicEnabled = Boolean(state.bgMusic.enabled);
  const bgMusicVolume = Number(state.bgMusic.volume);
  const bgMusicFileId = state.bgMusic.fileId;

  if (!isBatch) {
    const payload = {
      text: state.singleText.trim(),
      video_file_id: state.videos.video1,
      video2_file_id: state.videos.video2,
      split_screen_enabled: state.splitScreen,
      use_preset_video1: usePresetVideo1,
      use_preset_video2: usePresetVideo2,
      video1_preset_id: video1PresetId,
      video2_preset_id: video2PresetId,
      bg_music_enabled: bgMusicEnabled,
      bg_music_volume: bgMusicVolume,
      bg_music_file_id: bgMusicFileId,
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
      if (parsed.status === 429 && String(msg).toLowerCase().includes('daily limit')) {
        const el = document.querySelector('#rewardedContainer');
        if (el) el.classList.remove('hidden');
      }
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
    use_preset_video1: usePresetVideo1,
    use_preset_video2: usePresetVideo2,
    video1_preset_id: video1PresetId,
    video2_preset_id: video2PresetId,
    bg_music_enabled: bgMusicEnabled,
    bg_music_volume: bgMusicVolume,
    bg_music_file_id: bgMusicFileId,
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
    if (parsed.status === 429 && String(msg).toLowerCase().includes('daily limit')) {
      const el = document.querySelector('#rewardedContainer');
      if (el) el.classList.remove('hidden');
    }
    return;
  }
  updateStatus('✅ Batch started');
}

async function refreshYoutubeUi() {
  const statusEl = qs('#ytStatusInfo');
  const autoEl = qs('#ytAutoUpload');
  const cidEl = qs('#ytClientId');
  const csecEl = qs('#ytClientSecret');
  if (!statusEl || !autoEl) return;

  if (!isProUser()) {
    statusEl.textContent = '🔒 Pro required for YouTube integration.';
    statusEl.classList.remove('hidden');
    return;
  }

  try {
    const r = await fetch('/api/youtube/status', { cache: 'no-store' });
    const parsed = await parseApiResponse(r);
    if (!parsed.ok || !parsed.data || !parsed.data.success) {
      statusEl.textContent = 'Failed to load YouTube status.';
      statusEl.classList.remove('hidden');
      return;
    }

    const d = parsed.data;
    autoEl.checked = Boolean(d.auto_upload);
    const creds = d.has_credentials ? '✅ credentials' : '❌ credentials';
    const token = d.has_token ? '✅ token' : '❌ token';
    const enabled = d.auto_upload ? '✅ auto-upload on' : 'auto-upload off';
    const note = d.note ? ` — ${String(d.note)}` : '';
    statusEl.textContent = `${creds} | ${token} | ${enabled}${note}`;
    statusEl.classList.remove('hidden');

    if (cidEl && d.client_id) cidEl.value = String(d.client_id);
    if (csecEl && d.client_secret_masked) csecEl.placeholder = String(d.client_secret_masked);
  } catch {
    statusEl.textContent = 'Failed to load YouTube status.';
    statusEl.classList.remove('hidden');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  let state = normalizeState(loadState() || defaultState());
  const presetCfg = getPresetConfig();
  const maxStep = getMaxStep();
  if (state.step > maxStep) state.step = maxStep;

  // If preset is configured and the user has no uploaded selection yet, default to preset for video1
  if ((presetCfg.video1Path || presetCfg.soapPath) && !state.videos.video1 && state.videoSources.video1 === 'upload') {
    state.videoSources.video1 = 'preset';
  }

  const stepper = qs('#wizardStepper');
  const backBtn = qs('#backBtn');
  const nextBtn = qs('#nextBtn');
  const refreshJobsBtn = qs('#refreshJobsBtn');
  const cancelAllJobsBtn = qs('#cancelAllJobsBtn');
  const clearJobsBtn = qs('#clearJobsBtn');
  const autoDownloadToggle = qs('#autoDownloadToggle');
  const addToBatchBtn = qs('#addToBatchBtn');
  const clearTextsBtn = qs('#clearTextsBtn');
  const csvFile = qs('#csvFile');
  const generateBtn = qs('#generateBtn');
  const bgEnabled = qs('#bgMusicEnabled');
  const bgVol = qs('#bgMusicVolume');
  const bgFile = qs('#bgMusicFile');
  const ytAutoUpload = qs('#ytAutoUpload');
  const ytSaveCredsBtn = qs('#ytSaveCredsBtn');
  const ytConnectBtn = qs('#ytConnectBtn');
  const ytClientId = qs('#ytClientId');
  const ytClientSecret = qs('#ytClientSecret');

  renderWizard(state);
  refreshYoutubeUi();
  bindJobsClickHandlers();

  if (autoDownloadToggle) {
    // Always start disabled on page load. Browsers typically require a user gesture
    // for downloads; restoring "enabled" automatically makes it feel broken.
    setAutoDownloadEnabled(false);
    autoDownloadToggle.checked = false;
    autoDownloadToggle.addEventListener('change', () => {
      const enabled = Boolean(autoDownloadToggle.checked);
      setAutoDownloadEnabled(enabled);
      // Best-effort: trigger the first download immediately on this user gesture so the browser allows it.
      if (enabled) {
        maybeAutoDownload(lastJobsData);
      }
    });
  }

  if (cancelAllJobsBtn) {
    cancelAllJobsBtn.addEventListener('click', async () => {
      cancelAllJobsBtn.disabled = true;
      try {
        await fetch('/api/jobs/cancel_all', { method: 'POST' });
        updateStatus('🛑 Stopping jobs...');
        jobsPollDelayMs = 2000;
        fetchAndRenderJobs();
      } catch {
        updateStatus('Failed to stop jobs', true);
      } finally {
        cancelAllJobsBtn.disabled = false;
      }
    });
  }

  if (clearJobsBtn) {
    clearJobsBtn.addEventListener('click', async () => {
      const ok = window.confirm('Clear the entire queue and delete uploads/outputs for your account?');
      if (!ok) return;
      clearJobsBtn.disabled = true;
      try {
        await fetch('/api/jobs/clear', { method: 'POST' });
        sessionStorage.removeItem('autoDownloadedJobIds');
        lastJobsJson = '';
        updateStatus('✅ Queue cleared');
        jobsPollDelayMs = 2000;
        fetchAndRenderJobs();
      } catch {
        updateStatus('Failed to clear queue', true);
      } finally {
        clearJobsBtn.disabled = false;
      }
    });
  }

  if (bgEnabled) {
    bgEnabled.addEventListener('change', () => {
      state.bgMusic.enabled = Boolean(bgEnabled.checked);
      if (!state.bgMusic.enabled) {
        state.bgMusic.fileId = null;
        const info = qs('#bgMusicInfo');
        if (info) info.classList.add('hidden');
        const f = qs('#bgMusicFile');
        if (f) f.value = '';
      }
      saveState(state);
      renderWizard(state);
    });
  }

  if (bgVol) {
    bgVol.addEventListener('input', () => {
      const pct = Number(bgVol.value);
      const v = Number.isFinite(pct) ? Math.max(0, Math.min(40, pct)) / 100 : 0.15;
      state.bgMusic.volume = v;
      saveState(state);
      renderWizard(state);
    });
  }

  if (bgFile) {
    bgFile.addEventListener('change', async () => {
      if (!state.bgMusic.enabled) state.bgMusic.enabled = true;
      state = await uploadBgMusic(state);
      saveState(state);
      renderWizard(state);
    });
  }

  validateUploadedVideos(state).then((nextState) => {
    state = nextState;
    saveState(state);
    renderWizard(state);
  });

  if (stepper) {
    stepper.addEventListener('click', (e) => {
      const btn = e.target.closest('.wizard-step');
      if (!btn) return;
      const step = Number(btn.getAttribute('data-step'));
      const max = getMaxStep();
      if (step < 1 || step > max) return;
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

  qsa('input[name="video1Source"]').forEach((r) => {
    r.addEventListener('change', () => {
      state.videoSources.video1 = r.value === 'preset' ? 'preset' : 'upload';
      if (state.videoSources.video1 === 'preset') {
        state.videos.video1 = null;
        const info = qs('#video1Info');
        if (info) info.classList.remove('hidden');
        const input = qs('#video1');
        if (input) input.value = '';
      }
      saveState(state);
      renderWizard(state);
    });
  });

  qsa('input[name="video2Source"]').forEach((r) => {
    r.addEventListener('change', () => {
      state.videoSources.video2 = r.value === 'preset' ? 'preset' : 'upload';
      if (state.videoSources.video2 === 'preset') {
        state.videos.video2 = null;
        const info = qs('#video2Info');
        if (info) info.classList.remove('hidden');
        const input = qs('#video2');
        if (input) input.value = '';
      }
      saveState(state);
      renderWizard(state);
    });
  });

  const v1PresetSelect = qs('#video1PresetSelect');
  if (v1PresetSelect) {
    v1PresetSelect.addEventListener('change', () => {
      state.presetIds.video1 = String(v1PresetSelect.value || 'minecraft_parkour');
      saveState(state);
      renderWizard(state);
    });
  }

  const v2PresetSelect = qs('#video2PresetSelect');
  if (v2PresetSelect) {
    v2PresetSelect.addEventListener('change', () => {
      state.presetIds.video2 = String(v2PresetSelect.value || 'minecraft_parkour');
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
      state.step = Math.min(getMaxStep(), state.step + 1);
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

  if (ytSaveCredsBtn) {
    ytSaveCredsBtn.addEventListener('click', async () => {
      if (!isProUser()) return;
      const clientId = (ytClientId?.value || '').trim();
      const clientSecret = (ytClientSecret?.value || '').trim();
      if (!clientId || !clientSecret) {
        updateStatus('Enter Client ID and Client Secret first', true);
        return;
      }
      updateStatus('Saving YouTube credentials...');
      const r = await fetch('/api/youtube/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
      });
      const parsed = await parseApiResponse(r);
      if (!parsed.ok || !parsed.data || !parsed.data.success) {
        const msg = parsed.data && parsed.data.error ? parsed.data.error : parsed.raw ? parsed.raw.slice(0, 200) : 'Failed';
        updateStatus(`❌ Save failed (${parsed.status}): ${msg}`, true);
        await refreshYoutubeUi();
        return;
      }
      updateStatus('✅ Credentials saved');
      await refreshYoutubeUi();
    });
  }

  if (ytConnectBtn) {
    ytConnectBtn.addEventListener('click', async () => {
      if (!isProUser()) return;
      updateStatus('Opening YouTube consent screen...');
      const r = await fetch('/api/youtube/connect', { method: 'POST' });
      const parsed = await parseApiResponse(r);
      if (!parsed.ok || !parsed.data || !parsed.data.success || !parsed.data.auth_url) {
        const msg = parsed.data && parsed.data.error ? parsed.data.error : parsed.raw ? parsed.raw.slice(0, 200) : 'Failed';
        updateStatus(`❌ Connect failed (${parsed.status}): ${msg}`, true);
        return;
      }
      window.location.href = String(parsed.data.auth_url);
    });
  }

  if (ytAutoUpload) {
    ytAutoUpload.addEventListener('change', async () => {
      if (!isProUser()) return;
      const enabled = Boolean(ytAutoUpload.checked);
      const r = await fetch('/api/youtube/auto_upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      const parsed = await parseApiResponse(r);
      if (!parsed.ok || !parsed.data || !parsed.data.success) {
        const msg = parsed.data && parsed.data.error ? parsed.data.error : parsed.raw ? parsed.raw.slice(0, 200) : 'Failed';
        updateStatus(`❌ YouTube toggle failed (${parsed.status}): ${msg}`, true);
      } else {
        updateStatus(enabled ? '✅ Auto-upload enabled' : '✅ Auto-upload disabled');
      }
      await refreshYoutubeUi();
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


