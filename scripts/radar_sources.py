#!/usr/bin/env python3
"""Diversified radar: arXiv papers + Hacker News buzz about the tracked labs.

Alert-only, like all radar — Hugging Face remains the sole capture source.
Usage: python3 scripts/radar_sources.py
Exits 6 when new findings, so CI can open an issue. State: state/radar.json
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "radar.json"

LAB_TERMS = ["DeepSeek", "Qwen", "Kimi K", "GLM-", "MiniMax", "Hunyuan", "MiniCPM", "InternLM"]
HN_MIN_POINTS = 50


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-archive/radar"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def arxiv_new(term, seen):
    q = urllib.parse.quote(f'abs:"{term}"')
    xml = get(f"https://export.arxiv.org/api/query?search_query={q}"
              f"&sortBy=submittedDate&sortOrder=descending&max_results=5")
    out = []
    for m in re.finditer(r"<entry>(.*?)</entry>", xml, re.DOTALL):
        e = m.group(1)
        aid = re.search(r"<id>(.*?)</id>", e)
        title = re.search(r"<title>(.*?)</title>", e, re.DOTALL)
        if not aid or not title:
            continue
        aid = re.sub(r"v\d+$", "", aid.group(1).strip())
        if aid in seen:
            continue
        seen.append(aid)
        out.append((re.sub(r"\s+", " ", title.group(1)).strip(), aid))
    return out


def hn_new(term, seen):
    q = urllib.parse.quote(term)
    data = json.loads(get(f"https://hn.algolia.com/api/v1/search_by_date?query={q}"
                          f"&tags=story&numericFilters=points%3E{HN_MIN_POINTS}&hitsPerPage=5"))
    out = []
    for h in data.get("hits", []):
        oid = h.get("objectID")
        if not oid or oid in seen:
            continue
        seen.append(oid)
        out.append((h.get("title", "?"), f"https://news.ycombinator.com/item?id={oid}",
                    h.get("points", 0)))
    return out


def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = json.loads(STATE.read_text()) if STATE.exists() else \
        {"arxiv_seen": [], "hn_seen": [], "log": [], "first_run_done": False}
    first = not state.get("first_run_done")
    findings = []

    for term in LAB_TERMS:
        try:
            for title, url in arxiv_new(term, state["arxiv_seen"]):
                if not first:
                    findings.append(("paper", f"New paper mentioning {term}: {title}", url))
        except Exception as e:
            print(f"  ? arxiv {term}: {e}")
        try:
            for title, url, pts in hn_new(term, state["hn_seen"]):
                if not first:
                    findings.append(("buzz", f"HN front-page ({pts} pts): {title}", url))
        except Exception as e:
            print(f"  ? hn {term}: {e}")

    for kind, text, url in findings:
        state["log"].append({"kind": kind, "at": now, "text": text, "url": url})
    state["first_run_done"] = True
    state["last_run"] = now
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2) + "\n")

    if first:
        print(f"baseline: {len(state['arxiv_seen'])} papers, {len(state['hn_seen'])} HN stories recorded")
        return
    if findings:
        print("RADAR FINDINGS:")
        for kind, text, url in findings:
            print(f"  [{kind}] {text}\n         {url}")
        sys.exit(6)
    print("radar quiet")


if __name__ == "__main__":
    main()
