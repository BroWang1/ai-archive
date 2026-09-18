#!/usr/bin/env python3
"""Spot world-class or fast-rising open models from labs we don't track yet.

Usage: python3 scripts/trending.py

Pulls HF's global trending list, keeps open-weight-looking model repos whose
org is outside config/orgs.json (both lists), and suggests them. Exits 4 when
there are suggestions, so CI can open an issue. State in state/trending_seen.json
prevents re-alerting on the same repo.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "trending_seen.json"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-archive/trending"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    cfg = json.loads((ROOT / "config" / "orgs.json").read_text())
    tracked = set(cfg["orgs"]) | set(cfg.get("extra_orgs", []))
    seen = json.loads(STATE.read_text()) if STATE.exists() else {"repos": []}

    trending = fetch("https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=60")
    fresh = []
    for m in trending:
        rid = m["id"]
        org = rid.split("/")[0]
        if org in tracked or rid in seen["repos"]:
            continue
        if (m.get("downloads") or 0) < 1000:
            continue
        fresh.append((rid, m.get("downloads", 0), m.get("likes", 0), m.get("pipeline_tag", "?")))
        seen["repos"].append(rid)
        seen.setdefault("log", []).append(
            {"id": rid, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "downloads": m.get("downloads", 0)})

    seen["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(seen, indent=2) + "\n")

    if fresh:
        print("TRENDING OUTSIDE TRACKED ORGS (candidates for new labs / world-class models):")
        for rid, dl, likes, tag in fresh:
            print(f"  ?? {rid}  ({tag}, {dl:,} dl, {likes} likes)  -> consider: add org or ingest")
        sys.exit(4)
    print("nothing new trending outside tracked orgs")


if __name__ == "__main__":
    main()
