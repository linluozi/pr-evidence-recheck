"""Command line interface for the PR evidence recheck.

    python -m prrecheck run specs/attrs-1660.json --workspace /tmp/prr --out evidence/attrs-1660.json
    python -m prrecheck verify evidence/attrs-1660.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shutil
import subprocess
import sys

from . import certificate, stats, twotree, verdict as verdict_mod

REQUIRED_SPEC_KEYS = (
    "name", "upstream", "pr", "git_url", "base_sha", "head_sha", "head_tree_sha",
    "patch", "pythonpath_rel", "workload", "scales", "upstream_tests",
    "keep_threshold", "worst_case_floor",
)


def load_spec(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    missing = [k for k in REQUIRED_SPEC_KEYS if k not in spec]
    if missing:
        raise ValueError(f"spec {path} missing keys: {missing}")
    if not spec["scales"]:
        raise ValueError("spec must declare at least one scale")
    if spec["worst_case_floor"] > spec["keep_threshold"]:
        raise ValueError("worst_case_floor must not exceed keep_threshold")
    return spec


def environment() -> dict:
    model = "unknown"
    mem_kb = None
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    break
        with open("/proc/meminfo", encoding="utf-8") as fh:
            mem_kb = int(fh.readline().split()[1])
    except OSError:
        pass
    return {
        "cpu": model,
        "mem_total_kb": mem_kb,
        "python": sys.version.split()[0],
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "node": _try(["node", "-v"]),
    }


def _try(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=20).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _diff_maps(a: dict, b: dict) -> dict:
    keys_a, keys_b = set(a["cases"]), set(b["cases"])
    common = keys_a & keys_b
    mismatches = sum(1 for k in common if a["cases"][k] != b["cases"][k])
    return {
        "unique_inputs_baseline": len(keys_a),
        "unique_inputs_patched": len(keys_b),
        "unique_inputs_common": len(common),
        "mismatches": mismatches,
        "pairs_only_in_baseline": len(keys_a - keys_b),
        "pairs_only_in_patched": len(keys_b - keys_a),
        "reapply_equal": b.get("reapply_equal"),
        "reapply_canonical": b.get("reapply_canonical"),
    }


def run_spec(spec: dict, workspace: str, out_path: str, python: str,
             raw_dir: str, reps: int = 3, git_url: str | None = None) -> dict:
    root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    name = spec["name"]
    work = os.path.join(workspace, name)
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    raw_dir = os.path.abspath(os.path.join(raw_dir, name))
    os.makedirs(raw_dir, exist_ok=True)

    base = twotree.prepare_base_tree(git_url or spec["git_url"], spec["base_sha"],
                                     os.path.join(work, "base"))
    patched = twotree.copy_tree(base.path, os.path.join(work, "patched"))
    proof = twotree.apply_patch(patched, os.path.join(root, spec["patch"]))
    same = twotree.same_tree(proof["tree_sha"], spec["head_tree_sha"])

    with open(os.path.join(root, spec["patch"]), "rb") as fh:
        patch_sha = certificate.sha256_bytes(fh.read())

    tests = {}
    for label, tree in (("baseline", base), ("patched", patched)):
        tests[label] = twotree.run_upstream_tests(
            python, tree, spec["pythonpath_rel"], spec["upstream_tests"]["command"],
            cwd_rel=spec["upstream_tests"].get("cwd_rel", "."),
        )

    diff = {"baseline": None, "patched": None}
    for label, tree in (("baseline", base), ("patched", patched)):
        out = os.path.join(raw_dir, f"diff-{label}.json")
        twotree.run_json(
            python, tree, spec["pythonpath_rel"],
            os.path.join(root, spec["workload"]),
            ["--mode", "diff", "--cases", spec.get("diff_cases", 1500),
             "--seed", spec.get("seed", 20261116), "--out", out],
        )
        with open(out, encoding="utf-8") as fh:
            diff[label] = json.load(fh)
    diff_summary = _diff_maps(diff["baseline"], diff["patched"])

    scales = {}
    for scale in spec["scales"]:
        raw_base, raw_cand = [], []
        for rep in range(reps):
            for label, tree, bucket in (("baseline", base, raw_base),
                                        ("patched", patched, raw_cand)):
                out = os.path.join(raw_dir, f"{scale}-{label}-r{rep}.json")
                twotree.run_json(
                    python, tree, spec["pythonpath_rel"],
                    os.path.join(root, spec["workload"]),
                    ["--mode", "bench", "--scale", scale,
                     "--warmups", spec.get("warmups", 3),
                     "--samples", spec.get("samples", 5),
                     "--seed", spec.get("seed", 20261116), "--out", out],
                )
                with open(out, encoding="utf-8") as fh:
                    payload = json.load(fh)
                payload["rep"] = rep
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, sort_keys=True)
                bucket.extend(payload["samples_ns"])
        summary = stats.summarize(raw_base, raw_cand, ci_iterations=spec.get("ci_iterations", 2000),
                                  seed=spec.get("seed", 20261116))
        scales[scale] = {
            "baseline_ns": raw_base,
            "candidate_ns": raw_cand,
            "summary": summary,
        }

    verdict = verdict_mod.decide(
        same_tree=same,
        tree_detail=(f"patched tree {proof['tree_sha']} vs PR head tree "
                     f"{spec['head_tree_sha']}"),
        tests_baseline_failed=tests["baseline"]["failed"],
        tests_patched_failed=tests["patched"]["failed"],
        tests_baseline_passed=tests["baseline"]["passed"],
        tests_patched_passed=tests["patched"]["passed"],
        diff_unique_inputs=diff_summary["unique_inputs_common"],
        diff_mismatches=diff_summary["mismatches"],
        diff_min_unique=spec.get("diff_min_unique", 1000),
        scales={k: v["summary"] for k, v in scales.items()},
        keep_threshold=spec["keep_threshold"],
        worst_case_floor=spec["worst_case_floor"],
    )

    body = {
        "tool": "pr-evidence-recheck",
        "tool_version": "1.0.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "spec": spec,
        "patch_sha256": patch_sha,
        "trees": {
            "base_sha": spec["base_sha"],
            "patched_tree_sha": proof["tree_sha"],
            "expected_head_tree_sha": spec["head_tree_sha"],
            "same_tree": same,
            "diff_stat": proof["diff_stat"],
        },
        "upstream_tests": tests,
        "differential": diff_summary,
        "scales": scales,
        "verdict": verdict.as_dict(),
        "environment": environment(),
        "reps": reps,
    }
    cert = certificate.make_certificate(body)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(certificate.dumps_certificate(cert))
    return cert


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prrecheck")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="re-run one spec and emit a certificate")
    r.add_argument("spec")
    r.add_argument("--workspace", default="/tmp/prr-workspace")
    r.add_argument("--raw-dir", default="/tmp/prr-raw")
    r.add_argument("--out", required=True)
    r.add_argument("--python", default=sys.executable)
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--git-url", default=None,
                   help="override the spec's clone URL, e.g. git@github.com:owner/repo.git")

    v = sub.add_parser("verify", help="recompute a certificate digest")
    v.add_argument("certificate")

    args = ap.parse_args(argv)
    if args.cmd == "run":
        spec = load_spec(args.spec)
        cert = run_spec(spec, args.workspace, args.out, args.python, args.raw_dir,
                        args.reps, git_url=args.git_url)
        print(json.dumps({"decision": cert["verdict"]["decision"],
                          "median_speedup": cert["verdict"]["median_speedup"],
                          "same_tree": cert["trees"]["same_tree"],
                          "certificate_sha256": cert["certificate_sha256"]}, sort_keys=True))
        return 0 if cert["verdict"]["decision"] == verdict_mod.KEEP else 2
    cert = json.load(open(args.certificate, encoding="utf-8"))
    ok = certificate.verify_certificate(cert)
    print(json.dumps({"certificate": args.certificate, "valid": ok}, sort_keys=True))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
