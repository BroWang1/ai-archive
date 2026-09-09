# ai-archive

A preservation archive for Chinese open-weight AI models and their performance data.

## Why this exists

Chinese labs (Qwen, DeepSeek, Z.ai/GLM, Moonshot, and others) publish the largest and most capable open-weight models in the world — and nobody systematically preserves them:

- **Software Heritage archives Hugging Face's git content but has explicitly declared the LFS weight files out of scope** ([their tracking issue](https://gitlab.softwareheritage.org/swh/meta/-/issues/5060)). The weights tier of this archive is the contribution no institution currently makes.
- Repos disappear (e.g. the DeepSeek repo that today survives only as a community mirror named `...-deleted-repo`), labs silently edit configs after release (Qwen3's EOS token was swapped weeks post-release, unannounced), and custom `trust_remote_code` model code permanently breaks against new `transformers` versions.
- The 2026 licensing trend is tightening: frontier releases (Kimi K3, Qwen3.8-2.4T) now carry revenue and non-commercial restrictions their predecessors didn't. The permissive window is closing, so **capture-first, curate-later**: new releases are ingested promptly; classification and benchmarking happen afterward.

## Designated community

The archive is built for an ML practitioner in 2035 with a GPU and **no access to the original vendor** — someone who needs not just the weight bytes, but the custom modeling code, the tokenizer and chat template as they stood at a specific revision, the license text as published on a specific date, the external kernel/engine code the model needs to run, and honest, provenance-labeled benchmark numbers.

## What is preserved (the layers)

| Layer | What | Where |
|---|---|---|
| Knowledge | Machine-readable index: revisions, per-file sha256, license snapshots + hashes, gate terms, errata, provenance | `index/` (this repo) |
| Code & context | Everything-but-weights per revision: modeling code, tokenizer, configs, chat template, LICENSE, README | `snapshots/` (this repo) |
| Bits | Full weight mirrors | Hugging Face org (permissively-licensed subset) + master storage tier |
| Behavior | Benchmark runs with full reproducibility envelope | HF dataset repo (planned) |

The storage tiers are redundant copies against different failure modes; the layers above are the different kinds of preservation, and each record in `index/` tracks all of them.

## Repository layout

```
config/orgs.json      canonical lab orgs tracked (resolve by org, never by name search)
index/<org>/<name>.json   one record per model (see docs/SCHEMA.md)
snapshots/<org>/<name>/<revision>/   vendored non-weight files
scripts/ingest.py     capture a model: index record + snapshot (stdlib only)
scripts/verify.py     verify snapshots/weights against the manifests
scripts/liveness.py   detect upstream takedowns (404/403 transitions)
scripts/discover.py   detect new releases across tracked orgs
scripts/mirror.py     mirror weights to the HF org (requires huggingface_hub + HF_TOKEN)
state/                liveness + discovery state (committed by CI as heartbeat)
```

## Quickstart

```bash
# capture a model (no dependencies beyond Python 3.10+)
python3 scripts/ingest.py zai-org/GLM-4.6

# verify everything against the manifests
python3 scripts/verify.py --all

# check tracked upstreams for takedowns
python3 scripts/liveness.py

# scan tracked orgs for new releases
python3 scripts/discover.py
```

## Principles

1. **Dumb files.** Plain directory trees and JSON. No database, no proprietary format. Storage providers are interchangeable; migration is copy + verify.
2. **Pin commits, don't trust them.** Every capture is pinned to a full 40-char revision. Upstream SHAs are *not* durable (Hugging Face's `super_squash_history` can destroy them), so the archive keeps its own copies of everything it references.
3. **Per-model, per-revision licensing.** Never per-lab. License text is snapshotted and hashed at capture time; the upstream tag is treated as mutable and unreliable.
4. **Provenance on every claim.** Capture timestamps, endpoints, and tool versions are recorded. Benchmark scores carry per-score provenance labels (self-reported vs independently run) and are never mixed without them.
5. **Byte-exact copies are never altered.** Fixes and corrections live in `errata`, not in the artifacts.

## Legal posture

Public mirrors are limited to models whose license permits redistribution, with the original LICENSE vendored verbatim and all credit to the original creators. Weights are never modified. Takedown requests: open an issue.

## Status

Early. Rung A (index + snapshots + monitors) is live; the HF weight-mirror pilot is next.
