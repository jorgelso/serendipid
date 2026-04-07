import sys

path = 'D:/superbrain/superbrain-app/src/screens/RetryQueueScreen.tsx'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace fp.thumbnail_url with None/removed context
content = content.replace("if (fp.thumbnail_url) return fp.thumbnail_url;", "")
content = content.replace("title: fp.title || fp.url,", "title: fp.url,")
content = content.replace("thumbnail_url: fp.thumbnail_url,", "thumbnail_url: undefined,")
content = content.replace("await postsCache.markAsFailed(fp.shortcode, fp.url, fp.title, fp.thumbnail_url, fp.content_type);", "await postsCache.markAsFailed(fp.shortcode, fp.url, fp.url, undefined, fp.content_type);")
content = content.replace("{fp.title || fp.url}", "{fp.url}")
content = content.replace("{selectedPost?.title || selectedPost?.url}", "{selectedPost?.url}")
content = content.replace("{selectedPost?.failedAt && (\\n                <Text style={styles.sheetDate}>\\n                  Failed {new Date(selectedPost.failedAt).toLocaleDateString()}\\n                </Text>\\n              )}", "")
content = content.replace("{selectedPost?.failedAt && (", "/*")
content = content.replace("Failed {new Date(selectedPost.failedAt).toLocaleDateString()}", "")
content = content.replace("</Text>\\n              )}", "*/")


with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Patched RetryQueueScreen.tsx')
