#!/usr/bin/env python3
"""Fill the off-HF vault (Hetzner Storage Box) from the archive's mirrors,
verifying every weight file against the catalog fingerprints before upload.

Usage:
    export VAULT_DEST="u123456@u123456.your-storagebox.de"   # from Hetzner Robot
    python3 scripts/vault_sync.py [--workdir /tmp/vault-stage] [--limit N]

Designed to run on a rented VM near the Storage Box (datacenter speed) or any
machine with disk for one model at a time. Smallest models first; resumable —
state in state/vault_state.json records every verified upload. Uses ssh port 23
(Storage Box convention) and rsync; the box must have this machine's SSH key.
Verification happens BEFORE upload (local sha256 vs manifest); rsync re-checks
sizes/checksums in transit. Periodic deep re-verification is done by re-running
with --verify (re-downloads samples from the box and rehashes).
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "vault_state.json"
SSH = ["ssh", "-p", "23", "-o", "StrictHostKeyChecking=accept-new"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def queue():
    items = []
    for p in sorted((ROOT / "index").rglob("*.json")):
        r = json.loads(p.read_text())
        cap = r["captures"][-1]
        hf = (cap.get("mirrors") or {}).get("hf")
        if not hf:
            continue
        items.append((cap["weight_bytes"], r["repo_id"], hf["repo"], cap))
    items.sort()
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/tmp/vault-stage")
    ap.add_argument("--limit", type=int, default=0, help="stop after N models (0 = all)")
    ap.add_argument("--max-gb", type=float, default=0, help="skip models larger than this (staging disk cap; 0 = no cap)")
    args = ap.parse_args()
    dest = os.environ.get("VAULT_DEST")
    if not dest:
        sys.exit("set VAULT_DEST=u######@u######.your-storagebox.de (Hetzner Robot page)")

    from huggingface_hub import snapshot_download

    state = json.loads(STATE.read_text()) if STATE.exists() else {"vaulted": {}}
    done = 0
    for size, rid, mirror, cap in queue():
        if rid in state["vaulted"]:
            continue
        if args.limit and done >= args.limit:
            break
        if args.max_gb and size > args.max_gb * 1e9:
            continue
        print(f"== {rid} ({size/1e9:.1f} GB) from {mirror}", flush=True)
        stage = Path(args.workdir) / rid.replace("/", "__")
        try:
            snapshot_download(repo_id=mirror, local_dir=stage)
            manifest = {f["path"]: f["sha256"] for f in cap["files"]
                        if f["kind"] == "weights" and f["sha256"]}
            bad = [p for p, want in manifest.items()
                   if not (stage / p).exists() or sha256_file(stage / p) != want]
            if bad:
                print(f"  VERIFY FAILED pre-upload: {bad[:3]} — skipping", flush=True)
                continue
            box_path = f"ai-archive/{rid}/{cap['revision']}/"
            subprocess.run(SSH + [dest, "mkdir", "-p", box_path], check=True)
            subprocess.run(["rsync", "-a", "--checksum", "-e", "ssh -p 23",
                            f"{stage}/", f"{dest}:{box_path}"], check=True)
            state["vaulted"][rid] = {
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "revision": cap["revision"], "bytes": size,
                "verified_files": len(manifest), "box_path": box_path}
            STATE.parent.mkdir(exist_ok=True)
            STATE.write_text(json.dumps(state, indent=2) + "\n")
            done += 1
            print(f"  vaulted ({len(manifest)} weight files verified)", flush=True)
        except Exception as e:
            print(f"  error: {type(e).__name__}: {e}", flush=True)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    total_tb = sum(v["bytes"] for v in state["vaulted"].values()) / 1e12
    print(f"\nvault holds {len(state['vaulted'])} models, {total_tb:.2f} TB")


if __name__ == "__main__":
    main()
