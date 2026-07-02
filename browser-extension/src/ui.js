// Shared UI helper functions for abs-media-importer browser extension
// Lightweight, dependency-free utility library

/**
 * Set status message with appropriate styling
 * @param {string} text - Status message to display
 * @param {string} className - CSS class for styling (default: 'pending')
 */
export function setStatusMessage(text, className = 'pending') {
  const el = document.getElementById('status');
  if (!el) return;

  el.textContent = text;
  el.className = className;
}

/**
 * Render job progress bar with percentage and label
 * @param {number} progress - Progress percentage (0-100)
 * @param {string} label - Progress label text
 * @param {string} percentage - Displayed percentage text
 */
export function renderProgress(progress = 0, label = '', percentage = '') {
  const progressBar = document.getElementById('progress-bar-fill');
  const progressLabel = document.getElementById('progress-label');
  const progressPercentage = document.getElementById('progress-percentage');

  if (progressBar) {
    progressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  }

  if (progressLabel) {
    progressLabel.textContent = label || 'Processing...';
  }

  if (progressPercentage) {
    progressPercentage.textContent = percentage || `${Math.round(progress)}%`;
  }
}

/**
 * Format error message for display
 * @param {Error|string} error - Error object or message
 * @returns {string} Formatted error message
 */
export function formatError(error) {
  if (!error) return 'Unknown error';

  if (error instanceof Error) {
    return error.message || error.toString();
  }

  if (typeof error === 'string') {
    return error;
  }

  try {
    return JSON.stringify(error, null, 2);
  } catch {
    return String(error);
  }
}

/**
 * Normalize server URL from various input formats
 * @param {string} url - Server URL to normalize
 * @returns {string} Normalized URL
 */
export function normalizeServerUrl(url) {
  if (!url) return '';

  // Remove trailing slashes
  let normalized = url.replace(/\/+$/, '');

  // Ensure it starts with http:// or https://
  if (!/^https?:\/\//i.test(normalized)) {
    normalized = `http://${normalized}`;
  }

  return normalized;
}

/**
 * Check if URL is a valid YouTube video URL
 * @param {string} url - URL to check
 * @returns {boolean} True if URL is a YouTube video URL
 */
export function isYouTubeVideoUrl(url) {
  if (!url) return false;

  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }

  const host = parsed.hostname.toLowerCase();
  if (host === 'youtu.be') {
    return /^\/[\w-]{11,12}$/.test(parsed.pathname);
  }

  if (host === 'www.youtube.com' || host === 'youtube.com' || host === 'm.youtube.com') {
    if (parsed.pathname === '/watch') {
      return /^[A-Za-z0-9_-]{11,12}$/.test(parsed.searchParams.get('v') || '');
    }
    // youtu.be short links can also appear as /shorts/ID
    if (parsed.pathname.startsWith('/shorts/')) {
      return /^\/shorts\/[\w-]{11,12}$/.test(parsed.pathname);
    }
  }

  return false;
}

/**
 * Safely truncate long text with ellipsis
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Maximum length before truncation (default: 50)
 * @returns {string} Truncated text
 */
export function truncateText(text, maxLength = 50) {
  if (!text || text.length <= maxLength) {
    return text;
  }

  return text.substring(0, maxLength - 3) + '...';
}

/**
 * Format bytes to human-readable size
 * @param {number} bytes - Bytes to format
 * @param {number} decimals - Number of decimal places (default: 2)
 * @returns {string} Formatted size (e.g., "2.5 MB")
 */
export function formatFileSize(bytes, decimals = 2) {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

/**
 * Debounce function to limit event frequency
 * @param {Function} func - Function to debounce
 * @param {number} wait - Wait time in milliseconds (default: 250)
 * @returns {Function} Debounced function
 */
export function debounce(func, wait = 250) {
  let timeout;

  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };

    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Get gradient color based on progress percentage
 * @param {number} progress - Progress percentage (0-100)
 * @returns {string} CSS color value
 */
export function getProgressColor(progress) {
  if (progress < 30) {
    return '#4caf50'; // green
  } else if (progress < 70) {
    return '#ff9800'; // orange
  } else {
    return '#f44336'; // red
  }
}

/**
 * Generate random ID for temporary use
 * @param {number} length - ID length (default: 8)
 * @returns {string} Random ID
 */
export function generateId(length = 8) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';

  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }

  return result;
}
