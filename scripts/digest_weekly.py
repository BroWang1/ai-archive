#!/usr/bin/env python3
"""Weekly digest, fully self-running. Facts come from the archive's own records;
prose is optionally polished by the DeepSeek API (DEEPSEEK_API_KEY env) for
fractions of a cent — with a plain factual fallback so no AI is ever required.

Usage: python3 scripts/digest_weekly.py
Appends one entry to state/digests.json and prints it.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "digests.json"


def week_events():
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    captured, mirrored, alerts = [], [], []
    for p in (ROOT / "index").rglob("*.json"):
        r = json.loads(p.read_text())
        for cap in r["captures"]:
            if cap["captured_at"] >= cutoff:
                captured.append(r["repo_id"])
            hf = (cap.get("mirrors") or {}).get("hf")
            if hf and hf.get("mirrored_at", "") >= cutoff:
                mirrored.append(r["repo_id"])
    liv = ROOT / "state" / "liveness.json"
    if liv.exists():
        for rid, e in json.loads(liv.read_text()).get("repos", {}).items():
            for h in e.get("history", []):
                if h["at"] >= cutoff and h.get("from") and h["from"] != h["to"]:
                    alerts.append(f"{rid} {h['from']}->{h['to']}")
    radar = []
    for name, key in [("radar.json", "log"), ("github_watch.json", "log"), ("trending_seen.json", "log")]:
        f = ROOT / "state" / name
        if f.exists():
            for e in json.loads(f.read_text()).get(key, []):
                if e.get("at", "") >= cutoff:
                    radar.append(e.get("text") or e.get("id", ""))
    return captured, mirrored, alerts, radar


def factual_text(captured, mirrored, alerts, radar):
    bits = [f"Week in local AI: {len(captured)} models captured, {len(mirrored)} new preserved mirrors."]
    if mirrored:
        bits.append("Now downloadable: " + ", ".join(m.split("/")[1] for m in mirrored[:4]) +
                    ("…" if len(mirrored) > 4 else "") + ".")
    if alerts:
        bits.append(f"Upstream alerts: {'; '.join(alerts[:3])}.")
    if radar:
        bits.append(f"{len(radar)} radar signals (papers, buzz, lab code).")
    return " ".join(bits)


def deepseek_polish(facts):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content":
             "You write a 2-3 sentence weekly digest for aiarchive.info, a preservation archive of "
             "open-weight AI models. Factual, specific, no hype, no invented facts — use ONLY the "
             "facts given. Plain language for people who run AI models locally."},
            {"role": "user", "content": facts}],
        "temperature": 0.3, "max_tokens": 200}).encode()
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"deepseek unavailable ({e}); using factual digest")
        return None


def check_balance():
    """Report DeepSeek prepaid balance; warn when it runs low."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return
    req = urllib.request.Request("https://api.deepseek.com/user/balance",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            info = json.load(r)
        for b in info.get("balance_infos", []):
            bal = float(b.get("total_balance", 0))
            cur = b.get("currency", "?")
            print(f"deepseek balance: {bal:.2f} {cur}")
            low = bal < (0.50 if cur == "USD" else 3.50)
            if low:
                print(f"WARNING: DEEPSEEK BALANCE LOW ({bal:.2f} {cur}) — top up or the "
                      f"digest falls back to the no-AI version (nothing else is affected)")
    except Exception as e:
        print(f"balance check unavailable: {e}")


def main():
    captured, mirrored, alerts, radar = week_events()
    facts = json.dumps({"captured": captured, "mirrored": mirrored,
                        "alerts": alerts, "radar_signals": radar[:10]}, indent=1)
    text = deepseek_polish(facts) or factual_text(captured, mirrored, alerts, radar)
    state = json.loads(STATE.read_text()) if STATE.exists() else {"digests": []}
    state["digests"].append({
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "text": text,
        "url": "https://github.com/BroWang1/ai-archive/issues", "action": "details"})
    state["digests"] = state["digests"][-52:]  # keep a year
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    print(text)
    check_balance()


if __name__ == "__main__":
    main()
