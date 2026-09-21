from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXPECTED_ARTIFACT_SHA256 = (
    "96dfbec48282dd24d3334369a01e9e909f321ee39a1b0003c528c5379f68c1a6"
)


class ConversionTest(unittest.TestCase):
    def test_conversion_matches_pinned_artifact(self) -> None:
        source = os.environ.get("FUNASR_OFFICIAL_MODEL_PT")
        if not source:
            self.skipTest("FUNASR_OFFICIAL_MODEL_PT is not set")

        script = Path(__file__).parents[1] / "convert_from_official.py"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "model.safetensors"
            subprocess.run(
                [sys.executable, str(script), source, str(output)], check=True
            )
            digest = hashlib.sha256(output.read_bytes()).hexdigest()

        self.assertEqual(digest, EXPECTED_ARTIFACT_SHA256)


if __name__ == "__main__":
    unittest.main()
