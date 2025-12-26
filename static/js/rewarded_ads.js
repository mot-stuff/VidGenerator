function qs(sel) {
  return document.querySelector(sel);
}

function setHidden(el, hidden) {
  if (!el) return;
  el.classList.toggle('hidden', hidden);
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

function loadGpt() {
  if (window.googletag && window.googletag.apiReady) return Promise.resolve();
  if (window.__gptLoadingPromise) return window.__gptLoadingPromise;

  window.googletag = window.googletag || { cmd: [] };

  window.__gptLoadingPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src*="googletagservices.com/tag/js/gpt.js"]');
    if (existing) {
      window.googletag.cmd.push(() => resolve());
      return;
    }
    const s = document.createElement('script');
    s.src = 'https://www.googletagservices.com/tag/js/gpt.js';
    s.async = true;
    s.onload = () => window.googletag.cmd.push(() => resolve());
    s.onerror = () => reject(new Error('Failed to load GPT'));
    document.head.appendChild(s);
  });

  return window.__gptLoadingPromise;
}

async function fetchStatus() {
  const r = await fetch('/api/status', { cache: 'no-store' });
  const parsed = await parseApiResponse(r);
  if (!parsed.ok || !parsed.data || !parsed.data.user) return null;
  return parsed.data.user;
}

function updateProfileQuotaUi(user) {
  const el = qs('#quotaSummaryText');
  if (!el || !user) return;
  const dailyRemaining = Number(user.daily_remaining ?? 0);
  const dailyQuota = Number(user.daily_quota ?? 0);
  const bonus = Number(user.bonus_credits ?? 0);
  const bonusTxt = bonus > 0 ? ` (+${bonus} bonus)` : '';
  el.textContent = `${dailyRemaining} / ${dailyQuota}${bonusTxt}`;
}

async function startRewardedFlow({ adUnitPath }) {
  const watchBtn = qs('#watchAdBtn');
  const container = qs('#rewardedContainer');
  if (!watchBtn || !container) return;

  watchBtn.disabled = true;

  const startResp = await fetch('/api/rewarded/start', { method: 'POST' });
  const startParsed = await parseApiResponse(startResp);
  if (!startParsed.ok || !startParsed.data || !startParsed.data.success) {
    const msg = startParsed.data && startParsed.data.error ? startParsed.data.error : startParsed.raw || 'Failed';
    watchBtn.disabled = false;
    if (window.updateStatus) window.updateStatus(`❌ Rewarded start failed: ${msg}`, true);
    return;
  }

  const ticketId = startParsed.data.ticket_id;

  try {
    await loadGpt();
  } catch (e) {
    watchBtn.disabled = false;
    if (window.updateStatus) window.updateStatus(`❌ ${String(e.message || e)}`, true);
    return;
  }

  window.googletag = window.googletag || { cmd: [] };
  window.googletag.cmd.push(() => {
    const googletag = window.googletag;
    let rewardedSlot = null;
    let granted = false;

    try {
      rewardedSlot = googletag
        .defineOutOfPageSlot(adUnitPath, googletag.enums.OutOfPageFormat.REWARDED)
        .addService(googletag.pubads());

      googletag.enableServices();
    } catch (e) {
      watchBtn.disabled = false;
      if (window.updateStatus) window.updateStatus(`❌ Rewarded setup failed`, true);
      return;
    }

    const onReady = (evt) => {
      try {
        evt.makeRewardedVisible();
      } catch {
        // ignore
      }
    };

    const onGranted = async () => {
      granted = true;
      const redeemResp = await fetch('/api/rewarded/redeem', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticket_id: ticketId }),
      });
      const redeemParsed = await parseApiResponse(redeemResp);
      if (!redeemParsed.ok || !redeemParsed.data || !redeemParsed.data.success) {
        const msg = redeemParsed.data && redeemParsed.data.error ? redeemParsed.data.error : redeemParsed.raw || 'Failed';
        if (window.updateStatus) window.updateStatus(`❌ Reward failed: ${msg}`, true);
        watchBtn.disabled = false;
        return;
      }

      if (window.updateStatus) window.updateStatus('✅ Reward granted: +1 generation');
      watchBtn.disabled = true;
      setHidden(container, true);

      fetchStatus().then((u) => updateProfileQuotaUi(u));
    };

    const onClosed = () => {
      try {
        googletag.pubads().removeEventListener('rewardedSlotReady', onReady);
        googletag.pubads().removeEventListener('rewardedSlotGranted', onGranted);
        googletag.pubads().removeEventListener('rewardedSlotClosed', onClosed);
      } catch {
        // ignore
      }
      try {
        if (rewardedSlot) googletag.destroySlots([rewardedSlot]);
      } catch {
        // ignore
      }
      if (!granted) watchBtn.disabled = false;
    };

    googletag.pubads().addEventListener('rewardedSlotReady', onReady);
    googletag.pubads().addEventListener('rewardedSlotGranted', onGranted);
    googletag.pubads().addEventListener('rewardedSlotClosed', onClosed);

    try {
      googletag.display(rewardedSlot);
    } catch {
      watchBtn.disabled = false;
      if (window.updateStatus) window.updateStatus('❌ Rewarded display failed', true);
    }
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  const adUnitPath = (qs('#rewardedConfig')?.getAttribute('data-ad-unit-path') || '').trim();
  const container = qs('#rewardedContainer');
  const watchBtn = qs('#watchAdBtn');
  if (!container || !watchBtn) return;

  const user = await fetchStatus();
  if (user) updateProfileQuotaUi(user);

  const canShow = user && !user.is_admin && Number(user.daily_remaining ?? 0) <= 0 && Number(user.bonus_credits ?? 0) <= 0;
  setHidden(container, !canShow);
  if (!canShow) return;

  if (!adUnitPath) {
    watchBtn.disabled = true;
    if (!qs('#rewardedConfigMissingHint')) {
      const hint = document.createElement('div');
      hint.id = 'rewardedConfigMissingHint';
      hint.className = 'wizard-hint';
      hint.style.marginTop = '8px';
      hint.textContent = 'Rewarded ads are not configured. Set GAM_REWARDED_AD_UNIT_PATH on the server and restart.';
      watchBtn.insertAdjacentElement('afterend', hint);
    }
    return;
  }

  watchBtn.disabled = false;
  watchBtn.addEventListener('click', async () => {
    await startRewardedFlow({ adUnitPath });
  });
});


