import { isYouTubeWatchUrl } from './settings.js';

function $(id) { return document.getElementById(id); }

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

async function getActiveTabUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.url || '';
}

async function getSettings() {
  const res = await chrome.runtime.sendMessage({ action: 'getSettings' });
  if (!res?.ok) throw new Error(res?.error || 'Could not load settings');
  return res.settings;
}

async function queueVideo(url) {
  try {
    const res = await chrome.runtime.sendMessage({ action: 'queue', url });
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
  if (data.job_url) {
    jobLink.href = data.job_url;
  } else {
    // Fallback to server URL
    const serverUrl = data.serverUrl || 'http://localhost:8080';
    jobLink.href = `${serverUrl}${data.job_url}`;
  }

  // Render initial status
  renderJobStatus(data);
}

function renderJobStatus(data) {
  // Update status badge
  const statusBadge = $('status-badge');
  const statusText = $('#status-text');

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
  const progressBarFill = $('#progress-bar-fill');
  const progressPercentage = $('#progress-percentage');
  const progressLabel = $('#progress-label');

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
  const queueButton = $('#queue');
  queueButton.disabled = false;
}

async function onQueue() {
  const url = await getActiveTabUrl();
  if (!isYouTubeWatchUrl(url)) {
    setStatus('Not a YouTube video URL', 'err');
    return;
  }

  const queueButton = $('#queue');
  queueButton.disabled = true;
  queueButton.textContent = 'Queuing…';

  try {
    setStatus('Queuing video...', 'pending');

    const data = await queueVideo(url);

    if (data.ok) {
      setStatus('Video queued successfully!', 'ok');
      renderQueuedJob(data);

      // Start WebSocket connection for real-time updates
      startWebSocketConnection(data.job_id);
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

function startWebSocketConnection(jobId) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.host;
  const wsUrl = `${protocol}//${host}/api/ws/jobs/${jobId}`;

  const ws = new WebSocket(wsUrl);

  ws.onopen = function() {
    console.log('WebSocket connected');
    updateStatusDot(true);
  };

  ws.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'job_update') {
        renderJobStatus(data.job);
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };

  ws.onerror = function(error) {
    console.error('WebSocket error:', error);
    updateStatusDot(false);
  };

  ws.onclose = function(event) {
    console.log('WebSocket closed:', event.code, event.reason);
    updateStatusDot(false);

    // Attempt to reconnect after 5 seconds
    if (event.code !== 1000) { // Not a normal closure
      setTimeout(() => {
        startWebSocketConnection(jobId);
      }, 5000);
    }
  };
}

// Event listeners
$('#queue').addEventListener('click', onQueue);

// Initialize
init();