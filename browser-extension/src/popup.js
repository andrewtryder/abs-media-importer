import { isYouTubeWatchUrl } from './settings.js';

function $(id) { return document.getElementById(id); }

function setExtensionVersionLabel() {
  const versionEl = $('extension-version');
  if (!versionEl) return;
  const runtimeVersion = chrome.runtime?.getManifest?.().version;
  versionEl.textContent = runtimeVersion || 'unknown';
}

function setStatus(text, className = 'pending') {
  const el = $('status');
  el.textContent = text;
  el.className = className;
}

function updateStatusDot(connected) {
  const dot = $('status-dot');
  if (connected) {
    dot.className = 'status-dot connected';
  } else {
    dot.className = 'status-dot disconnected';
  }
}

let activeJobId = null;

async function getActiveTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url || '';
}

async function getSettings() {
  const res = await chrome.runtime.sendMessage({ action: 'getSettings' });
  if (!res?.ok) throw new Error(res?.error || 'Could not load settings');
  return res.settings;
}

async function queueVideo(url, allowReimport = false) {
  try {
    const res = await chrome.runtime.sendMessage({ action: 'queue', url, allowReimport });
    if (!res?.ok) throw new Error(res?.error || 'Queue failed');
    return res;
  } catch (err) {
    throw err;
  }
}

function renderQueuedJob(data) {
  // Show result section
  const result = $('result');
  const queueForm = $('queue-form');

  result.classList.add('visible');
  queueForm.style.display = 'none';

  // Update job info
  $('job-id').textContent = data.job_id;
  $('queued-title').textContent = data.title || 'Unknown Title';
  $('queued-uploader').textContent = `by ${data.uploader || 'Unknown'}`;

  // Update job link (construct proper URL)
  const jobLink = $('job-link');
  const serverUrl = data.serverUrl || 'http://localhost:8080';
  if (data.job_url?.startsWith('http://') || data.job_url?.startsWith('https://')) {
    jobLink.href = data.job_url;
  } else {
    jobLink.href = `${serverUrl}${data.job_url || ''}`;
  }

  // Render initial status
  renderJobStatus(data);
}

function renderJobStatus(data) {
  // Update status badge
  const statusBadge = $('status-badge');
  const statusText = $('status-text');

  if (data.status === 'queued') {
    statusBadge.className = 'status-badge status-queued';
    statusBadge.textContent = 'queued';
    statusText.textContent = 'Queued';
  } else if (data.status === 'running' || data.status === 'downloading') {
    statusBadge.className = 'status-badge status-running';
    statusBadge.textContent = data.status;
    statusText.textContent = 'Processing';
  } else if (data.status === 'succeeded') {
    statusBadge.className = 'status-badge status-succeeded';
    statusBadge.textContent = 'succeeded';
    statusText.textContent = 'Complete';
  } else if (data.status === 'failed') {
    statusBadge.className = 'status-badge status-failed';
    statusBadge.textContent = 'failed';
    statusText.textContent = 'Failed';
  } else if (data.status === 'cancelled') {
    statusBadge.className = 'status-badge status-cancelled';
    statusBadge.textContent = 'cancelled';
    statusText.textContent = 'Cancelled';
  }

  // Update progress bar
  const progressBarFill = $('progress-bar-fill');
  const progressPercentage = $('progress-percentage');
  const progressLabel = $('progress-label');

  const progress = data.progress_percent || data.progress || 0;
  progressBarFill.style.width = `${progress}%`;
  progressPercentage.textContent = `${Math.round(progress)}%`;
  progressLabel.textContent = data.progress_label || `Stage: ${data.phase || data.status}` || 'Processing...';

  // Update status dot based on job status
  if (data.status === 'succeeded' || data.status === 'failed' || data.status === 'cancelled') {
    updateStatusDot(false); // Terminal status
  } else {
    updateStatusDot(true); // Active job
  }
}

async function init() {
  let url;
  try {
    url = await getActiveTabUrl();
  } catch (err) {
    $('video').textContent = 'Could not read current tab.';
    setStatus('Error reading tab', 'err');
    return;
  }

  if (!isYouTubeWatchUrl(url)) {
    $('video').innerHTML = 'Not a YouTube video page.';
    setStatus('Please navigate to a YouTube video page', 'err');
    return;
  }

  // Show current tab info
  const videoElement = $('video');
  videoElement.innerHTML = `Current video:<br><a href="${url}" target="_blank" style="word-break: break-all;">${url}</a>`;

  // Try to load settings
  let serverUrl = '';
  let settings = {};
  try {
    settings = await getSettings();
    serverUrl = settings.serverUrl || '';
    $('allow-reimport').checked = Boolean(settings.allowReimport);
  } catch (err) {
    console.error('Error loading settings:', err);
    setStatus('Failed to load extension settings', 'err');
  }

  if (!serverUrl) {
    setStatus('Set the server URL in options first', 'err');
  } else {
    setStatus('Ready to queue', 'ok');
  }

  // Enable queue button
  const queueButton = $('queue');
  queueButton.disabled = false;
}

async function onQueue() {
  const url = await getActiveTabUrl();
  if (!isYouTubeWatchUrl(url)) {
    setStatus('Not a YouTube video URL', 'err');
    return;
  }

  const allowReimport = $('allow-reimport')?.checked || false;

  const queueButton = $('queue');
  queueButton.disabled = true;
  queueButton.textContent = 'Queuing…';

  try {
    setStatus('Queuing video...', 'pending');

    const data = await queueVideo(url, allowReimport);

    if (data.ok) {
      activeJobId = data.job_id || null;
      setStatus('Video queued successfully!', 'ok');
      renderQueuedJob(data);

      // Ask background service worker to own the WebSocket lifecycle.
      chrome.runtime.sendMessage({ action: 'startWebSocket', jobId: data.job_id }).catch((err) => {
        console.error('Failed to request WebSocket start:', err);
      });
    } else {
      throw new Error(data.error || 'Queue failed');
    }
  } catch (err) {
    console.error('Queue failed:', err);
    setStatus(`Queue failed: ${err.message}`, 'err');
  } finally {
    queueButton.disabled = false;
    queueButton.textContent = 'Queue video';
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (!message || typeof message.action !== 'string') return;

  if (message.action === 'queueError') {
    setStatus(`Queue failed: ${message.error || 'Unknown error'}`, 'err');
    updateStatusDot(false);
    return;
  }

  if (message.action === 'websocketConnected') {
    if (!activeJobId || message.jobId === activeJobId) updateStatusDot(true);
    return;
  }

  if (message.action === 'websocketDisconnected' || message.action === 'websocketError') {
    if (!activeJobId || message.jobId === activeJobId) updateStatusDot(false);
    return;
  }

  if (message.action === 'jobUpdate' && message.job) {
    const job = message.job;
    if (activeJobId && job.id && job.id !== activeJobId) return;

    renderJobStatus(job);
    if (job.status === 'failed' && job.error_message) {
      setStatus(`Queue failed: ${job.error_message}`, 'err');
    } else if (job.status === 'succeeded') {
      setStatus('Completed successfully', 'ok');
    }
  }
});

// Event listeners
$('queue').addEventListener('click', onQueue);
setExtensionVersionLabel();

// Initialize
init();
