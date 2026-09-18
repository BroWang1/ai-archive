#!/usr/bin/env python3
"""Scan tracked canonical orgs for new model releases.

Usage: python3 scripts/discover.py [--auto-capture [CAP]]

Compares each org's current repo listing against state/known_repos.json.
With --auto-capture, immediately ingests new repos (capture-first,
curate-later; metadata + code snapshot only, never weights), up to CAP
per run (default 20). Exits 3 when new repos were found, so CI can open
an issue listing them.
"""
import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "known_repos.json"
HF = "https://huggingface.co"


def org_repos(org):
    url = f"{HF}/api/models?author={org}&limit=1000&sort=lastModified&direction=-1"
    req = urllib.request.Request(url, headers={"User-Agent": "ai-archive/discover"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return [m["id"] for m in json.load(r)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-capture", nargs="?", const=20, type=int, default=None)
    args = ap.parse_args()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    orgs = json.loads((ROOT / "config" / "orgs.json").read_text())["orgs"]
    state = json.loads(STATE.read_text()) if STATE.exists() else {"known": {}, "first_run_done": False}
    first_run = not state.get("first_run_done")
    new = []

    for org in orgs:
        try:
            current = org_repos(org)
        except Exception as e:
            print(f"  ? {org}: {e}")
            continue
        known = set(state["known"].get(org, []))
        fresh = [r for r in current if r not in known]
        state["known"][org] = sorted(set(current) | known)
        if not first_run:
            new.extend(fresh)

    state["first_run_done"] = True
    state["last_run"] = now
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    total = sum(len(v) for v in state["known"].values())
    print(f"tracking {total} repos across {len(orgs)} orgs")
    if first_run:
        print("first run: baseline recorded, no alerts")
        return
    if new:
        print("NEW RELEASES (capture-first, curate-later):")
        for r in new:
            print(f"  ++ {r}")
        if args.auto_capture:
            import time
            sys.path.insert(0, str(ROOT / "scripts"))
            import classify
            import ingest
            for r in new[: args.auto_capture]:
                try:
                    ingest.ingest(r)
                    classify.classify_record(ROOT / "index" / f"{r}.json")
                    print(f"  auto-captured {r}")
                except Exception as e:
                    print(f"  !! capture failed {r}: {e}")
                time.sleep(2)
            if len(new) > args.auto_capture:
                print(f"  ({len(new) - args.auto_capture} more left for next run)")
        sys.exit(3)
    print("no new releases")


if __name__ == "__main__":
    main()
