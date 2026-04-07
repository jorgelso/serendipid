import sys

path = 'D:/superbrain/docs/CHANGELOG.md'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

insert_idx = 7

new_content = lines[:insert_idx] + [
    "## [Unreleased]\n",
    "\n",
    "### Added\n",
    "- **CLI status Command**: Run 'superbrain-server status' (or 'update') to show server QR code and URLs instantly and safely without crashing on startup port conflicts.\n",
    "- **Mobile Retry Queue Screen**: A dedicated screen in Settings to see failed analyses, allowing you to directly delete stuck processing items using a new 'DELETE /queue/{shortcode}' endpoint.\n",
    "\n",
    "### Fixed & Changed\n",
    "- **UI Performance**: Resolved 15-20s navigation freezes when navigating to Settings or Library screens by returning cached data instantly and pushing blocking calls to the background.\n",
    "- **UI Fix**: Fixed a visual bug where the 'Analyzing...' placeholder cards on the Home Screen were erroneously deleted from the feed after using the Share Intent.\n",
    "- **Visual Polish**: Converted remaining text emojis (brain, heart) in app screens to native Ionicons.\n",
    "\n"
]

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_content)
    f.writelines(lines[insert_idx:])

print("Fixed changelog successfully!")
