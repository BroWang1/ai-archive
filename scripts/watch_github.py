#!/usr/bin/env python3
"""Radar layer: watch the labs' GitHub orgs for new repos (code often lands
before weights). Alert-only — never captures; HF remains the system of record.

Usage: python3 scripts/watch_github.py
Exits 5 when new lab repos appeared, so CI can open an issue.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "github_watch.json"

# the labs' GitHub homes (different names than their HF orgs)
LAB_GH = ["deepseek-ai", "QwenLM", "zai-org", "MoonshotAI", "Tencent-Hunyuan",
          "Wan-Video", "MiniMax-AI", "InternLM", "OpenBMB", "stepfun-ai",
          "baichuan-inc", "FlagOpen", "XiaomiMiMo",
          # runtime ecosystem: new support here = archived models become runnable
          "ggml-org", "vllm-project"]


def org_repos(org):
    url = f"https://api.github.com/orgs/{org}/repos?sort=created&direction=desc&per_page=30"
    headers = {"User-Agent": "ai-archive/watch", "Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return [(x["full_name"], x.get("description") or "", x.get("created_at", ""))
                for x in json.load(r)]


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = json.loads(STATE.read_text()) if STATE.exists() else {"known": {}, "log": [], "first_run_done": False}
    first = not state.get("first_run_done")
    fresh = []
    for org in LAB_GH:
        try:
            repos = org_repos(org)
        except Exception as e:
            print(f"  ? {org}: {e}")
            continue
        known = set(state["known"].get(org, []))
        for name, desc, created in repos:
            if name not in known:
                state["known"].setdefault(org, []).append(name)
                if not first:
                    fresh.append((name, desc))
                    state["log"].append({"id": name, "at": now, "desc": desc[:140]})

    state["first_run_done"] = True
    state["last_run"] = now
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    if first:
        print(f"baseline: {sum(len(v) for v in state['known'].values())} lab repos across {len(LAB_GH)} GitHub orgs")
        return
    if fresh:
        print("NEW LAB CODE (radar — weights may follow on HF):")
        for name, desc in fresh:
            print(f"  >> {name}  {desc[:100]}")
        sys.exit(5)
    print("no new lab repos")


if __name__ == "__main__":
    main()
