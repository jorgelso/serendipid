/**
 * SuperBrain Extension - Content Script
 * Multi-collection Instagram scraper → smart local DB → SuperBrain import
 *
 * FLOW (across page navigations):
 * 1. ROOT /saved/         → discover collection folders, save to state, redirect to all-posts
 * 2. /saved/all-posts/    → scroll & extract all post URLs, save, redirect to 1st collection
 * 3. /saved/<collection>/ → scroll & extract, tag posts, redirect to next collection
 * 4. After last collection → build final DB (deduplicate), show Import button
 * 5. Import               → analyze each post, create/assign collections on server
 */

(function () {
  'use strict';

  // ── Guard against duplicate injection ────────────────────────────────
  if (window.__superbrainContentLoaded) {
    console.log('[SuperBrain] Already loaded, skipping.');
    return;
  }
  window.__superbrainContentLoaded = true;

  // ── App-level icon set (must match the mobile app exactly) ──────────
  const VALID_ICONS = [
    'folder', 'airplane', 'restaurant', 'shirt', 'fitness',
    'book', 'film', 'camera', 'star', 'heart', 'flame', 'pin', 'time'
  ];
  const ICON_KEYWORDS = {
    airplane:   ['travel', 'trip', 'vacation', 'flight', 'holiday', 'tourism', 'explore'],
    restaurant: ['food', 'recipe', 'meal', 'cooking', 'restaurant', 'eat', 'dish', 'cook', 'bake'],
    shirt:      ['fashion', 'style', 'outfit', 'clothes', 'clothing', 'dress', 'wear', 'ootd'],
    fitness:    ['workout', 'gym', 'exercise', 'fitness', 'training', 'health', 'yoga', 'run'],
    book:       ['book', 'read', 'reading', 'study', 'learning', 'education', 'learn'],
    film:       ['movie', 'film', 'cinema', 'series', 'tv', 'show', 'watch', 'anime'],
    camera:     ['photo', 'photography', 'pic', 'picture', 'art', 'design', 'draw', 'paint'],
    star:       ['favorite', 'best', 'top', 'rated', 'wishlist', 'inspo', 'inspiration'],
    heart:      ['love', 'like', 'heart', 'crush', 'couple', 'relationship'],
    flame:      ['hot', 'trending', 'fire', 'popular', 'viral', 'meme', 'funny'],
    pin:        ['place', 'location', 'spot', 'address', 'city', 'map', 'cafe'],
    time:       ['later', 'queue', 'reminder', 'save', 'todo', 'watch later']
  };

  function pickIcon(name) {
    const lower = name.toLowerCase();
    for (const [icon, kws] of Object.entries(ICON_KEYWORDS)) {
      if (kws.some(k => lower.includes(k))) return icon;
    }
    return 'folder';
  }

  // ── State ────────────────────────────────────────────────────────────
  const STORAGE_KEY = 'sb_scrape_state';
  let settings = null;
  let isRunning = false;
  let shouldStop = false;

  // ── Helpers ──────────────────────────────────────────────────────────
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  function extractShortcode(url) {
    const m = url.match(/\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
    return m ? m[2] : null;
  }

  function normalizeUrl(url) {
    const m = url.match(/\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
    if (!m) return null;
    return `https://www.instagram.com/${m[1]}/${m[2]}/`;
  }

  function escapeHtml(t) { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; }

  // ── Storage helpers ──────────────────────────────────────────────────
  function saveState(state) {
    return new Promise(r => chrome.storage.local.set({ [STORAGE_KEY]: state }, r));
  }
  function loadState() {
    return new Promise(r => chrome.storage.local.get([STORAGE_KEY], res => r(res[STORAGE_KEY] || null)));
  }
  function clearState() {
    return new Promise(r => chrome.storage.local.remove([STORAGE_KEY], r));
  }

  // ── Local DB (final, after scrape) ──────────────────────────────────
  const DB_KEY = 'superbrain_db';
  function loadDB() {
    return new Promise(r => chrome.storage.local.get([DB_KEY], res => {
      r(res[DB_KEY] || { collections: [], posts: {} });
    }));
  }
  function saveDB(db) {
    return new Promise(r => chrome.storage.local.set({ [DB_KEY]: db }, r));
  }

  // ── Overlay UI ──────────────────────────────────────────────────────
  function createOverlay() {
    const existing = document.getElementById('sb-import-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'sb-import-overlay';
    overlay.className = 'sb-import-overlay';
    overlay.innerHTML = `
      <div class="sb-import-panel">
        <div class="sb-import-logo">🧠</div>
        <h2 class="sb-import-title">SuperBrain Import</h2>
        <p class="sb-import-subtitle" id="sb-import-subtitle">Initializing...</p>
        <div class="sb-import-progress">
          <div class="sb-import-progress-bar">
            <div class="sb-import-progress-fill" id="sb-progress-fill"></div>
          </div>
          <div class="sb-import-stats">
            <div class="sb-import-stat">
              <div class="sb-import-stat-value" id="sb-stat-scraped">0</div>
              <div class="sb-import-stat-label">Scraped</div>
            </div>
            <div class="sb-import-stat">
              <div class="sb-import-stat-value" id="sb-stat-saved">0</div>
              <div class="sb-import-stat-label">Saved</div>
            </div>
            <div class="sb-import-stat">
              <div class="sb-import-stat-value" id="sb-stat-failed">0</div>
              <div class="sb-import-stat-label">Failed</div>
            </div>
          </div>
        </div>
        <div class="sb-import-detail" id="sb-import-detail"></div>
        <div class="sb-import-actions">
          <button class="sb-import-btn sb-import-btn-primary" id="sb-import-btn" style="display:none;">
            Import to SuperBrain
          </button>
          <button class="sb-import-btn sb-import-btn-secondary" id="sb-stop-btn" style="display:none;">
            Stop
          </button>
        </div>
        <div class="sb-import-log">
          <div class="sb-import-log-title">Activity Log</div>
          <div id="sb-log-entries"></div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    document.getElementById('sb-stop-btn').addEventListener('click', () => {
      shouldStop = true;
      addLog('Stopping...', 'info');
    });
    document.getElementById('sb-import-btn').addEventListener('click', () => {
      const btn = document.getElementById('sb-import-btn');
      btn.disabled = true;
      btn.textContent = 'Importing...';
      startImport();
    });
  }

  function updateProgress(pct, detail) {
    const fill = document.getElementById('sb-progress-fill');
    if (fill) fill.style.width = `${pct}%`;
    const sub = document.getElementById('sb-import-subtitle');
    if (sub) sub.textContent = detail || '';
    const det = document.getElementById('sb-import-detail');
    if (det) det.textContent = detail || '';
  }

  function updateStats(scraped, saved, failed) {
    const s = document.getElementById('sb-stat-scraped');
    const v = document.getElementById('sb-stat-saved');
    const f = document.getElementById('sb-stat-failed');
    if (s) s.textContent = scraped;
    if (v) v.textContent = saved;
    if (f) f.textContent = failed;

    try {
      chrome.runtime.sendMessage({ type: 'DB_STATS_UPDATE', stats: { scraped, saved, failed } });
    } catch (e) { /* context invalidated */ }
  }

  function addLog(message, level = 'info') {
    const log = document.getElementById('sb-log-entries');
    if (!log) { console.log(`[SB] ${message}`); return; }
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const entry = document.createElement('div');
    entry.className = `sb-import-log-entry ${level}`;
    entry.innerHTML = `<span class="sb-import-log-time">${time}</span><span>${escapeHtml(message)}</span>`;
    log.insertBefore(entry, log.firstChild);
    while (log.children.length > 150) log.removeChild(log.lastChild);

    try {
      chrome.runtime.sendMessage({ type: 'IMPORT_LOG', message: `[Scrap] ${message}`, level });
    } catch (e) { /* context invalidated */ }
  }

  // ── Scroll until no more content loads ──────────────────────────────
  async function scrollToBottom() {
    let noChangeCount = 0;
    const maxNoChange = 7;
    const maxAttempts = 200;
    let attempts = 0;

    while (noChangeCount < maxNoChange && attempts < maxAttempts && !shouldStop) {
      const oldH = document.documentElement.scrollHeight;
      window.scrollTo(0, document.documentElement.scrollHeight);
      await sleep(1800);
      attempts++;
      const newH = document.documentElement.scrollHeight;

      if (newH === oldH) {
        noChangeCount++;
        addLog(`No new content (${noChangeCount}/${maxNoChange})`, 'info');
        await sleep(1200);
      } else {
        noChangeCount = 0;
        const count = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"], a[href*="/tv/"]').length;
        addLog(`Loading more... (~${count} links)`, 'info');
      }
    }
    window.scrollTo(0, 0);
  }

  // ── Extract all post links from current page ────────────────────────
  function extractPostLinks() {
    const links = document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"], a[href*="/reels/"], a[href*="/tv/"]');
    const posts = [];
    const seen = new Set();
    links.forEach(link => {
      const href = link.href;
      if (!href || href.includes('/explore/') || href.includes('/accounts/') || href.includes('/tags/')) return;
      const url = normalizeUrl(href);
      if (!url) return;
      const sc = extractShortcode(url);
      if (sc && !seen.has(sc)) {
        seen.add(sc);
        posts.push({ shortcode: sc, url });
      }
    });
    return posts;
  }

  // ── Slugs to skip (system collections, not user content) ────────────
  const SKIP_COLLECTION_SLUGS = new Set(['all-posts', 'audio']);

  // ── Extract collection folder links from root /saved/ page ──────────
  function extractCollectionFolders() {
    const links = document.querySelectorAll('a[href*="/saved/"]');
    const cols = [];
    const seen = new Set();
    links.forEach(link => {
      const href = link.href;
      if (!href) return;
      const m = href.match(/\/saved\/([^\/\?#]+)/);
      if (!m) return;
      const slug = m[1];
      // Skip system collections and duplicates
      if (SKIP_COLLECTION_SLUGS.has(slug.toLowerCase()) || seen.has(slug)) return;
      seen.add(slug);
      // Try to get a human-readable name from the link text
      const rawText = link.textContent?.trim() || '';
      const name = (rawText.length > 0 && rawText.length < 100) ? rawText : slug.replace(/-/g, ' ');
      // Also skip if the name looks like "Audio" (case-insensitive)
      if (name.toLowerCase() === 'audio') return;
      cols.push({ name, slug, url: href });
    });
    return cols;
  }

  // ── Scroll root /saved/ page to load all collection folders ──────────
  async function scrollToLoadCollections() {
    addLog('Scrolling to load all collections...', 'info');
    let noChangeCount = 0;
    const maxNoChange = 5;
    const maxAttempts = 50;
    let attempts = 0;

    while (noChangeCount < maxNoChange && attempts < maxAttempts && !shouldStop) {
      const oldH = document.documentElement.scrollHeight;
      window.scrollTo(0, document.documentElement.scrollHeight);
      await sleep(1500);
      attempts++;
      const newH = document.documentElement.scrollHeight;

      if (newH === oldH) {
        noChangeCount++;
      } else {
        noChangeCount = 0;
        const count = extractCollectionFolders().length;
        addLog(`Loading collections... (${count} found so far)`, 'info');
      }
    }
    window.scrollTo(0, 0);
  }

  // ── Get username from current URL ───────────────────────────────────
  function getUsername() {
    const m = window.location.href.match(/instagram\.com\/([^\/]+)\/saved/);
    return m ? m[1] : null;
  }

  // ════════════════════════════════════════════════════════════════════
  // SCRAPE STATE MACHINE
  // State persisted in chrome.storage across page navigations:
  //   phase: 'init' | 'all-posts' | 'collection' | 'done'
  //   settings: { serverUrl, apiToken }
  //   username: string
  //   collections: [{ name, slug, url }]
  //   collectionIndex: number (which collection we're scraping next)
  //   allPostShortcodes: [string]
  //   collectionPosts: { collectionName: [shortcode] }
  // ════════════════════════════════════════════════════════════════════

  async function startScrape(config) {
    if (isRunning) return;
    isRunning = true;
    shouldStop = false;
    settings = config.settings;

    createOverlay();
    addLog('Starting Instagram Saved scan...', 'info');
    document.getElementById('sb-stop-btn').style.display = 'inline-flex';

    const username = getUsername();
    if (!username) {
      addLog('Could not detect username from URL', 'error');
      isRunning = false;
      return;
    }

    const currentUrl = window.location.href;

    // ── Determine where we are and what phase to run ────────────────
    if (/\/saved\/?(\?|#|$)/.test(currentUrl) || /\/saved\/?$/.test(currentUrl)) {
      // ROOT PAGE — Phase 1: scroll to load all collections, then redirect to all-posts
      addLog('On root Saved page — loading all collections...', 'info');
      updateProgress(2, 'Loading collections...');

      // Scroll to load lazy-loaded collection folders
      await scrollToLoadCollections();
      if (shouldStop) { addLog('Stopped by user', 'info'); isRunning = false; return; }

      const folders = extractCollectionFolders();
      addLog(`Found ${folders.length} user collections: ${folders.map(f => f.name).join(', ') || '(none)'}`, 'success');

      const state = {
        phase: 'all-posts',
        settings: config.settings,
        username,
        collections: folders,
        collectionIndex: 0,
        allPostShortcodes: [],
        collectionPosts: {}
      };
      await saveState(state);

      const allPostsUrl = `https://www.instagram.com/${username}/saved/all-posts/`;
      addLog(`Navigating to All Posts...`, 'info');
      window.location.href = allPostsUrl;
      return; // page will reload

    } else if (currentUrl.includes('/saved/all-posts')) {
      // ALL-POSTS PAGE — scrape all, then move to first collection
      await handleAllPostsPage();

    } else if (currentUrl.includes('/saved/')) {
      // COLLECTION PAGE — scrape this collection, then next or finalize
      await handleCollectionPage();

    } else {
      addLog('Not on a recognized saved page', 'error');
      isRunning = false;
    }
  }

  async function handleAllPostsPage() {
    const state = await loadState();
    if (!state || state.phase !== 'all-posts') {
      addLog('No pending scrape state found', 'error');
      isRunning = false;
      return;
    }
    settings = state.settings;

    createOverlay();
    addLog('Scraping All Posts — scrolling to load everything...', 'info');
    document.getElementById('sb-stop-btn').style.display = 'inline-flex';
    updateProgress(5, 'Scrolling All Posts...');

    await scrollToBottom();
    if (shouldStop) { addLog('Stopped by user', 'info'); isRunning = false; return; }

    const posts = extractPostLinks();
    addLog(`All Posts: found ${posts.length} posts`, 'success');
    state.allPostShortcodes = posts.map(p => p.shortcode);

    // Also store URLs for later
    if (!state.postUrls) state.postUrls = {};
    for (const p of posts) {
      state.postUrls[p.shortcode] = p.url;
    }

    updateStats(posts.length, 0, 0);

    // Move to first collection (or finalize if no collections)
    if (state.collections.length > 0) {
      state.phase = 'collection';
      state.collectionIndex = 0;
      await saveState(state);

      const col = state.collections[0];
      addLog(`Navigating to collection: ${col.name}...`, 'info');
      window.location.href = col.url;
    } else {
      // No user collections — finalize directly
      state.phase = 'done';
      await saveState(state);
      await buildFinalDB(state);
    }
  }

  async function handleCollectionPage() {
    const state = await loadState();
    if (!state || state.phase !== 'collection') {
      addLog('No pending collection scrape state', 'error');
      isRunning = false;
      return;
    }
    settings = state.settings;

    const col = state.collections[state.collectionIndex];
    if (!col) {
      // All collections done — finalize
      state.phase = 'done';
      await saveState(state);
      await buildFinalDB(state);
      return;
    }

    createOverlay();
    const progress = Math.round(20 + (state.collectionIndex / state.collections.length) * 60);
    addLog(`Scraping collection: ${col.name} (${state.collectionIndex + 1}/${state.collections.length})...`, 'info');
    document.getElementById('sb-stop-btn').style.display = 'inline-flex';
    updateProgress(progress, `Scrolling: ${col.name}...`);

    await scrollToBottom();
    if (shouldStop) { addLog('Stopped by user', 'info'); isRunning = false; return; }

    const posts = extractPostLinks();
    addLog(`${col.name}: found ${posts.length} posts`, 'success');

    // Store this collection's shortcodes
    state.collectionPosts[col.name] = posts.map(p => p.shortcode);

    // Store URLs
    if (!state.postUrls) state.postUrls = {};
    for (const p of posts) {
      state.postUrls[p.shortcode] = p.url;
    }

    // Move to next collection or finalize
    state.collectionIndex++;
    if (state.collectionIndex < state.collections.length) {
      await saveState(state);
      const nextCol = state.collections[state.collectionIndex];
      addLog(`Navigating to collection: ${nextCol.name}...`, 'info');
      window.location.href = nextCol.url;
    } else {
      state.phase = 'done';
      await saveState(state);
      await buildFinalDB(state);
    }
  }

  // ── Build final DB from scraped data ────────────────────────────────
  async function buildFinalDB(state) {
    createOverlay();
    addLog('Building local database...', 'info');
    updateProgress(85, 'Building database...');

    // Figure out which posts belong to which collection
    // A post that's in ANY user collection → belongs to that collection
    // A post that's ONLY in all-posts (not in any collection) → collection = null
    const postInCollection = {}; // shortcode → collectionName

    for (const [colName, shortcodes] of Object.entries(state.collectionPosts)) {
      for (const sc of shortcodes) {
        // If a post appears in multiple user collections, first one wins
        if (!postInCollection[sc]) {
          postInCollection[sc] = colName;
        }
      }
    }

    // Build posts map
    const posts = {};
    const allShortcodes = new Set(state.allPostShortcodes);

    // Add all posts from collections (whether or not they were in all-posts)
    for (const [colName, shortcodes] of Object.entries(state.collectionPosts)) {
      for (const sc of shortcodes) {
        posts[sc] = {
          shortcode: sc,
          url: state.postUrls[sc] || `https://www.instagram.com/p/${sc}/`,
          collection: colName,
          status: 'pending',
          attempts: 0,
          error: null
        };
      }
    }

    // Add posts from all-posts that are NOT in any user collection
    for (const sc of state.allPostShortcodes) {
      if (!postInCollection[sc]) {
        posts[sc] = {
          shortcode: sc,
          url: state.postUrls[sc] || `https://www.instagram.com/p/${sc}/`,
          collection: null, // uncategorized
          status: 'pending',
          attempts: 0,
          error: null
        };
      }
    }

    // Build collections list
    const collections = state.collections.map(col => ({
      name: col.name,
      slug: col.slug,
      icon: pickIcon(col.name),
      postShortcodes: state.collectionPosts[col.name] || []
    }));

    const db = { collections, posts };
    await saveDB(db);
    await clearState(); // Done with scrape state

    // Count stats
    const totalPosts = Object.keys(posts).length;
    const inCollections = Object.values(posts).filter(p => p.collection !== null).length;
    const uncategorized = totalPosts - inCollections;

    addLog(`Database built! ${totalPosts} total posts`, 'success');
    addLog(`  → ${inCollections} in ${collections.length} collections`, 'info');
    addLog(`  → ${uncategorized} uncategorized (all-posts only)`, 'info');
    addLog('Click "Import to SuperBrain" to start importing', 'info');

    updateProgress(100, 'Scraping complete!');
    updateStats(totalPosts, 0, 0);

    document.getElementById('sb-stop-btn').style.display = 'none';
    const btn = document.getElementById('sb-import-btn');
    if (btn) {
      btn.style.display = 'inline-flex';
      btn.disabled = false;
      btn.textContent = `Import ${totalPosts} Posts to SuperBrain`;
    }

    isRunning = false;
  }

  // ════════════════════════════════════════════════════════════════════
  // IMPORT TO SUPERBRAIN
  // ════════════════════════════════════════════════════════════════════

  async function startImport() {
    const db = await loadDB();
    if (!db || !db.posts || Object.keys(db.posts).length === 0) {
      addLog('No posts in local database. Run a scan first.', 'error');
      return;
    }

    // Load settings from storage if not in memory
    if (!settings) {
      const stored = await new Promise(r => chrome.storage.sync.get(['serverUrl', 'apiToken'], r));
      settings = { serverUrl: stored.serverUrl?.replace(/\/$/, ''), apiToken: stored.apiToken };
    }
    if (!settings.serverUrl || !settings.apiToken) {
      addLog('Server not configured. Go to Settings.', 'error');
      return;
    }

    isRunning = true;
    shouldStop = false;

    const stopBtn = document.getElementById('sb-stop-btn');
    const importBtn = document.getElementById('sb-import-btn');
    if (stopBtn) stopBtn.style.display = 'inline-flex';
    if (importBtn) importBtn.style.display = 'none';

    addLog('Starting import to SuperBrain...', 'info');

    // Get posts that need processing (pending or failed)
    const postsToProcess = Object.values(db.posts).filter(p =>
      p.status === 'pending' || p.status === 'failed'
    );

    if (postsToProcess.length === 0) {
      addLog('All posts already imported!', 'success');
      isRunning = false;
      if (stopBtn) stopBtn.style.display = 'none';
      if (importBtn) { importBtn.style.display = 'inline-flex'; importBtn.disabled = false; importBtn.textContent = 'All Done!'; }
      return;
    }

    addLog(`${postsToProcess.length} posts to process...`, 'info');

    // Load server collections once
    let serverCollections = [];
    try {
      const resp = await fetch(`${settings.serverUrl}/collections`, {
        headers: { 'X-API-Key': settings.apiToken }
      });
      if (resp.ok) {
        const data = await resp.json();
        serverCollections = data.data || [];
      }
      addLog(`Server has ${serverCollections.length} existing collections`, 'info');
    } catch (e) {
      addLog(`Warning: Could not fetch server collections: ${e.message}`, 'error');
    }

    // Cache of collection name → server collection (so we don't re-create)
    const collectionCache = {};
    for (const sc of serverCollections) {
      collectionCache[sc.name.toLowerCase().trim()] = sc;
    }

    let saved = 0;
    let failed = 0;

    for (let i = 0; i < postsToProcess.length; i++) {
      if (shouldStop) {
        addLog('Import stopped by user', 'info');
        break;
      }

      const post = postsToProcess[i];
      const pct = Math.round(((i + 1) / postsToProcess.length) * 100);
      updateProgress(pct, `Processing ${i + 1}/${postsToProcess.length}: ${post.shortcode}`);

      try {
        // ── Step 1: If post has a collection, ensure it exists on server ──
        let serverCollection = null;
        if (post.collection) {
          const key = post.collection.toLowerCase().trim();

          if (collectionCache[key]) {
            serverCollection = collectionCache[key];
          } else {
            // Create collection on server
            const icon = pickIcon(post.collection);
            const colId = `ig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            addLog(`Creating collection: ${post.collection} (icon: ${icon})`, 'info');

            const createResp = await fetch(`${settings.serverUrl}/collections`, {
              method: 'POST',
              headers: { 'X-API-Key': settings.apiToken, 'Content-Type': 'application/json' },
              body: JSON.stringify({
                id: colId,
                name: post.collection,
                icon: icon,
                post_ids: []
              })
            });

            if (createResp.ok) {
              const createData = await createResp.json();
              serverCollection = createData.data;
              collectionCache[key] = serverCollection;
              addLog(`Created collection: ${post.collection}`, 'success');
            } else {
              addLog(`Failed to create collection: ${post.collection}`, 'error');
            }
          }
        }

        // ── Step 2: Analyze the post ──────────────────────────────────
        const analyzeResp = await fetch(`${settings.serverUrl}/analyze`, {
          method: 'POST',
          headers: { 'X-API-Key': settings.apiToken, 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: post.url })
        });

        const analyzeOk = analyzeResp.ok || analyzeResp.status === 202 || analyzeResp.status === 503;

        if (analyzeResp.status === 409) {
          // Already analyzed — that's fine
          addLog(`Already analyzed: ${post.shortcode}`, 'info');
        } else if (!analyzeOk) {
          const errText = await analyzeResp.text().catch(() => '');
          throw new Error(`Analyze failed (${analyzeResp.status}): ${errText.substring(0, 100)}`);
        }

        // ── Step 3: If in collection, add shortcode to collection post_ids ──
        if (serverCollection) {
          try {
            // Get current post_ids from server
            const currentIds = serverCollection.post_ids || [];
            if (!currentIds.includes(post.shortcode)) {
              const newIds = [...currentIds, post.shortcode];
              const updateResp = await fetch(`${settings.serverUrl}/collections/${serverCollection.id}/posts`, {
                method: 'PUT',
                headers: { 'X-API-Key': settings.apiToken, 'Content-Type': 'application/json' },
                body: JSON.stringify({ post_ids: newIds })
              });
              if (updateResp.ok) {
                serverCollection.post_ids = newIds; // update cache
              }
            }
          } catch (e) {
            addLog(`Warning: Could not add to collection: ${e.message}`, 'error');
          }
        }

        // ── Mark as saved ──
        db.posts[post.shortcode].status = 'saved';
        db.posts[post.shortcode].error = null;
        saved++;

        const colTag = post.collection ? ` → ${post.collection}` : '';
        addLog(`Saved: ${post.shortcode}${colTag}`, 'success');

      } catch (error) {
        db.posts[post.shortcode].status = 'failed';
        db.posts[post.shortcode].attempts = (db.posts[post.shortcode].attempts || 0) + 1;
        db.posts[post.shortcode].error = error.message;
        failed++;
        addLog(`Failed: ${post.shortcode} — ${error.message}`, 'error');
      }

      // Save DB periodically
      if (i % 5 === 0 || i === postsToProcess.length - 1) {
        await saveDB(db);
      }
      updateStats(Object.keys(db.posts).length, saved, failed);

      // Small delay between requests
      await sleep(500);
    }

    await saveDB(db);
    addLog(`Import complete! Saved: ${saved}, Failed: ${failed}`, 'success');
    updateStats(Object.keys(db.posts).length, saved, failed);

    if (stopBtn) stopBtn.style.display = 'none';
    if (importBtn) {
      importBtn.style.display = 'inline-flex';
      importBtn.disabled = false;
      importBtn.textContent = failed > 0 ? `Retry ${failed} Failed` : 'All Done!';
    }

    try {
      chrome.runtime.sendMessage({ type: 'IMPORT_COMPLETE', stats: { saved, failed } });
    } catch (e) { /* context invalidated */ }

    isRunning = false;
  }

  // ════════════════════════════════════════════════════════════════════
  // AUTO-RESUME ON PAGE LOAD
  // Check if we have a pending multi-page scrape to continue
  // ════════════════════════════════════════════════════════════════════

  async function checkAutoResume() {
    const state = await loadState();
    if (!state) return;

    console.log('[SuperBrain] Found pending state, phase:', state.phase);
    settings = state.settings;

    if (state.phase === 'all-posts' && window.location.href.includes('/saved/all-posts')) {
      await sleep(2000);
      await handleAllPostsPage();
    } else if (state.phase === 'collection' && window.location.href.includes('/saved/')) {
      await sleep(2000);
      await handleCollectionPage();
    } else if (state.phase === 'done') {
      await buildFinalDB(state);
    }
  }

  // Also check for explicit pending scrape trigger (from popup)
  chrome.storage.local.get(['sb_pending_scrape'], (result) => {
    if (result.sb_pending_scrape) {
      const config = result.sb_pending_scrape;
      chrome.storage.local.remove(['sb_pending_scrape'], () => {
        setTimeout(() => startScrape(config), 2000);
      });
      return;
    }
    // Otherwise check auto-resume
    checkAutoResume();
  });

  // ════════════════════════════════════════════════════════════════════
  // MESSAGE LISTENER
  // ════════════════════════════════════════════════════════════════════

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === 'START_SCRAPE') {
      startScrape(message);
      sendResponse({ success: true });

    } else if (message.action === 'START_IMPORT') {
      // Import only (don't re-scrape)
      createOverlay();
      startImport();
      sendResponse({ success: true });

    } else if (message.action === 'STOP_SCRAPE') {
      shouldStop = true;
      sendResponse({ success: true });

    } else if (message.action === 'GET_DB_STATS') {
      loadDB().then(db => {
        const posts = db.posts || {};
        const all = Object.values(posts);
        sendResponse({
          totalPosts: all.length,
          processed: all.filter(p => p.status === 'saved').length,
          pending: all.filter(p => p.status === 'pending').length,
          failed: all.filter(p => p.status === 'failed').length,
          collections: (db.collections || []).length,
          failedItems: all.filter(p => p.status === 'failed').map(p => ({
            shortcode: p.shortcode,
            error: p.error,
            attempts: p.attempts
          }))
        });
      });
      return true; // async response

    } else if (message.action === 'RETRY_FAILED') {
      loadDB().then(async db => {
        const posts = db.posts || {};
        let count = 0;
        for (const sc of Object.keys(posts)) {
          if (posts[sc].status === 'failed') {
            posts[sc].status = 'pending';
            posts[sc].error = null;
            count++;
          }
        }
        await saveDB(db);
        sendResponse({ success: true, count });
      });
      return true; // async response

    } else if (message.action === 'CLEAR_DB') {
      saveDB({ collections: [], posts: {} }).then(() => {
        clearState().then(() => {
          sendResponse({ success: true });
        });
      });
      return true; // async response
    }

    return true;
  });

  console.log('[SuperBrain] Content script loaded and ready');
})();
