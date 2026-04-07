import sys

path = 'D:/superbrain/docs/CHANGELOG.md'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = 10
new_content = lines[:insert_idx] + [
    "### Unreleased - [April 2026 Update]\\n",
    "\\n",
    "#### Features & Improvements\\n",
    "- **CLI 'status' Command**: Added \superbrain-server status\ (or \update\) to instantly print server connection URL and QR code without restarting the backend.\\n",
    "- **Retry Queue Screen**: Added a new interactive screen inside the mobile app to manage failed items and view failure details.\\n",
    "- **Optimistic UI Loading**: The Settings and Home screens now show cached local data instantly while syncing gracefully in the background, eliminating the previous navigation freeze.\\n",
    "- **UI Polish**: Missing \"Analyzing ?\" overlays automatically protected when swapping cache during share-intent background loads.\\n",
    "- **Icon Updates**: Upgraded hardcoded emojis inside Category badges to native Ionicons (like \"sparkles\" and \"brain\").\\n",
    "- **Backend DELETE Endpoint**: New native endpoint (\/queue/{shortcode}\) to safely prune stuck posts from the retry queue via the mobile app.\\n",
    "\\n",
] + lines[insert_idx:]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_content)
print("Updated CHANGELOG.md!")
