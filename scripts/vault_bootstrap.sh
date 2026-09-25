#!/bin/bash
# One-shot setup for a rented transfer VM (Hetzner Cloud, Ubuntu):
# fills the Storage Box vault from the archive's HF mirrors at datacenter speed.
# Usage on a fresh VM:
#   export VAULT_DEST="u123456@u123456.your-storagebox.de"
#   bash <(curl -fsSL https://raw.githubusercontent.com/BroWang1/ai-archive/main/scripts/vault_bootstrap.sh)
set -e
apt-get update -qq && apt-get install -y -qq git rsync python3-pip >/dev/null
pip3 -q install huggingface_hub
git clone --filter=blob:none --no-checkout https://github.com/BroWang1/ai-archive.git /opt/ai-archive
cd /opt/ai-archive
git sparse-checkout set index config scripts state
git checkout main
echo "starting vault fill (smallest first, resumable) ..."
python3 scripts/vault_sync.py --workdir /root/stage
echo "DONE — copy state/vault_state.json back to the main repo to record it"
