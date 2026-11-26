"""Small file utilities shared by the MLX CLI and the parity tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory


def write_json(path: Path, payload) -> None:
    """Publish a complete JSON file atomically (same contract as the torch CLI)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / "result.json"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.link(temporary, path)
