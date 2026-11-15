"""Two-tree preparation and measurement.

The single non-negotiable invariant: the *patched* tree that gets measured must
hash to the exact tree object of the PR head commit. A patch that applies but
produces a different tree is not the PR's code, and any speedup measured on it
is worthless.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass


class TwoTreeError(RuntimeError):
    pass


def _run(cmd, *, cwd=None, env=None, timeout=900, check=True):
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        raise TwoTreeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout[-4000:]}")
    return proc


@dataclass
class Tree:
    path: str
    head_sha: str


def prepare_base_tree(git_url: str, base_sha: str, dest: str) -> Tree:
    """Clone one commit of ``git_url`` into ``dest`` without full history."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    _run(["git", "clone", "--depth=1", "-q", git_url, dest])
    _run(["git", "fetch", "-q", "--depth=1", "origin", base_sha], cwd=dest)
    _run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=dest)
    head = _run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
    if head != base_sha:
        raise TwoTreeError(f"base tree HEAD {head} != requested {base_sha}")
    return Tree(dest, head)


def copy_tree(src: str, dest: str) -> Tree:
    """Duplicate a prepared tree (including its .git) for patching."""
    _run(["cp", "-a", src, dest], check=True)
    head = _run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()
    return Tree(dest, head)


def apply_patch(tree: Tree, patch_path: str) -> dict:
    """Apply ``patch_path`` and return the resulting tree hash + proof fields."""
    check = _run(["git", "apply", "--check", patch_path], cwd=tree.path, check=False)
    if check.returncode != 0:
        raise TwoTreeError(f"git apply --check failed: {check.stdout[-2000:]}")
    _run(["git", "apply", patch_path], cwd=tree.path)
    _run(["git", "add", "-A"], cwd=tree.path)
    tree_sha = _run(["git", "write-tree"], cwd=tree.path).stdout.strip()
    diff_stat = _run(["git", "diff", "--stat", "HEAD"], cwd=tree.path).stdout.strip()
    return {"tree_sha": tree_sha, "diff_stat": diff_stat}


def same_tree(patched_tree_sha: str, expected_head_tree_sha: str) -> bool:
    return patched_tree_sha == expected_head_tree_sha


def runner_env(tree_path: str, pythonpath_rel: str, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    rel = "" if pythonpath_rel in ("", ".") else pythonpath_rel
    prefix = os.path.join(tree_path, rel) if rel else tree_path
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = prefix + (os.pathsep + old if old else "")
    env["PYTHONHASHSEED"] = "0"
    env.pop("PYTHONWARNINGS", None)
    if extra:
        env.update(extra)
    return env


def run_json(python: str, tree: Tree, pythonpath_rel: str, script: str,
             args: list, *, timeout=900, cwd=None) -> dict:
    """Run a workload script against ``tree`` and parse its JSON stdout."""
    env = runner_env(tree.path, pythonpath_rel)
    cmd = [python, script, *[str(a) for a in args]]
    proc = _run(cmd, cwd=cwd or tree.path, env=env, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise TwoTreeError(f"workload failed: {' '.join(cmd)}\n{proc.stdout[-4000:]}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise TwoTreeError(f"workload emitted no JSON: {proc.stdout[-2000:]}") from exc


def parse_pytest_summary(output: str, returncode: int) -> dict:
    """Pull pass/fail counts out of a pytest summary line.

    pytest omits the ``0 failed`` token on a green run, so a zero exit status is
    the authoritative signal that nothing failed.
    """
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    counts = {}
    for m in re.finditer(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)", tail):
        key = "error" if m.group(2) == "errors" else m.group(2).rstrip("s")
        counts[key] = int(m.group(1))
    if counts.get("failed") is None and returncode == 0:
        counts["failed"] = 0
    if counts.get("error") is None and returncode == 0:
        counts["error"] = 0
    return {
        "passed": counts.get("passed"),
        "failed": counts.get("failed"),
        "errors": counts.get("error"),
        "skipped": counts.get("skipped"),
        "summary_line": tail,
    }


def run_upstream_tests(python: str, tree: Tree, pythonpath_rel: str,
                       command: list, *, cwd_rel: str = ".", timeout=1800) -> dict:
    """Run a test command in ``tree``; parse the pytest summary line if present."""
    env = runner_env(tree.path, pythonpath_rel)
    cwd = os.path.join(tree.path, cwd_rel)
    started = time.perf_counter()
    proc = _run([python, *command], cwd=cwd, env=env, timeout=timeout, check=False)
    elapsed = time.perf_counter() - started
    out = proc.stdout
    summary = parse_pytest_summary(out, proc.returncode)
    return {
        "command": " ".join([python, *command]),
        "cwd_rel": cwd_rel,
        "exit_code": proc.returncode,
        "elapsed_s": round(elapsed, 3),
        **summary,
        "tail": "\n".join(out.strip().splitlines()[-25:]),
    }
