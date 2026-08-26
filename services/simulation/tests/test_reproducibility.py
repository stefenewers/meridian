"""Reproducibility is the product claim, so it is tested across processes, not just calls.

An in-process repeat cannot catch hash-seed nondeterminism, because the seed is fixed for
the life of the interpreter. This test shells out twice with different PYTHONHASHSEED
values, which is exactly the condition that previously produced diverging results from
identical configs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SNIPPET = "import json, sys\nsys.path.insert(0, " + repr(str(ROOT)) + ")\n" + """
from meridian.library import load_by_id
from meridian.runner import execute
cfg = load_by_id("late-night-airport-expansion")
cfg.run.replications = 2
cfg.run.horizon_minutes = 120
out = execute(cfg).to_dict()
print(json.dumps({
    "baseline": out["baseline"],
    "proposed": out["proposed"],
    "verdict": out["recommendation"]["verdict"],
    "snapshot": out["provenance"]["input_snapshot"],
}, sort_keys=True))
"""


def _run(hash_seed: str) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    proc = subprocess.run([sys.executable, "-c", SNIPPET], capture_output=True, text=True,
                          env=env, cwd=ROOT, timeout=900)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_identical_across_hash_seeds():
    a = _run("1")
    b = _run("42")
    assert a["snapshot"] == b["snapshot"]
    assert a["baseline"] == b["baseline"], "baseline arm diverged between processes"
    assert a["proposed"] == b["proposed"], "proposed arm diverged between processes"
    assert a["verdict"] == b["verdict"]
