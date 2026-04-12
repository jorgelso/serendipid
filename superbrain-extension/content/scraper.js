/**
 * SuperBrain Extension - Instagram Scraper
 * Scrapes saved posts and collections from Instagram
 */

function extractShortcode(url) {
  const match = url.match(/\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
  return match ? match[2] : null;
}

function normalizeUrl(url) {
  if (!url) return null;
  
  const match = url.match(/\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
  if (!match) return null;
  
  const type = match[1];
  const shortcode = match[2];
  
  return `https://www.instagram.com/${type}/${shortcode}/`;
}

class InstagramScraper {
  constructor(onProgress, onLog) {
    this.onProgress = onProgress;
    this.onLog = onLog;
    this.shouldStop = false;
  }

  stop() {
    this.shouldStop = true;
    this.log('Stopping scraper...', 'info');
  }

  log(message, level = 'info') {
    if (this.onLog) {
      this.onLog(message, level);
    }
    console.log(`[Scraper] ${message}`);
  }

  reportProgress(current, total, detail) {
    if (this.onProgress) {
      this.onProgress(current, total, detail);
    }
  }

  async sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async scrollToLoadAll(container) {
    this.log('Starting scroll to load all content...', 'info');
    
    let lastHeight = 0;
    let noChangeCount = 0;
    let scrollAttempts = 0;
    const maxScrollAttempts = 100;
    const maxNoChange = 5;
    
    while (noChangeCount < maxNoChange && scrollAttempts < maxScrollAttempts && !this.shouldStop) {
      const oldHeight = container.scrollHeight;
      container.scrollTop = oldHeight;
      
      await this.sleep(1500);
      
      scrollAttempts++;
      
      const newHeight = container.scrollHeight;
      
      if (newHeight === oldHeight) {
        noChangeCount++;
        this.log(`No new content loaded (${noChangeCount}/${maxNoChange})`, 'info');
        await this.sleep(1000);
      } else {
        noChangeCount = 0;
        this.log(`Loaded more content...`, 'info');
      }
    }
    
    this.log('Finished scrolling', 'info');
  }

  async scrapeCollections() {
    this.log('Scraping collections...', 'info');
    
    const collections = [];
    
    const sidebar = document.querySelector('aside') || document.querySelector('nav');
    if (!sidebar) {
      this.log('Could not find sidebar', 'error');
      return collections;
    }
    
    const collectionElements = sidebar.querySelectorAll('[href*="/saved/"]');
    
    for (const el of collectionElements) {
      if (this.shouldStop) break;
      
      const href = el.href;
      const nameEl = el.querySelector('span') || el.querySelector('div') || el;
      let name = nameEl.textContent?.trim() || '';
      
      if (name && !name.includes('All posts') && name.length > 0 && name.length < 100) {
        const collectionUrl = href.includes('/saved/') ? href : `https://www.instagram.com${href}`;
        
        if (!collections.some(c => c.name === name)) {
          collections.push({
            name: name,
            url: collectionUrl,
            posts: []
          });
          this.log(`Found collection: ${name}`, 'info');
        }
      }
    }
    
    this.log(`Found ${collections.length} collections`, 'success');
    return collections;
  }

  async scrapePostsFromCurrentPage(collectionName = null) {
    this.log(`Scraping posts from ${collectionName || 'main saved page'}...`, 'info');
    
    const mainSection = document.querySelector('main[role="main"]');
    if (!mainSection) {
      this.log('Could not find main content area', 'error');
      return [];
    }

    const scrollContainer = mainSection.querySelector('div[style*="overflow"]') || mainSection;
    
    await this.scrollToLoadAll(scrollContainer);
    
    if (this.shouldStop) return [];
    
    const postLinks = mainSection.querySelectorAll('a[href*="/p/"], a[href*="/reel/"], a[href*="/reels/"], a[href*="/tv/"]');
    
    const posts = [];
    const seenShortcodes = new Set();
    
    postLinks.forEach(link => {
      const href = link.href;
      if (href && !href.includes('/explore/') && !href.includes('/accounts/') && !href.includes('/tags/')) {
        const url = normalizeUrl(href);
        if (url) {
          const shortcode = extractShortcode(url);
          if (shortcode && !seenShortcodes.has(shortcode)) {
            seenShortcodes.add(shortcode);
            posts.push({
              url,
              shortcode,
              collectionName
            });
          }
        }
      }
    });
    
    this.log(`Found ${posts.length} posts`, 'success');
    return posts;
  }

  async scrapeAllSaved() {
    this.log('Starting full scrape of Instagram saved...', 'info');
    
    const results = {
      collections: [],
      posts: [],
      allPosts: []
    };

    if (this.shouldStop) return results;

    this.log('Step 1: Scraping posts from "All Saved"...', 'info');
    const allSavedPosts = await this.scrapePostsFromCurrentPage(null);
    results.allPosts = allSavedPosts;
    results.posts.push(...allSavedPosts);

    this.reportProgress(10, 100, 'Scraped All Saved posts');

    if (this.shouldStop) return results;

    this.log('Step 2: Finding user collections...', 'info');
    const collections = await this.scrapeCollections();
    results.collections = collections;

    this.reportProgress(20, 100, `Found ${collections.length} collections`);

    const totalItems = collections.length + 1;
    let processedItems = 1;

    for (const collection of collections) {
      if (this.shouldStop) break;

      this.log(`Step 3: Scraping collection "${collection.name}"...`, 'info');
      
      const collectionUrl = collection.url;
      if (collectionUrl && collectionUrl !== window.location.href) {
        this.log(`Navigating to ${collectionUrl}...`, 'info');
        
        window.location.href = collectionUrl;
        await this.sleep(3000);
        
        if (this.shouldStop) break;
      }
      
      const collectionPosts = await this.scrapePostsFromCurrentPage(collection.name);
      collection.posts = collectionPosts;
      results.posts.push(...collectionPosts);
      
      processedItems++;
      const progress = 20 + Math.round((processedItems / totalItems) * 70);
      this.reportProgress(progress, 100, `Scraped ${collection.name}: ${collectionPosts.length} posts`);
    }

    if (window.location.href.includes('/saved/')) {
      this.log('Returning to main saved page...', 'info');
    }

    this.reportProgress(100, 100, `Scraping complete!`);

    this.log(`Total: ${results.allPosts.length} in All Saved, ${results.collections.length} collections with ${results.posts.length - results.allPosts.length} unique posts`, 'success');

    return results;
  }

  async scrapeCurrentPageOnly() {
    this.log('Scraping current page only...', 'info');
    
    const currentUrl = window.location.href;
    let collectionName = null;
    
    const collectionMatch = currentUrl.match(/\/saved\/([^\/]+)/);
    if (collectionMatch && collectionMatch[1]) {
      collectionName = collectionMatch[1];
      if (collectionName === 'all-posts') {
        collectionName = null;
      }
    }
    
    const posts = await this.scrapePostsFromCurrentPage(collectionName);
    
    const collections = collectionName ? [{ name: collectionName, posts: posts }] : [];
    
    return {
      collections,
      posts,
      allPosts: collectionName ? [] : posts
    };
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { InstagramScraper, extractShortcode, normalizeUrl };
}
