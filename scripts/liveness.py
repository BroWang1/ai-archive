#!/usr/bin/env python3
"""Check every indexed upstream repo for takedowns (404/403 transitions).

Usage: python3 scripts/liveness.py

Writes state/liveness.json (committed by CI — the commit doubles as the
heartbeat that keeps the scheduled workflow alive). Prints transitions and
exits 2 when any repo newly went gone/gated, so CI can open an issue.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "liveness.json"
HF = "https://huggingface.co"


def probe(repo_id):
    req = urllib.request.Request(f"{HF}/api/models/{repo_id}",
                                 headers={"User-Agent": "ai-archive/liveness"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except urllib.error.URLError:
        return None  # network problem, not a verdict


def status_of(code):
    if code == 200:
        return "live"
    if code in (401, 403):
        return "gated"
    if code == 404:
        return "gone"
    return "unknown"


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = json.loads(STATE.read_text()) if STATE.exists() else {"repos": {}}
    records = sorted((ROOT / "index").rglob("*.json"))
    transitions = []

    for record_path in records:
        record = json.loads(record_path.read_text())
        repo_id = record["repo_id"]
        code = probe(repo_id)
        if code is None:
            print(f"  ? {repo_id}: network error, skipping")
            continue
        new = status_of(code)
        prev = state["repos"].get(repo_id, {}).get("status")
        entry = state["repos"].setdefault(repo_id, {"history": []})
        entry["status"] = new
        entry["last_checked"] = now
        entry["last_http"] = code
        if prev and prev != new:
            entry["history"].append({"at": now, "from": prev, "to": new, "http": code})
            transitions.append((repo_id, prev, new))
            record["status"] = new
            record_path.write_text(json.dumps(record, indent=2) + "\n")
        elif not prev:
            entry["history"].append({"at": now, "from": None, "to": new, "http": code})

    state["last_run"] = now
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    print(f"checked {len(records)} repos at {now}")
    if transitions:
        print("TRANSITIONS DETECTED:")
        for repo_id, prev, new in transitions:
            print(f"  !! {repo_id}: {prev} -> {new}")
        sys.exit(2)
    print("no transitions")


if __name__ == "__main__":
    main()
