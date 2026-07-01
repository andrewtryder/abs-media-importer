// Tiny browser API shim: Chrome exposes chrome.*, Firefox exposes browser.*.
// Both support Promise-style APIs in Manifest V3. We expose a single `api` object.
const api = typeof browser !== 'undefined' ? browser : chrome;

export default api;

export const tabs = api.tabs;
export const storage = api.storage;
export const contextMenus = api.contextMenus;
export const runtime = api.runtime;
export const action = api.action || api.browserAction;
export const notifications = api.notifications;