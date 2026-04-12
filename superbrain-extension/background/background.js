/**
 * SuperBrain Extension - Background Service Worker
 * Relays messages between content scripts and popup
 */

// Relay messages from content script to popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // These message types come from the content script and need to reach the popup
  if (message.type === 'IMPORT_LOG' || 
      message.type === 'IMPORT_PROGRESS' ||
      message.type === 'DB_STATS_UPDATE' ||
      message.type === 'IMPORT_COMPLETE' ||
      message.type === 'IMPORT_ERROR') {
    // No-op: the popup listens via chrome.runtime.onMessage which
    // automatically receives messages from content scripts too.
    // We just need to not return false (which would close the channel).
    return;
  }
});

chrome.runtime.onInstalled.addListener(() => {
  console.log('SuperBrain Extension installed');
});
