/**
 * SuperBrain Extension - Local Database
 * Manages local storage for scraped posts and collections
 */

const DB_VERSION = 1;
const STORAGE_KEY = 'superbrain_db';

const COLLECTION_ICONS = [
  'folder',
  'airplane',
  'restaurant',
  'shirt',
  'fitness',
  'book',
  'film',
  'camera',
  'star',
  'heart',
  'flame',
  'pin',
  'time'
];

const ICON_KEYWORDS = {
  airplane: ['travel', 'trip', 'vacation', 'flight', 'holiday', 'tourism'],
  restaurant: ['food', 'recipe', 'meal', 'cooking', 'restaurant', 'eat', 'dish'],
  shirt: ['fashion', 'style', 'outfit', 'clothes', 'clothing', 'dress'],
  fitness: ['workout', 'gym', 'exercise', 'fitness', 'training', 'health'],
  book: ['book', 'read', 'reading', 'study', 'learning', 'education'],
  film: ['movie', 'film', 'cinema', 'series', 'tv', 'show'],
  camera: ['photo', 'photography', 'pic', 'picture', 'art', 'design'],
  star: ['favorite', 'best', 'top', 'rated', 'wishlist'],
  heart: ['love', 'like', 'heart', 'favorite', 'like'],
  flame: ['hot', 'trending', 'fire', 'popular'],
  pin: ['place', 'location', 'spot', 'place', 'address'],
  time: ['watch', 'later', 'queue', 'reminder']
};

function getIconForCollection(name) {
  const lowerName = name.toLowerCase();
  
  for (const [icon, keywords] of Object.entries(ICON_KEYWORDS)) {
    if (keywords.some(keyword => lowerName.includes(keyword))) {
      return icon;
    }
  }
  
  return 'folder';
}

function normalizeCollectionName(name) {
  return name.toLowerCase().trim();
}

function extractShortcode(url) {
  const match = url.match(/\/(p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
  return match ? match[2] : null;
}

class SuperBrainDB {
  constructor() {
    this.db = null;
  }

  async init() {
    return new Promise((resolve) => {
      chrome.storage.local.get([STORAGE_KEY], (result) => {
        if (result[STORAGE_KEY]) {
          this.db = result[STORAGE_KEY];
        } else {
          this.db = {
            version: DB_VERSION,
            collections: [],
            posts: [],
            importHistory: [],
            failedItems: []
          };
        }
        resolve(this.db);
      });
    });
  }

  async save() {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [STORAGE_KEY]: this.db }, resolve);
    });
  }

  async addCollection(collection) {
    const existing = this.db.collections.find(c => 
      normalizeCollectionName(c.name) === normalizeCollectionName(collection.name)
    );
    
    if (existing) {
      return existing;
    }

    const newCollection = {
      id: `ig_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name: collection.name,
      icon: collection.icon || getIconForCollection(collection.name),
      shortcodes: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      sbCollectionId: null,
      sbSynced: false
    };

    this.db.collections.push(newCollection);
    await this.save();
    return newCollection;
  }

  async addPost(url, collectionName = null) {
    const shortcode = extractShortcode(url);
    if (!shortcode) return null;

    let post = this.db.posts.find(p => p.shortcode === shortcode);
    
    if (!post) {
      post = {
        shortcode,
        url,
        collections: [],
        status: 'pending',
        attempts: 0,
        lastError: null,
        createdAt: new Date().toISOString(),
        processedAt: null
      };
      this.db.posts.push(post);
    }

    if (collectionName) {
      const collection = this.db.collections.find(c => 
        normalizeCollectionName(c.name) === normalizeCollectionName(collectionName)
      );
      
      if (collection && !post.collections.includes(collection.name)) {
        post.collections.push(collection.name);
        
        if (!collection.shortcodes.includes(shortcode)) {
          collection.shortcodes.push(shortcode);
          collection.updatedAt = new Date().toISOString();
        }
      }
    }

    await this.save();
    return post;
  }

  async markPostProcessed(shortcode) {
    const post = this.db.posts.find(p => p.shortcode === shortcode);
    if (post) {
      post.status = 'processed';
      post.processedAt = new Date().toISOString();
      post.lastError = null;
      await this.save();
    }
  }

  async markPostFailed(shortcode, error) {
    const post = this.db.posts.find(p => p.shortcode === shortcode);
    if (post) {
      post.status = 'failed';
      post.attempts++;
      post.lastError = error;
      
      const failedItem = this.db.failedItems.find(f => f.shortcode === shortcode);
      if (!failedItem) {
        this.db.failedItems.push({
          shortcode,
          url: post.url,
          error,
          attempts: post.attempts,
          failedAt: new Date().toISOString()
        });
      } else {
        failedItem.attempts = post.attempts;
        failedItem.error = error;
        failedItem.failedAt = new Date().toISOString();
      }
      
      await this.save();
    }
  }

  async markPostSaved(shortcode, sbCollectionId = null) {
    const post = this.db.posts.find(p => p.shortcode === shortcode);
    if (post) {
      post.status = 'saved';
      post.processedAt = new Date().toISOString();
      post.lastError = null;
      
      if (sbCollectionId) {
        post.sbCollectionId = sbCollectionId;
      }

      const failedIndex = this.db.failedItems.findIndex(f => f.shortcode === shortcode);
      if (failedIndex !== -1) {
        this.db.failedItems.splice(failedIndex, 1);
      }
      
      await this.save();
    }
  }

  async getPost(shortcode) {
    return this.db.posts.find(p => p.shortcode === shortcode);
  }

  async getPostByUrl(url) {
    const shortcode = extractShortcode(url);
    return shortcode ? this.getPost(shortcode) : null;
  }

  async getCollection(name) {
    return this.db.collections.find(c => 
      normalizeCollectionName(c.name) === normalizeCollectionName(name)
    );
  }

  async getAllCollections() {
    return this.db.collections;
  }

  async getAllPosts() {
    return this.db.posts;
  }

  async getPostsInCollection(collectionName) {
    const collection = await this.getCollection(collectionName);
    if (!collection) return [];
    return this.db.posts.filter(p => 
      p.collections.some(c => normalizeCollectionName(c) === normalizeCollectionName(collectionName))
    );
  }

  async getPostsWithoutCollection() {
    return this.db.posts.filter(p => 
      p.collections.length === 0 && p.status !== 'processed'
    );
  }

  async getFailedItems() {
    return this.db.failedItems;
  }

  async getPendingPosts() {
    return this.db.posts.filter(p => 
      p.status === 'pending' || p.status === 'failed'
    );
  }

  async getStats() {
    const posts = this.db.posts;
    const collections = this.db.collections;
    const failed = this.db.failedItems;

    return {
      totalPosts: posts.length,
      processed: posts.filter(p => p.status === 'processed' || p.status === 'saved').length,
      pending: posts.filter(p => p.status === 'pending').length,
      failed: failed.length,
      collections: collections.length
    };
  }

  async updateCollectionSbId(localId, sbCollectionId) {
    const collection = this.db.collections.find(c => c.id === localId);
    if (collection) {
      collection.sbCollectionId = sbCollectionId;
      collection.sbSynced = true;
      await this.save();
    }
  }

  async retryFailed(shortcode) {
    const post = this.db.posts.find(p => p.shortcode === shortcode);
    if (post) {
      post.status = 'pending';
      post.lastError = null;
      await this.save();
      return true;
    }
    return false;
  }

  async retryAllFailed() {
    const failedShortcodes = this.db.failedItems.map(f => f.shortcode);
    for (const shortcode of failedShortcodes) {
      await this.retryFailed(shortcode);
    }
    return failedShortcodes.length;
  }

  async clearFailed() {
    this.db.failedItems = [];
    this.db.posts.forEach(p => {
      if (p.status === 'failed') {
        p.status = 'pending';
        p.lastError = null;
      }
    });
    await this.save();
  }

  async clearAll() {
    this.db = {
      version: DB_VERSION,
      collections: [],
      posts: [],
      importHistory: [],
      failedItems: []
    };
    await this.save();
  }

  async getPostsForImport() {
    const posts = [];
    
    const userCollectionPosts = this.db.posts.filter(p => 
      p.collections.length > 0 && (p.status === 'pending' || p.status === 'failed')
    );
    
    for (const post of userCollectionPosts) {
      posts.push({
        ...post,
        importCollection: post.collections[0]
      });
    }
    
    const noCollectionPosts = this.db.posts.filter(p => 
      p.collections.length === 0 && (p.status === 'pending' || p.status === 'failed')
    );
    
    for (const post of noCollectionPosts) {
      posts.push({
        ...post,
        importCollection: null
      });
    }
    
    return posts;
  }
}

const db = new SuperBrainDB();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SuperBrainDB, db, getIconForCollection, extractShortcode };
}
