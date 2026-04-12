document.addEventListener('DOMContentLoaded', async () => {
  await loadSettings();
  setupEventListeners();
});

async function loadSettings() {
  const result = await chrome.storage.sync.get(['serverUrl', 'apiToken']);
  
  if (result.serverUrl) {
    document.getElementById('serverUrl').value = result.serverUrl;
  }
  
  if (result.apiToken) {
    document.getElementById('apiToken').value = result.apiToken;
  }
}

function setupEventListeners() {
  document.getElementById('saveBtn').addEventListener('click', saveSettings);
  document.getElementById('testBtn').addEventListener('click', testConnection);
}

async function saveSettings() {
  const saveBtn = document.getElementById('saveBtn');
  const saveSpinner = document.getElementById('saveSpinner');
  const saveBtnText = document.getElementById('saveBtnText');
  const connectionStatus = document.getElementById('connectionStatus');
  
  const serverUrl = document.getElementById('serverUrl').value.trim();
  const apiToken = document.getElementById('apiToken').value.trim().toUpperCase();
  
  if (!serverUrl) {
    showStatus('Please enter a server URL', 'error');
    return;
  }
  
  if (!apiToken || apiToken.length !== 8) {
    showStatus('Access token must be 8 characters', 'error');
    return;
  }
  
  saveBtn.disabled = true;
  saveSpinner.classList.remove('hidden');
  saveBtnText.textContent = 'Saving...';
  connectionStatus.classList.remove('show');
  
  await chrome.storage.sync.set({
    serverUrl: serverUrl.replace(/\/$/, ''),
    apiToken: apiToken
  });
  
  saveBtn.disabled = false;
  saveSpinner.classList.add('hidden');
  saveBtnText.textContent = 'Save Settings';
  
  showStatus('Settings saved successfully!', 'success');
}

async function testConnection() {
  const testBtn = document.getElementById('testBtn');
  const testSpinner = document.getElementById('testSpinner');
  const testBtnText = document.getElementById('testBtnText');
  const connectionStatus = document.getElementById('connectionStatus');
  
  const serverUrl = document.getElementById('serverUrl').value.trim();
  const apiToken = document.getElementById('apiToken').value.trim().toUpperCase();
  
  if (!serverUrl) {
    showStatus('Please enter a server URL', 'error');
    return;
  }
  
  testBtn.disabled = true;
  testSpinner.classList.remove('hidden');
  testBtnText.textContent = 'Testing...';
  connectionStatus.classList.remove('show');
  
  const cleanUrl = serverUrl.replace(/\/$/, '');
  
  try {
    const response = await fetch(`${cleanUrl}/ping`, {
      method: 'GET',
      headers: { 'X-API-Key': apiToken }
    });
    
    if (response.ok) {
      const data = await response.json();
      showStatus(`Connection successful! Server: ${data.message || 'Online'}`, 'success');
    } else if (response.status === 401) {
      showStatus('Invalid access token', 'error');
    } else {
      showStatus(`Server error: ${response.status}`, 'error');
    }
  } catch (error) {
    showStatus(`Connection failed: ${error.message}`, 'error');
  }
  
  testBtn.disabled = false;
  testSpinner.classList.add('hidden');
  testBtnText.textContent = 'Test Connection';
}

function showStatus(message, type) {
  const connectionStatus = document.getElementById('connectionStatus');
  connectionStatus.textContent = message;
  connectionStatus.className = `show ${type}`;
  
  setTimeout(() => {
    connectionStatus.classList.remove('show');
  }, 5000);
}
