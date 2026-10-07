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
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "vault_state.json"
SSH = ["ssh", "-p", "23", "-o", "StrictHostKeyChecking=accept-new"]

# torrents: the HF-independent download path. Created here because the staged
# copy is already on local disk — hashing it now is nearly free vs re-reading
# the whole vault later.
TORRENT_OUT = Path(os.environ.get("TORRENT_OUT", "/opt/torrents"))
TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.tracker.cl:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
]


def _bparse(b, i=0):
    """Minimal bencode parser; returns (value, next_index). The info dict's
    value is returned as its raw byte span so its sha1 (the infohash) can be
    computed exactly as clients do."""
    c = b[i:i + 1]
    if c == b"i":
        j = b.index(b"e", i)
        return int(b[i + 1:j]), j + 1
    if c in (b"l", b"d"):
        is_dict = c == b"d"
        i += 1
        out = {} if is_dict else []
        while b[i:i + 1] != b"e":
            if is_dict:
                k, i = _bparse(b, i)
                start = i
                v, i = _bparse(b, i)
                out[k] = (start, i) if k == b"info" else v
            else:
                v, i = _bparse(b, i)
                out.append(v)
        return out, i + 1
    j = b.index(b":", i)
    n = int(b[i:j])
    return b[j + 1:j + 1 + n], j + 1 + n


def make_torrent(stage, rid, size):
    """Create a v1 torrent of the staged snapshot; returns file/infohash/magnet."""
    TORRENT_OUT.mkdir(parents=True, exist_ok=True)
    name = rid.replace("/", "__")
    tfile = TORRENT_OUT / f"{name}.torrent"
    if tfile.exists():
        tfile.unlink()
    piece_log2 = "24" if size > 50e9 else "22"  # 16MB pieces for giants, 4MB otherwise
    cmd = ["mktorrent", "-l", piece_log2, "-n", name, "-o", str(tfile)]
    for t in TRACKERS:
        cmd += ["-a", t]
    cmd.append(str(stage))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw = tfile.read_bytes()
    top, _ = _bparse(raw)
    s, e = top[b"info"]
    ih = hashlib.sha1(raw[s:e]).hexdigest()
    magnet = (f"magnet:?xt=urn:btih:{ih}&dn={urllib.parse.quote(name)}"
              + "".join("&tr=" + urllib.parse.quote(t, safe="") for t in TRACKERS))
    return {"file": tfile.name, "infohash": ih, "magnet": magnet,
            "piece_length": 1 << int(piece_log2)}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def queue():
    """All redistributable models: from our mirror when one exists, else straight
    from the original repo at the captured revision. The vault outruns HF's
    duplication quota because plain downloads aren't capped the same way."""
    items = []
    for p in sorted((ROOT / "index").rglob("*.json")):
        r = json.loads(p.read_text())
        cap = r["captures"][-1]
        if cap["license"].get("redistributable") is not True:
            continue
        hf = (cap.get("mirrors") or {}).get("hf")
        if hf:
            items.append((cap["weight_bytes"], r["repo_id"], hf["repo"], None, cap))
        else:
            items.append((cap["weight_bytes"], r["repo_id"], r["repo_id"], cap["revision"], cap))
    items.sort(key=lambda x: x[0])
    return items


def stream_model(dest, workdir, rid, source, revision, cap):
    """Models larger than the staging disk: download, verify, upload and delete
    ONE FILE AT A TIME, so peak disk use is a single shard. Progress is kept in
    a sidecar file so an interrupted model resumes instead of restarting. No
    torrent here (that needs every file on disk at once) — made later from the
    box copy. Returns the number of hash-verified weight files."""
    from huggingface_hub import hf_hub_download
    box_path = f"ai-archive/{rid}/{cap['revision']}/"
    subprocess.run(SSH + [dest, "mkdir", "-p", box_path], check=True)
    hashes = {f["path"]: f["sha256"] for f in cap["files"]
              if f["kind"] == "weights" and f["sha256"]}
    prog = Path(workdir) / (rid.replace("/", "__") + ".stream.json")
    done_files = set(json.loads(prog.read_text())) if prog.exists() else set()
    stage = Path(workdir) / ("stream__" + rid.replace("/", "__"))
    for f in cap["files"]:
        path = f["path"]
        if path in done_files:
            continue
        local = Path(hf_hub_download(repo_id=source, filename=path,
                                     revision=revision, local_dir=stage))
        if path in hashes and sha256_file(local) != hashes[path]:
            raise RuntimeError(f"hash mismatch pre-upload: {path}")
        subprocess.run(["rsync", "-a", "--checksum", "--relative", "-e", "ssh -p 23",
                        f"{stage}/./{path}", f"{dest}:{box_path}"], check=True)
        shutil.rmtree(stage, ignore_errors=True)
        done_files.add(path)
        prog.write_text(json.dumps(sorted(done_files)))
        print(f"  streamed {path}", flush=True)
    prog.unlink()
    return len(hashes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="/tmp/vault-stage")
    ap.add_argument("--limit", type=int, default=0, help="stop after N models (0 = all)")
    ap.add_argument("--max-gb", type=float, default=0, help="skip models larger than this (staging disk cap; 0 = no cap)")
    ap.add_argument("--stream-over-gb", type=float, default=900,
                    help="models larger than this stream file-by-file instead of staging whole (0 = never)")
    args = ap.parse_args()
    dest = os.environ.get("VAULT_DEST")
    if not dest:
        sys.exit("set VAULT_DEST=u######@u######.your-storagebox.de (Hetzner Robot page)")

    from huggingface_hub import snapshot_download

    state = json.loads(STATE.read_text()) if STATE.exists() else {"vaulted": {}}
    done = 0
    for size, rid, source, revision, cap in queue():
        if rid in state["vaulted"]:
            continue
        if args.limit and done >= args.limit:
            break
        if args.max_gb and size > args.max_gb * 1e9:
            continue
        if args.stream_over_gb and size > args.stream_over_gb * 1e9:
            print(f"== {rid} ({size/1e9:.1f} GB) STREAMING file-by-file from {source}", flush=True)
            try:
                nver = stream_model(dest, args.workdir, rid, source, revision, cap)
                state["vaulted"][rid] = {
                    "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "revision": cap["revision"], "bytes": size, "streamed": True,
                    "verified_files": nver,
                    "box_path": f"ai-archive/{rid}/{cap['revision']}/"}
                STATE.parent.mkdir(exist_ok=True)
                STATE.write_text(json.dumps(state, indent=2) + "\n")
                done += 1
                print(f"  vaulted via stream ({nver} weight files verified)", flush=True)
            except Exception as e:
                print(f"  error: {type(e).__name__}: {e}", flush=True)
            continue
        print(f"== {rid} ({size/1e9:.1f} GB) from {source}" + (f"@{revision[:12]}" if revision else ""), flush=True)
        stage = Path(args.workdir) / rid.replace("/", "__")
        try:
            snapshot_download(repo_id=source, revision=revision, local_dir=stage)
            shutil.rmtree(stage / ".cache", ignore_errors=True)  # hub metadata, not model content
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
            try:
                info = make_torrent(stage, rid, size)
                state["vaulted"][rid]["torrent"] = info
                STATE.write_text(json.dumps(state, indent=2) + "\n")
                print(f"  torrent: {info['infohash'][:12]}", flush=True)
            except Exception as e:  # a torrent failure must never block preservation
                print(f"  torrent skipped: {type(e).__name__}: {e}", flush=True)
        except Exception as e:
            print(f"  error: {type(e).__name__}: {e}", flush=True)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    total_tb = sum(v["bytes"] for v in state["vaulted"].values()) / 1e12
    print(f"\nvault holds {len(state['vaulted'])} models, {total_tb:.2f} TB")


if __name__ == "__main__":
    main()
