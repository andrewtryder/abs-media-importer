import { DEFAULT_SETTINGS, STORAGE_KEYS, loadSettings, saveSettings } from './settings.js';

function $(id) { return document.getElementById(id); }

function populate(settings) {
  $('serverUrl').value = settings.serverUrl || '';
  $('apiToken').value = settings.apiToken || '';
  $('defaultDestinationFolder').value = settings.defaultDestinationFolder || '';
  $('embedMetadata').checked = settings.embedMetadata;
  $('embedThumbnail').checked = settings.embedThumbnail;
  $('embedChapters').checked = settings.embedChapters;
  $('triggerAbsScan').checked = settings.triggerAbsScan;
}

function collect() {
  return {
    serverUrl: $('serverUrl').value.trim(),
    apiToken: $('apiToken').value.trim(),
    defaultDestinationFolder: $('defaultDestinationFolder').value.trim(),
    embedMetadata: $('embedMetadata').checked,
    embedThumbnail: $('embedThumbnail').checked,
    embedChapters: $('embedChapters').checked,
    triggerAbsScan: $('triggerAbsScan').checked,
  };
}

function setStatus(text, ok = true) {
  const el = $('status');
  el.textContent = text;
  el.className = ok ? 'ok' : 'err';
}

function updateStatusPanel(statusData, settings) {
  // Status panel elements
  const statusIndicator = document.getElementById('status-indicator');
  const statusText = document.getElementById('status-text');
  const connectionStatus = document.getElementById('connection-status');
  const dryRunStatus = document.getElementById('dry-run-status');
  const absConfigured = document.getElementById('abs-configured');
  const playlistsAllowed = document.getElementById('playlists-allowed');
  const channelsAllowed = document.getElementById('channels-allowed');
  const apiStatus = document.getElementById('api-status');

  // Update connection status indicator
  if (statusData.extension_api_enabled && statusData.auth_required) {
    statusIndicator.className = 'status-indicator status-connected';
    statusIndicator.title = 'Extension API enabled with token required';
    connectionStatus.textContent = 'Connected';
    apiStatus.textContent = 'API Auth Required';
    apiStatus.className = 'status-badge status-warning';
  } else if (statusData.extension_api_enabled && !statusData.auth_required) {
    statusIndicator.className = 'status-indicator status-connected';
    statusIndicator.title = 'Extension API enabled without token';
    connectionStatus.textContent = 'Connected';
    apiStatus.textContent = 'API No Auth';
    apiStatus.className = 'status-badge status-success';
  } else {
    statusIndicator.className = 'status-indicator status-disconnected';
    statusIndicator.title = 'Extension API disabled';
    connectionStatus.textContent = 'Disconnected';
    apiStatus.textContent = 'API Disabled';
    apiStatus.className = 'status-badge status-error';
  }

  // Update dry run status
  dryRunStatus.textContent = statusData.dry_run ? 'Dry run enabled' : 'Production mode';
  dryRunStatus.className = `status-badge ${statusData.dry_run ? 'status-warning' : 'status-success'}`;

  // Update ABS configured status
  const isAbsConfigured = statusData.abs_configured;
  absConfigured.textContent = isAbsConfigured ? 'Configured' : 'Not configured';
  absConfigured.className = `status-badge ${isAbsConfigured ? 'status-success' : 'status-error'}`;

  // Update playlists allowed
  playlistsAllowed.textContent = statusData.allow_playlists ? 'Allowed' : 'Restricted';
  playlistsAllowed.className = `status-badge ${statusData.allow_playlists ? 'status-success' : 'status-error'}`;

  // Update channels allowed
  channelsAllowed.textContent = statusData.allow_channels ? 'Allowed' : 'Restricted';
  channelsAllowed.className = `status-badge ${statusData.allow_channels ? 'status-success' : 'status-error'}`;

  // Update overall status
  let overallStatus = 'OK';
  let overallClass = 'status-success';

  if (!statusData.extension_api_enabled) {
    overallStatus = 'API Disabled';
    overallClass = 'status-error';
  } else if (statusData.extension_api_enabled && statusData.auth_required && !statusData.ok) {
    overallStatus = 'Invalid Token';
    overallClass = 'status-error';
  } else if (statusData.dry_run) {
    overallStatus = 'Dry Run';
    overallClass = 'status-warning';
  } else {
    overallStatus = 'Production';
    overallClass = 'status-success';
  }

  document.getElementById('overall-status').textContent = overallStatus;
  document.getElementById('overall-status-indicator').className = `status-indicator ${overallClass}`;
}

async function loadStatusFromServer(serverUrl, apiToken = null) {
  if (!serverUrl) {
    throw new Error('Server URL is required');
  }

  try {
    const base = serverUrl.replace(/\/+$/, '');
    const headers = {};
    if (apiToken) headers['Authorization'] = `Bearer ${apiToken}`;

    const res = await fetch(`${base}/api/extension/status`, { headers });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    return data;
  } catch (err) {
    throw new Error(`Failed to load server status: ${err.message}`);
  }
}

async function onSave() {
  try {
    await saveSettings(collect());

    // Refresh status after saving
    setStatus('Settings saved, testing connection...', true);
    await onTest();
  } catch (err) {
    setStatus(`Save failed: ${err.message}`, false);
  }
}

async function onTest() {
  const { serverUrl, apiToken } = collect();

  if (!serverUrl) {
    setStatus('Enter a server URL first.', false);
    return;
  }

  setStatus('Testing connection…', true);

  // Show initial status panel loading state
  document.getElementById('status-panel').style.display = 'block';

  try {
    const statusData = await loadStatusFromServer(serverUrl, apiToken);

    // Update status panel with server response
    updateStatusPanel(statusData, collect());

    // Update local settings with server data if needed
    const localSettings = await loadSettings();
    const needsUpdate = false;

    if (needsUpdate) {
      await saveSettings({
        serverUrl: statusData.serverUrl || localSettings.serverUrl,
        apiToken: statusData.apiToken || localSettings.apiToken,
        defaultDestinationFolder: localSettings.defaultDestinationFolder,
        embedMetadata: localSettings.embedMetadata,
        embedThumbnail: localSettings.embedThumbnail,
        embedChapters: localSettings.embedChapters,
        triggerAbsScan: localSettings.triggerAbsScan,
      });
    }

    setStatus(statusData.ok ? 'Connected successfully!' : 'Server responded but not OK', statusData.ok ? true : false);

  } catch (err) {
    console.error('Test connection failed:', err);

    // Hide status panel on error
    document.getElementById('status-panel').style.display = 'none';

    setStatus(`Connection failed: ${err.message}`, false);
  }
}

// Toggle password visibility for API token
$('apiToken').type = 'password';
const togglePassword = document.createElement('button');
togglePassword.type = 'button';
togglePassword.textContent = '👁';
togglePassword.style.position = 'absolute';
togglePassword.style.right = '8px';
togglePassword.style.top = '8px';
togglePassword.style.background = 'none';
togglePassword.style.border = 'none';
togglePassword.style.cursor = 'pointer';
togglePassword.style.fontSize = '1rem';

let passwordVisible = false;
togglePassword.onclick = function(e) {
  e.preventDefault();
  passwordVisible = !passwordVisible;
  $('apiToken').type = passwordVisible ? 'text' : 'password';
  this.textContent = passwordVisible ? '🙈' : '👁';
};

$('apiToken').parentElement.style.position = 'relative';
$('apiToken').parentElement.appendChild(togglePassword);

(async () => {
  populate(await loadSettings());
  $('save').addEventListener('click', onSave);
  $('test').addEventListener('click', onTest);

  // Optional: Auto-test on page load if server URL is configured
  const initialSettings = await loadSettings();
  if (initialSettings.serverUrl) {
    // Small delay to allow page render
    setTimeout(async () => {
      try {
        const statusData = await loadStatusFromServer(initialSettings.serverUrl, initialSettings.apiToken);
        updateStatusPanel(statusData, initialSettings);
        document.getElementById('status-panel').style.display = 'block';
        setStatus('Connection status loaded', true);
      } catch (err) {
        console.log('Initial status load failed:', err);
        document.getElementById('status-panel').style.display = 'none';
      }
    }, 500);
  }
})();