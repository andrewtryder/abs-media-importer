// Background service worker for the abs-media-importer extension.
// Owns the in-memory settings cache, the context menu, the API call to queue videos,
// and WebSocket connections for real-time job status updates.

import { DEFAULT_SETTINGS, STORAGE_KEYS, isYouTubeWatchUrl, loadSettings } from './settings.js';

const CONTEXT_MENU_ID = 'abs-media-importer-queue-video';

// In-memory cache of settings, refreshed from storage on startup and on changes.
let settings = { ...DEFAULT_SETTINGS };

// Active WebSocket connections for job status updates
const activeWebSockets = new Map();

// Build the request body for the queue endpoint from the current settings + a URL.
function buildRequestBody(url, options = {}) {
  const allowReimport =
    typeof options.allowReimport === 'boolean'
      ? options.allowReimport
      : settings.allowReimport;
  return {
    url,
    destination_folder: settings.defaultDestinationFolder || '',
    output_title: '',
    embed_metadata: settings.embedMetadata,
    embed_thumbnail: settings.embedThumbnail,
    embed_chapters: settings.embedChapters,
    trigger_abs_scan: settings.triggerAbsScan,
    allow_reimport: allowReimport,
  };
}

function authHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (settings.authEnabled && settings.apiToken) {
    headers['Authorization'] = `Bearer ${settings.apiToken}`;
  }
  return headers;
}

async function queueVideo(url, options = {}) {
  if (!settings.serverUrl) {
    throw new Error('Server URL not configured. Open the extension options to set it.');
  }
  const base = settings.serverUrl.replace(/\/+$/, '');
  const response = await fetch(`${base}/api/extension/queue`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify(buildRequestBody(url, options)),
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

function notify(message, title = 'ABS Media Importer') {
  try {
    chrome.notifications?.create({
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/icon-128.png'),
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

async function handleQueue(url, options = {}) {
  if (!isYouTubeWatchUrl(url)) {
    const err = new Error('Not a YouTube video URL.');
    notify(err.message);
    throw err;
  }
  try {
    const data = await queueVideo(url, options);
    if (!data?.job_id) {
      throw new Error('Queue response missing job_id');
    }
    const responsePayload = {
      ok: true,
      job_id: data.job_id,
      rq_job_id: data.rq_job_id || null,
      status: data.status || 'queued',
      title: data.title || null,
      uploader: data.uploader || null,
      job_url: data.job_url || null,
      serverUrl: settings.serverUrl,
    };

    notify(`Queued successfully: ${responsePayload.title || responsePayload.job_id}`);
    await openJobPage(responsePayload.job_url);

    // Start WebSocket connection for real-time updates
    startJobWebSocket(responsePayload.job_id);

    // Send message to popup to update UI
    chrome.runtime.sendMessage({
      action: 'queueSuccess',
      jobId: responsePayload.job_id,
      job_id: responsePayload.job_id,
      title: responsePayload.title,
      uploader: responsePayload.uploader,
      status: responsePayload.status,
      progress: 0,
      progressLabel: 'Queued',
      jobUrl: responsePayload.job_url,
      job_url: responsePayload.job_url,
      serverUrl: settings.serverUrl,
    }).catch(err => {
      console.error('Failed to send queue success message to popup:', err);
    });
    return responsePayload;
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
    throw err;
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
      title: 'Send to ABS Media Importer',
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

function urlFromContextMenu(info, tab) {
  return info.linkUrl || info.pageUrl || tab?.url || '';
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
function buildJobWebSocketUrl(jobId) {
  const baseUrl = settings.serverUrl.replace(/\/+$/, '');
  const base = new URL(baseUrl);
  const wsProtocol = base.protocol === 'http:' ? 'ws:' : 'wss:';
  const wsUrl = new URL(`${wsProtocol}//${base.host}/api/ws/jobs/${encodeURIComponent(jobId)}`);
  if (settings.authEnabled && settings.apiToken) {
    wsUrl.searchParams.set('token', settings.apiToken);
  }
  return wsUrl.toString();
}

function startJobWebSocket(jobId) {
  if (!settings.serverUrl) {
    console.error('Cannot start WebSocket: server URL not configured');
    return null;
  }

  const existing = activeWebSockets.get(jobId);
  if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
    return existing;
  }
  let ws;
  try {
    ws = new WebSocket(buildJobWebSocketUrl(jobId));
  } catch (error) {
    console.error(`Cannot start WebSocket for job ${jobId}:`, error);
    return null;
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
    handleQueue(message.url, { allowReimport: Boolean(message.allowReimport) }).then(
      (data) => sendResponse(data),
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

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== CONTEXT_MENU_ID) return;
  const url = urlFromContextMenu(info, tab);
  handleQueue(url).catch((err) => {
    console.error('Context menu queue failed:', err);
  });
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
