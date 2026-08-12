#!/bin/bash
# Pull the latest code and restart the SuperBrain backend service on the Pi.
# Run on the Pi itself, or remotely: ssh pi@<pi-ip> "~/second-brain/superbrain/backend/deploy.sh"

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

cd "$REPO_DIR"
git pull

cd "$REPO_DIR/superbrain/backend"
source .venv/bin/activate
pip install -r requirements.txt

sudo systemctl restart superbrain
echo "✓ Deployed and restarted superbrain.service"
