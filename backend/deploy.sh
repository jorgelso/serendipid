#!/bin/bash
# Update a server install of Serendipid: pull the latest code, refresh Python
# dependencies, optionally rebuild the web app, and restart the services.
#
# Run it on the server:            ./backend/deploy.sh
# or from another machine:         ssh user@host "/path/to/repo/backend/deploy.sh"
#
# Settings (environment variables):
#   SERENDIPID_SERVICE       systemd unit for the backend   (default: serendipid)
#   SERENDIPID_WEB_SERVICE   systemd unit for the web app   (default: unset = don't rebuild the web app)
#   SERENDIPID_BRANCH        branch to pull                 (default: the current branch)

set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(git -C "$BACKEND_DIR" rev-parse --show-toplevel)"
SERVICE="${SERENDIPID_SERVICE:-serendipid}"
WEB_SERVICE="${SERENDIPID_WEB_SERVICE:-}"
BRANCH="${SERENDIPID_BRANCH:-$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)}"

echo "Pulling $BRANCH in $REPO_DIR"
git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"

echo "Updating backend dependencies"
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

if [ -n "$WEB_SERVICE" ]; then
    echo "Rebuilding the web app"
    (cd "$REPO_DIR/serendipid-web" && npm ci && npm run build)
    sudo systemctl restart "$WEB_SERVICE"
fi

sudo systemctl restart "$SERVICE"
echo "Done: restarted $SERVICE${WEB_SERVICE:+ and $WEB_SERVICE}"
