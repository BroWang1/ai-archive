#!/usr/bin/env python3
"""Create torrents for models that were vaulted before torrent creation was
added to vault_sync.py. Re-stages each one (they are the smallest models, so
this is cheap), builds the torrent, records it in state/vault_state.json.

Usage (on the worker VM):
    /opt/venv/bin/python -u scripts/torrent_backfill.py [--workdir DIR]
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vault_sync import ROOT, STATE, make_torrent  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/mnt/HC_Volume_106958500/stage")
    args = ap.parse_args()
    from huggingface_hub import snapshot_download

    state = json.loads(STATE.read_text())
    todo = [(rid, v) for rid, v in state["vaulted"].items() if not v.get("torrent")]
    print(f"{len(todo)} vaulted models need torrents")
    for rid, v in todo:
        rec = json.loads((ROOT / "index" / f"{rid}.json").read_text())
        cap = rec["captures"][-1]
        hf = (cap.get("mirrors") or {}).get("hf")
        source, revision = (hf["repo"], None) if hf else (rid, cap["revision"])
        stage = Path(args.workdir) / rid.replace("/", "__")
        print(f"== {rid} ({v['bytes']/1e9:.1f} GB)", flush=True)
        try:
            snapshot_download(repo_id=source, revision=revision, local_dir=stage)
            shutil.rmtree(stage / ".cache", ignore_errors=True)
            v["torrent"] = make_torrent(stage, rid, v["bytes"])
            STATE.write_text(json.dumps(state, indent=2) + "\n")
            print(f"  torrent: {v['torrent']['infohash'][:12]}", flush=True)
        except Exception as e:
            print(f"  failed: {type(e).__name__}: {e}", flush=True)
        finally:
            shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
