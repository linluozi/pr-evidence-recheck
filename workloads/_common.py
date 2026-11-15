"""Shared helpers for the workload scripts.

Every workload supports two modes and prints exactly one JSON object on the
last stdout line:

``bench``
    ``--scale NAME --warmups W --samples S --seed N --out FILE``
    times one full workload call ``S`` times after ``W`` untimed warmups and
    reports raw per-call nanosecond samples plus an output checksum.

``diff``
    ``--cases N --seed S --out FILE``
    runs ``N`` independently generated inputs and returns a map
    ``{sha256(input_bytes): sha256(output_bytes)}``. The driver intersects the
    two maps and counts *unique* inputs, so re-running one frozen input cannot
    inflate coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canon(obj) -> bytes:
    """Stable byte image of a Python value for hashing."""
    return repr(obj).encode("utf-8", "backslashreplace")


def parse_common(prog: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog=prog)
    ap.add_argument("--mode", choices=("bench", "diff"), required=True)
    ap.add_argument("--scale", default="small")
    ap.add_argument("--warmups", type=int, default=3)
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--cases", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=20261116)
    ap.add_argument("--out", required=True)
    return ap.parse_args()


def emit(out_path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, sort_keys=True)
    print(json.dumps({"ok": True, "out": out_path}))


def timed_bench(make_case, warmups: int, samples: int, digest=None) -> dict:
    """Time ``make_case()`` with perf_counter_ns; warmups are not recorded."""
    digest = digest or canon
    samples_ns = []
    checksum = None
    for _ in range(warmups):
        case = make_case()
        t0 = time.perf_counter_ns()
        result = case()
        t1 = time.perf_counter_ns()
        checksum = sha256_bytes(digest(result))
    for _ in range(samples):
        case = make_case()
        t0 = time.perf_counter_ns()
        result = case()
        t1 = time.perf_counter_ns()
        samples_ns.append(t1 - t0)
        checksum = sha256_bytes(digest(result))
    return {"samples_ns": samples_ns, "checksum": checksum}


def diff_cases(cases) -> dict:
    """``cases`` yields ``(input_bytes, output_bytes, extra)``; returns a digest map."""
    table = {}
    for item in cases:
        raw, out = item[0], item[1]
        table[sha256_bytes(raw)] = sha256_bytes(out)
    return {"unique_inputs": len(table), "cases": table}
