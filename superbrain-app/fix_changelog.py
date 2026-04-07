import sys

path = 'D:/superbrain/docs/CHANGELOG.md'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '### ? Added' in line:
        insert_idx = i + 2
        break

new_content = lines[:insert_idx] + [
    "- **CLI status Command**: Run superbrain-server status (or update) to instantly print server connection URL and QR code without restarting the backend.\\n",
    "- **Retry Queue Screen**: Full interactive view inside the mobile app to manage failed items and view failed dates.\\n",
    "- **Optimistic UI Loading**: The Settings and Home screens now show cached local data instantly while syncing gracefully in the background, eliminating the previous navigation freeze.\\n",
    "- **Backend DELETE Endpoint**: New native endpoint (/queue/{shortcode}) to safely prune stuck posts from the retry queue.\\n",
    "\\n"
] + lines[insert_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_content)
print("Updated CHANGELOG.md")
