/**
 * SuperBrain Extension - Popup Script
 * UI for triggering scan, import, and retry
 */

let isRunning = false;
let currentDbStats = {
  totalPosts: 0, processed: 0, pending: 0, failed: 0, collections: 0, failedItems: []
};

document.addEventListener('DOMContentLoaded', async () => {
  await checkConnection();
  await loadDbStats();
  setupEventListeners();
});

function setupEventListeners() {
  document.getElementById('scrapeBtn').addEventListener('click', startScrape);
  document.getElementById('stopBtn').addEventListener('click', stopScrape);
  document.getElementById('settingsLink').addEventListener('click', openSettings);
  document.getElementById('retryFailedBtn').addEventListener('click', retryFailed);
  document.getElementById('clearFailedBtn').addEventListener('click', clearFailed);
  document.getElementById('clearDbLink').addEventListener('click', clearDatabase);
  chrome.runtime.onMessage.addListener(handleMessage);
}

async function checkConnection() {
  const result = await chrome.storage.sync.get(['serverUrl', 'apiToken']);
  const statusDot = document.getElementById('statusDot');
  const statusText = document.getElementById('statusText');
  const serverInfo = document.getElementById('serverInfo');
  const scrapeBtn = document.getElementById('scrapeBtn');

  if (!result.serverUrl || !result.apiToken) {
    statusDot.classList.remove('connected');
    statusText.textContent = 'Not configured';
    statusText.classList.add('error');
    serverInfo.textContent = 'Configure in settings';
    scrapeBtn.disabled = true;
    return false;
  }

  const serverUrl = result.serverUrl.replace(/\/$/, '');
  serverInfo.textContent = serverUrl;

  try {
    const response = await fetch(`${serverUrl}/ping`, {
      method: 'GET',
      headers: { 'X-API-Key': result.apiToken }
    });
    if (response.ok) {
      statusDot.classList.add('connected');
      statusText.textContent = 'Connected';
      statusText.classList.remove('error');
      statusText.classList.add('success');
      scrapeBtn.disabled = false;
      addLog('Connected to SuperBrain', 'success');
      return true;
    } else {
      throw new Error('Server error');
    }
  } catch (error) {
    statusDot.classList.remove('connected');
    statusText.textContent = 'Connection failed';
    statusText.classList.add('error');
    serverInfo.textContent = 'Check settings';
    scrapeBtn.disabled = true;
    addLog('Connection failed', 'error');
    return false;
  }
}

async function loadDbStats() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab.url || !tab.url.includes('instagram.com')) {
    updateDbStatsUI(currentDbStats);
    return;
  }
  try {
    const response = await chrome.tabs.sendMessage(tab.id, { action: 'GET_DB_STATS' });
    if (response) {
      currentDbStats = response;
      updateDbStatsUI(response);
    }
  } catch (error) {
    console.log('Could not load DB stats (content script may not be injected yet)');
  }
}

function updateDbStatsUI(stats) {
  document.getElementById('dbTotal').textContent = stats.totalPosts || 0;
  document.getElementById('dbSaved').textContent = stats.processed || 0;
  document.getElementById('dbPending').textContent = stats.pending || 0;
  document.getElementById('dbFailed').textContent = stats.failed || 0;
  document.getElementById('dbCollections').textContent = stats.collections || 0;
  document.getElementById('failedCount').textContent = stats.failed || 0;

  const retryBtn = document.getElementById('retryFailedBtn');
  const clearBtn = document.getElementById('clearFailedBtn');
  retryBtn.disabled = !(stats.failed > 0);
  clearBtn.disabled = !(stats.failed > 0);

  updateFailedList(stats.failedItems || []);
}

function updateFailedList(failedItems) {
  const list = document.getElementById('failedList');
  if (!failedItems || failedItems.length === 0) {
    list.innerHTML = '<div class="failed-empty">No failed posts</div>';
    return;
  }
  list.innerHTML = failedItems.slice(0, 5).map(item => `
    <div class="failed-item">
      <span class="failed-shortcode">${item.shortcode?.substring(0, 12) || '?'}...</span>
      <span class="failed-error">${escapeHtml((item.error || 'Unknown error').substring(0, 40))}</span>
    </div>
  `).join('');
  if (failedItems.length > 5) {
    list.innerHTML += `<div class="failed-more">+${failedItems.length - 5} more</div>`;
  }
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { action: 'GET_DB_STATS' });
    return true;
  } catch (e) {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ['content/content.js'] });
      await chrome.scripting.insertCSS({ target: { tabId }, files: ['content/content.css'] });
      await new Promise(r => setTimeout(r, 500));
      return true;
    } catch (err) {
      console.error('Failed to inject content script:', err);
      return false;
    }
  }
}

async function startScrape() {
  if (isRunning) return;

  const result = await chrome.storage.sync.get(['serverUrl', 'apiToken']);
  if (!result.serverUrl || !result.apiToken) {
    addLog('Configure settings first', 'error');
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab.url || !tab.url.includes('instagram.com')) {
    addLog('Navigate to Instagram first', 'error');
    return;
  }
  if (!tab.url.includes('/saved')) {
    addLog('Navigate to your Instagram Saved page first', 'error');
    addLog('Go to: Profile → ☰ → Saved', 'info');
    return;
  }

  isRunning = true;
  updateRunningUI(true);
  addLog('Starting scan...', 'info');

  try {
    const injected = await ensureContentScript(tab.id);
    if (!injected) throw new Error('Could not inject content script');

    chrome.tabs.sendMessage(tab.id, {
      action: 'START_SCRAPE',
      settings: {
        serverUrl: result.serverUrl.replace(/\/$/, ''),
        apiToken: result.apiToken
      }
    }, (response) => {
      if (chrome.runtime.lastError) {
        addLog('Failed: ' + chrome.runtime.lastError.message, 'error');
        isRunning = false;
        updateRunningUI(false);
      }
    });
  } catch (error) {
    addLog('Failed to start: ' + error.message, 'error');
    isRunning = false;
    updateRunningUI(false);
  }
}

async function stopScrape() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab.id) {
    try { chrome.tabs.sendMessage(tab.id, { action: 'STOP_SCRAPE' }); } catch (e) {}
  }
  isRunning = false;
  updateRunningUI(false);
  addLog('Stopped by user', 'info');
}

function updateRunningUI(running) {
  const scrapeBtn = document.getElementById('scrapeBtn');
  const scrapeSpinner = document.getElementById('scrapeSpinner');
  const scrapeBtnText = document.getElementById('scrapeBtnText');
  const stopBtn = document.getElementById('stopBtn');
  const progressSection = document.getElementById('progressSection');

  if (running) {
    scrapeBtn.disabled = true;
    scrapeSpinner.classList.remove('hidden');
    scrapeBtnText.textContent = 'Running...';
    stopBtn.classList.remove('hidden');
    progressSection.classList.remove('hidden');
  } else {
    scrapeBtn.disabled = false;
    scrapeSpinner.classList.add('hidden');
    scrapeBtnText.textContent = 'Scan Instagram Saved';
    stopBtn.classList.add('hidden');
    progressSection.classList.add('hidden');
    isRunning = false;
  }
}

function handleMessage(message) {
  switch (message.type) {
    case 'IMPORT_LOG':
      addLog(message.message, message.level);
      break;
    case 'IMPORT_PROGRESS':
      updateProgress(message.current, message.total, message.currentItem);
      break;
    case 'DB_STATS_UPDATE':
      if (message.stats) {
        currentDbStats = { ...currentDbStats, ...message.stats };
        updateDbStatsUI(currentDbStats);
      }
      break;
    case 'IMPORT_COMPLETE':
      addLog(`Complete! Saved: ${message.stats.saved}, Failed: ${message.stats.failed}`, 'success');
      isRunning = false;
      updateRunningUI(false);
      loadDbStats();
      break;
  }
}

function updateProgress(current, total, currentItem) {
  const progressFill = document.getElementById('progressFill');
  const progressCount = document.getElementById('progressCount');
  const progressDetail = document.getElementById('progressDetail');
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  progressFill.style.width = `${pct}%`;
  progressCount.textContent = `${current} / ${total}`;
  progressDetail.textContent = currentItem || 'Processing...';
}

async function retryFailed() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab.url || !tab.url.includes('instagram.com')) {
    addLog('Open Instagram page to retry', 'error');
    return;
  }

  try {
    const injected = await ensureContentScript(tab.id);
    if (!injected) { addLog('Could not inject into page', 'error'); return; }

    const response = await chrome.tabs.sendMessage(tab.id, { action: 'RETRY_FAILED' });
    if (response && response.success) {
      addLog(`Reset ${response.count} failed posts to pending`, 'info');
      await loadDbStats();

      // Now trigger import (not scrape — we already have the data)
      isRunning = true;
      updateRunningUI(true);
      chrome.tabs.sendMessage(tab.id, { action: 'START_IMPORT' });
    }
  } catch (error) {
    addLog('Failed to retry: ' + error.message, 'error');
  }
}

async function clearFailed() {
  const confirmed = confirm('Clear all local data (posts & collections)?');
  if (!confirmed) return;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab.url && tab.url.includes('instagram.com')) {
    try { await chrome.tabs.sendMessage(tab.id, { action: 'CLEAR_DB' }); } catch (e) {}
  }
  try { await chrome.storage.local.remove(['superbrain_db', 'sb_scrape_state']); } catch (e) {}

  currentDbStats = { totalPosts: 0, processed: 0, pending: 0, failed: 0, collections: 0, failedItems: [] };
  updateDbStatsUI(currentDbStats);
  addLog('Database cleared', 'info');
}

async function clearDatabase(e) {
  e.preventDefault();
  const confirmed = confirm('Clear ALL local data? This cannot be undone.');
  if (!confirmed) return;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab.url && tab.url.includes('instagram.com')) {
    try { await chrome.tabs.sendMessage(tab.id, { action: 'CLEAR_DB' }); } catch (e) {}
  }
  try { await chrome.storage.local.remove(['superbrain_db', 'sb_scrape_state', 'sb_pending_scrape']); } catch (e) {}

  currentDbStats = { totalPosts: 0, processed: 0, pending: 0, failed: 0, collections: 0, failedItems: [] };
  updateDbStatsUI(currentDbStats);
  addLog('All data cleared', 'info');
}

function addLog(message, level = 'info') {
  const logEntries = document.getElementById('logEntries');
  const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.innerHTML = `
    <span class="log-time">${time}</span>
    <span class="log-message ${level}">${escapeHtml(message)}</span>
  `;
  logEntries.insertBefore(entry, logEntries.firstChild);
  while (logEntries.children.length > 50) logEntries.removeChild(logEntries.lastChild);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function openSettings(e) {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
}
