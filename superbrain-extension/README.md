# SuperBrain Chrome Extension

A Chrome extension for bulk importing Instagram saved posts and collections to SuperBrain.

## Features

- **Bulk Import**: Import all Instagram saved posts with a single click
- **Collection Sync**: Automatically recreates Instagram collections in SuperBrain with matching names and icons
- **Background Processing**: Posts are sent to SuperBrain backend for AI analysis
- **Progress Tracking**: Real-time progress and activity logging

## Installation

### Generate Icons (Required)

Before loading the extension in Chrome, you need to generate PNG icons from the SVG. You can use any of these methods:

**Method 1: Online Converter**
1. Go to https://cloudconvert.com/svg-to-png
2. Upload `icons/icon.svg`
3. Convert to PNG at sizes: 16x16, 48x48, 128x128
4. Save as `icon16.png`, `icon48.png`, `icon128.png` in the `icons/` folder

**Method 2: Using ImageMagick (CLI)**
```bash
# Install ImageMagick if needed, then:
cd superbrain-extension/icons
magick convert -background none icon.svg -resize 16x16 icon16.png
magick convert -background none icon.svg -resize 48x48 icon48.png
magick convert -background none icon.svg -resize 128x128 icon128.png
```

**Method 3: Using Python (Pillow)**
```python
from PIL import Image
import io
import base64

svg_data = open('icon.svg', 'r').read()

for size in [16, 48, 128]:
    # Use cairosvg or other SVG converter
    png_data = convert_svg_to_png(svg_data, size)
    Image.open(io.BytesIO(png_data)).save(f'icon{size}.png')
```

### Load Extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `superbrain-extension` folder

## Configuration

1. Click the SuperBrain extension icon in the toolbar
2. Click "Settings" at the bottom
3. Enter your SuperBrain server URL (e.g., `http://localhost:5000`)
4. Enter your 8-character Access Token from the SuperBrain backend
5. Click "Save Settings"
6. Click "Test Connection" to verify

## Usage

1. Open Instagram and navigate to your profile
2. Click on "Saved" to view your saved posts
3. Click the SuperBrain extension icon in your browser toolbar
4. Click "Scan Instagram Saved"
5. The extension will:
   - Scroll through your saved posts
   - Extract post URLs
   - Send them to SuperBrain for analysis
   - Create collections that match your Instagram collections

## How It Works

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Instagram      │────▶│  Chrome          │────▶│  SuperBrain     │
│  Saved Page     │     │  Extension       │     │  Backend        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────────────┐
                        │  Scroll & Extract │
                        │  Post URLs        │
                        └──────────────────┘
```

## API Integration

The extension connects to the SuperBrain backend using these endpoints:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/ping` | GET | Test connection |
| `/analyze` | POST | Submit post URL for analysis |
| `/collections` | GET | List existing collections |
| `/collections` | POST | Create new collection |
| `/collections/{id}/posts` | PUT | Add post to collection |
| `/cache/{shortcode}` | GET | Get post by shortcode |

## Files Structure

```
superbrain-extension/
├── manifest.json          # Extension manifest
├── icons/
│   ├── icon.svg           # Source SVG icon
│   ├── icon16.png         # 16x16 icon
│   ├── icon48.png         # 48x48 icon
│   └── icon128.png        # 128x128 icon
├── popup/
│   ├── popup.html         # Extension popup UI
│   ├── popup.css          # Popup styles
│   └── popup.js           # Popup logic
├── content/
│   ├── content.js         # Instagram page script
│   └── content.css        # Import overlay styles
├── background/
│   └── background.js      # Service worker
└── options/
    ├── options.html       # Settings page
    ├── options.css        # Settings styles
    └── options.js         # Settings logic
```

## Theme

The extension uses the same dark theme and color palette as the SuperBrain mobile app:

| Color | Hex | Usage |
|-------|-----|-------|
| Background | `#0f1115` | Main background |
| Card | `#1e2229` | Card backgrounds |
| Primary | `#6366f1` | Primary actions (Indigo) |
| Accent | `#8b5cf6` | Accent elements (Violet) |
| Success | `#10b981` | Success states (Emerald) |
| Error | `#ef4444` | Error states (Red) |

## Troubleshooting

### "No posts found"
- Make sure you're on an Instagram saved page
- Try scrolling manually first to load posts
- Check if Instagram is blocking automated scrolling

### "Connection failed"
- Verify your server URL is correct
- Make sure the SuperBrain backend is running
- Check if CORS is enabled on the backend

### "Import stopped"
- Instagram may have rate limits
- Try importing in smaller batches
- Wait a few minutes between imports

## License

This extension is part of the SuperBrain project and is licensed under AGPL-3.0.
