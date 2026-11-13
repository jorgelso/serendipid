# serendipid-extension

A Chrome extension (Manifest V3) that imports your Instagram saved posts and collections into Serendipid directly from the browser, as an alternative to Instagram's data export. It scrolls through your saved posts, sends each URL to the backend for analysis, and recreates your Instagram collections in Serendipid.

## Install

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select this `serendipid-extension` folder.

## Configure

1. Click the extension icon, then **Settings**.
2. Enter the backend URL, for example `http://localhost:5050` or your server's address on your network.
3. Enter the 32-character access token. In the backend folder, `python utils/manage_token.py show` prints it.
4. Click **Save Settings**, then **Test Connection**.

The extension talks to the backend directly, so the backend must be reachable from the computer running Chrome.

## Use

1. Open Instagram in the same browser and go to your profile's **Saved** page.
2. Click the extension icon and choose **Scan Instagram Saved**.
3. Keep the tab open while it scrolls, collects post URLs and submits them. Progress and failures are shown in the overlay and the popup.

Posts already in your library are skipped, so running it again only submits new saves. Instagram rate-limits heavy browsing; if it starts failing, stop and try again later.

## Backend endpoints used

| Endpoint | Method | Purpose |
|---|---|---|
| `/ping` | GET | Connection test |
| `/analyze` | POST | Submit a post URL for analysis |
| `/cache/{shortcode}` | GET | Check whether a post is already analyzed |
| `/collections` | GET, POST | List and create collections |
| `/collections/{id}/posts` | PUT | Set a collection's posts |

## Layout

```
manifest.json
background/background.js   service worker
content/                   script injected into instagram.com, and its overlay styles
popup/                     toolbar popup
options/                   settings page
icons/
```
