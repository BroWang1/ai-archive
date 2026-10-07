#!/usr/bin/env python3
"""Pull torrent results from the worker VM into the repo so the website can
offer HF-independent downloads: .torrent files land in docs/torrents/ (served
by GitHub Pages at aiarchive.info/torrents/...), and each index record gets
mirrors.torrent with the magnet link and infohash.

Usage (on any machine with the VM's SSH key):
    python3 scripts/adopt_torrents.py [user@host]
Then: python3 scripts/build_catalog.py && git add -A && commit/push.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VM = sys.argv[1] if len(sys.argv) > 1 else "root@95.216.199.18"
SSH = os.environ.get("VAULT_VM_SSH", "ssh -i ~/.ssh/aiarchive_vault -o IdentitiesOnly=yes")


def main():
    tdir = ROOT / "docs" / "torrents"
    tdir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-a", "-e", SSH, f"{VM}:/opt/torrents/", f"{tdir}/"], check=True)
    subprocess.run(["rsync", "-a", "-e", SSH, f"{VM}:/opt/ai-archive/state/vault_state.json",
                    str(ROOT / "state" / "vault_state.json")], check=True)

    state = json.loads((ROOT / "state" / "vault_state.json").read_text())
    adopted = 0
    for rid, v in state["vaulted"].items():
        rec_path = ROOT / "index" / f"{rid}.json"
        if not rec_path.exists():
            continue
        rec = json.loads(rec_path.read_text())
        cap = rec["captures"][-1]
        cap.setdefault("mirrors", {})
        cap["mirrors"]["vault"] = {"at": v["at"], "revision": v["revision"],
                                   "box_path": v["box_path"]}
        t = v.get("torrent")
        if t and (tdir / t["file"]).exists():
            cap["mirrors"]["torrent"] = {"file": f"torrents/{t['file']}",
                                         "infohash": t["infohash"], "magnet": t["magnet"]}
            adopted += 1
        rec_path.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"adopted {adopted} torrents, {len(state['vaulted'])} vault records")


if __name__ == "__main__":
    main()
