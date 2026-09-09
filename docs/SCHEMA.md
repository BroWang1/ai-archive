# Index record schema

One JSON file per model: `index/<org>/<name>.json`. A record holds one or more **captures** (one per upstream revision seen). Fields marked *(auto)* are written by `scripts/ingest.py`; the rest are curated by hand.

```
{
  "repo_id": "zai-org/GLM-4.6",              (auto) canonical upstream id
  "canonical_org": "zai-org",                 (auto) must be in config/orgs.json
  "status": "live",                           (auto, liveness.py) live | gated | gone
  "captures": [
    {
      "revision": "<40-char sha>",            (auto) pinned upstream commit
      "captured_at": "2026-09-09T20:11:04Z",  (auto) UTC capture time
      "provenance": {                         (auto) archive's own chain of custody
        "endpoint": "https://huggingface.co/api/models/...",
        "tool": "ingest.py/0.1",
        "etag": "...", "last_modified": "..."
      },
      "license": {
        "tag": "mit",                         (auto) HF cardData tag — MUTABLE, do not trust alone
        "file": "LICENSE",                    (auto) which file was snapshotted
        "sha256": "...",                      (auto) hash of the license TEXT at capture
        "redistributable": null,              curated: true | false | null (unclassified)
        "obligations": [],                    curated: e.g. "attribution", "MAU-cap-100M",
                                              "territory-excludes-EU-UK-KR", "pass-through-use-restrictions"
      },
      "gate_terms_sha256": null,              (auto) hash of extra_gated_* frontmatter if present
      "files": [                              (auto) full upstream file manifest
        {"path": "model-00001-of-000XX.safetensors",
         "size": 4996u, "sha256": "<lfs oid>", "kind": "weights"},
        {"path": "config.json", "size": 1234, "sha256": "<computed>", "kind": "snapshot"}
      ],
      "total_bytes": 713600000000,            (auto)
      "weight_bytes": 713500000000,           (auto)
      "snapshot_dir": "snapshots/zai-org/GLM-4.6/<sha>/",  (auto)
      "runtime": {                            curated: out-of-repo code the model needs
        "external_repos": [                   e.g. {"url": "https://github.com/deepseek-ai/FlashMLA",
                                                    "commit": "<sha>", "role": "kernel"}
        ],
        "working_env": null                   e.g. {"transformers": "4.57.1", "torch": "2.4.0",
                                                    "notes": "breaks on transformers>=5.0 (#44561)"}
      },
      "serving": null,                        curated: lab-verified deploy config, verbatim
                                              e.g. {"engine": "vllm", "version": "0.19.1",
                                                    "command": "...", "flags": [...]}
      "mirrors": {                            (auto, mirror.py)
        "hf": null,                           e.g. {"repo": "<archive-org>/GLM-4.6",
                                                    "byte_identical": true, "mirrored_at": "..."}
        "master": null
      }
    }
  ],
  "errata": [                                 curated: known post-release problems
    {"type": "chat_template", "description": "...", "discovered": "2026-..",
     "upstream_fixed_in": null, "fix_url": null, "affects_benchmarks": true}
  ],
  "context": {                                curated: fragile release context
    "announcement_urls": [], "tech_report": null, "arxiv": null
  },
  "notes": ""
}
```

## Rules

- `kind: "weights"` is assigned by file extension (`.safetensors .bin .pt .pth .gguf .h5 .msgpack .ckpt .onnx`). Weight files are manifested (size + upstream LFS sha256) but **never** stored in this repo.
- Everything else is downloaded into `snapshot_dir` and sha256'd locally — the code/context layer.
- A new upstream revision appends a capture; existing captures are never edited except to fill curated fields. History accumulates.
- `license.redistributable` starts `null`. Nothing is publicly mirrored while it is `null` or `false`.
- Liveness transitions (`live → gone`) are recorded by `scripts/liveness.py` in `state/liveness.json` with timestamps; the record's `status` is updated but captures are kept forever — that is the point.
