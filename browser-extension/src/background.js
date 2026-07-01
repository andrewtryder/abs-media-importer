// Background service worker for the yt-abs-importer extension.
// Owns the in-memory settings cache, the context menu, the API call to queue videos,
// and WebSocket connections for real-time job status updates.

import { DEFAULT_SETTINGS, STORAGE_KEYS, isYouTubeWatchUrl, loadSettings } from './settings.js';
import { setStatusMessage, renderProgress, formatError, normalizeServerUrl, isYouTubeVideoUrl } from './ui.js';

const CONTEXT_MENU_ID = 'ytabs-queue-video';

// In-memory cache of settings, refreshed from storage on startup and on changes.
let settings = { ...DEFAULT_SETTINGS };

// Active WebSocket connections for job status updates
const activeWebSockets = new Map();

// Build the request body for the queue endpoint from the current settings + a URL.
function buildRequestBody(url) {
  return {
    url,
    destination_folder: settings.defaultDestinationFolder || '',
    output_title: '',
    embed_metadata: settings.embedMetadata,
    embed_thumbnail: settings.embedThumbnail,
    embed_chapters: settings.embedChapters,
    trigger_abs_scan: settings.triggerAbsScan,
  };
}

function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (settings.apiToken) headers['Authorization'] = `Bearer ${settings.apiToken}`;
  return headers;
}

async function queueVideo(url) {
  if (!settings.serverUrl) {
    throw new Error('Server URL not configured. Open the extension options to set it.');
  }
  const base = settings.serverUrl.replace(/\/+$/, '');
  const response = await fetch(`${base}/api/extension/queue`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(buildRequestBody(url)),
  });
  if (!response.ok) {
    let detail;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = await response.text();
    }
    throw new Error(`HTTP ${response.status}: ${detail || response.statusText}`);
  }
  return response.json();
}

function notify(message, title = 'yt-abs-importer') {
  try {
    chrome.notifications?.create({
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon.svg'),
      title,
      message: String(message),
    });
  } catch (err) {
    console.error('Notification failed:', err);
  }
}

async function openJobPage(jobUrl) {
  if (!jobUrl) return;
  const base = settings.serverUrl.replace(/\/+$/, '');
  await chrome.tabs.create({ url: `${base}${jobUrl}` });
}

async function handleQueue(url) {
  if (!isYouTubeWatchUrl(url)) {
    notify('Not a YouTube video URL.');
    return;
  }
  try {
    const data = await queueVideo(url);
    notify(`Queued: ${data.title || data.job_id}`);
    await openJobPage(data.job_url);

    // Start WebSocket connection for real-time updates
    startJobWebSocket(data.job_id);

    // Send message to popup to update UI
    chrome.runtime.sendMessage({
      action: 'queueSuccess',
      jobId: data.job_id,
      title: data.title,
      uploader: data.uploader,
      status: 'queued',
      progress: 0,
      progressLabel: 'Queued',
      jobUrl: data.job_url,
      serverUrl: settings.serverUrl,
    }).catch(err => {
      console.error('Failed to send queue success message to popup:', err);
    });

  } catch (err) {
    console.error('Queue failed:', err);
    notify(err.message || 'Failed to queue video');

    // Send error message to popup
    chrome.runtime.sendMessage({
      action: 'queueError',
      error: err.message || 'Failed to queue video',
    }).catch(err => {
      console.error('Failed to send queue error message to popup:', err);
    });
  }
}

function createContextMenus() {
  chrome.contextMenus.remove(CONTEXT_MENU_ID, () => {
    // "Cannot find menu item..." is expected on first run.
    const removeError = chrome.runtime.lastError;
    if (removeError && !removeError.message?.includes('Cannot find menu item')) {
      console.error('Context menu cleanup failed:', removeError.message);
      return;
    }

    chrome.contextMenus.create({
      id: CONTEXT_MENU_ID,
      title: 'Send to yt-abs-importer',
      contexts: ['page', 'link'],
      documentUrlPatterns: [
        'https://www.youtube.com/*',
        'https://youtube.com/*',
        'https://m.youtube.com/*',
        'https://youtu.be/*',
      ],
    }, () => {
      const createError = chrome.runtime.lastError;
      if (createError && !createError.message?.includes('duplicate id')) {
        console.error('Context menu setup failed:', createError.message);
      }
    });
  });
}

async function refreshSettings() {
  settings = await loadSettings();

  // Stop any existing WebSocket connections
  for (const [jobId, ws] of activeWebSockets) {
    ws.close(1000, 'Settings updated');
  }
  activeWebSockets.clear();
}

// WebSocket connection manager
function startJobWebSocket(jobId) {
  if (!settings.serverUrl) {
    console.error('Cannot start WebSocket: server URL not configured');
    return null;
  }

  const baseUrl = settings.serverUrl.replace(/\/+$/, '');
  const wsUrl = `${baseUrl.startsWith('http://') ? 'ws://' : 'wss://'}${baseUrl.replace(/^https?:\/\//, '')}/api/ws/jobs/${jobId}`;

  const ws = new WebSocket(wsUrl);

  // Add auth token if configured
  if (settings.apiToken) {
    // WebSocket auth via query parameter
    wsUrl += `?token=${settings.apiToken}`;
    ws = new WebSocket(wsUrl);
  }

  ws.onopen = function() {
    console.log(`WebSocket connected for job ${jobId}`);
    // Send keepalive message to prevent timeout
    ws.keepaliveInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 30000);

    // Notify popup that WebSocket is connected
    chrome.runtime.sendMessage({
      action: 'websocketConnected',
      jobId: jobId,
    }).catch(err => {
      console.error('Failed to notify popup of WebSocket connection:', err);
    });
  };

  ws.onmessage = function(event) {
    try {
      const data = JSON.parse(event.data);

      if (data.type === 'pong') {
        // Keepalive response, nothing to do
        return;
      }

      if (data.type === 'job_update') {
        // Forward job update to popup
        chrome.runtime.sendMessage({
          action: 'jobUpdate',
          job: data.job,
        }).catch(err => {
          console.error('Failed to forward job update to popup:', err);
        });
      }
    } catch (error) {
      console.error('Error parsing WebSocket message:', error);
    }
  };

  ws.onclose = function(event) {
    console.log(`WebSocket closed for job ${jobId}: code=${event.code}, reason=${event.reason}`);

    // Clear keepalive interval
    if (ws.keepaliveInterval) {
      clearInterval(ws.keepaliveInterval);
    }

    // Remove from active connections
    activeWebSockets.delete(jobId);

    // Notify popup that WebSocket is disconnected
    chrome.runtime.sendMessage({
      action: 'websocketDisconnected',
      jobId: jobId,
      code: event.code,
      reason: event.reason,
    }).catch(err => {
      console.error('Failed to notify popup of WebSocket disconnection:', err);
    });

    // Attempt to reconnect if not a normal closure
    if (event.code !== 1000 && event.code !== 1001) {
      console.log(`Attempting to reconnect WebSocket for job ${jobId} in 5 seconds...`);
      setTimeout(() => startJobWebSocket(jobId), 5000);
    }
  };

  ws.onerror = function(error) {
    console.error(`WebSocket error for job ${jobId}:`, error);

    chrome.runtime.sendMessage({
      action: 'websocketError',
      jobId: jobId,
      error: error,
    }).catch(err => {
      console.error('Failed to notify popup of WebSocket error:', err);
    });
  };

  // Store WebSocket connection
  activeWebSockets.set(jobId, ws);

  return ws;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || typeof message.action !== 'string') {
    sendResponse({ ok: false, error: 'Unknown message' });
    return false;
  }

  if (message.action === 'getSettings') {
    sendResponse({ ok: true, settings });
    return false;
  }

  if (message.action === 'queue') {
    handleQueue(message.url).then(
      () => sendResponse({ ok: true }),
      (err) => sendResponse({ ok: false, error: err.message || String(err) })
    );
    return true; // keep channel open for async response
  }

  if (message.action === 'startWebSocket') {
    // Start WebSocket for a job ID
    const ws = startJobWebSocket(message.jobId);
    sendResponse({ ok: true, wsActive: ws !== null });
    return false;
  }

  if (message.action === 'stopWebSocket') {
    // Stop WebSocket for a job ID
    const ws = activeWebSockets.get(message.jobId);
    if (ws) {
      ws.close(1000, 'Stopped by user');
      activeWebSockets.delete(message.jobId);
    }
    sendResponse({ ok: true });
    return false;
  }

  if (message.action === 'getActiveWebSockets') {
    // Return list of active job IDs
    sendResponse({
      ok: true,
      activeJobs: Array.from(activeWebSockets.keys()),
    });
    return false;
  }

  sendResponse({ ok: false, error: `Unknown action: ${message.action}` });
  return false;
});

// Keep cache fresh when options page writes to storage.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'local') return;
  for (const key of STORAGE_KEYS) {
    if (key in changes) settings[key] = changes[key].newValue;
  }
});

// Initialize eagerly for the case where the worker wakes up without onInstalled.
refreshSettings().then(createContextMenus);