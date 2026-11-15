"""The retract criterion.

A PR that claims a speedup is only worth keeping if the claim survives four
independent checks: the measured tree is byte-for-byte the PR head tree, the
upstream test suite is not worse than baseline, differential output is
identical, and the same-tree speedup clears the operator's declared bar on a
worst-case envelope as well as on the headline workload.

Everything here is a pure function of already-measured numbers, so the
decision is auditable and unit-testable without running a benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

KEEP = "KEEP"
RETRACT = "RETRACT"
INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class Verdict:
    decision: str
    keep_threshold: float
    worst_case_floor: float
    median_speedup: Optional[float]
    worst_speedup: Optional[float]
    gates: list = field(default_factory=list)
    reasons: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "keep_threshold": self.keep_threshold,
            "worst_case_floor": self.worst_case_floor,
            "median_speedup": self.median_speedup,
            "worst_speedup": self.worst_speedup,
            "gates": [g.as_dict() for g in self.gates],
            "reasons": list(self.reasons),
        }


def decide(
    *,
    same_tree: bool,
    tree_detail: str,
    tests_baseline_failed: Optional[int],
    tests_patched_failed: Optional[int],
    tests_baseline_passed: Optional[int],
    tests_patched_passed: Optional[int],
    diff_unique_inputs: int,
    diff_mismatches: int,
    diff_min_unique: int,
    scales: Mapping[str, Mapping[str, float]],
    keep_threshold: float,
    worst_case_floor: float,
    noise_rsd_limit: float = 0.10,
) -> Verdict:
    """Fold every measurement into KEEP / RETRACT / INCONCLUSIVE.

    ``scales`` maps scale name -> summary dict produced by
    :func:`prrecheck.stats.summarize`.
    """
    gates: list = []
    reasons: list = []

    gates.append(Gate("T1-same-tree", bool(same_tree), tree_detail))
    if not same_tree:
        reasons.append("patched tree does not hash to the PR head tree")

    base_failed = tests_baseline_failed
    patched_failed = tests_patched_failed
    if base_failed is None or patched_failed is None:
        gates.append(Gate("T2-upstream-tests", False, "tests were not run"))
        reasons.append("upstream tests were not run on both trees")
    else:
        ok = patched_failed <= base_failed
        gates.append(
            Gate(
                "T2-upstream-tests",
                ok,
                f"baseline {base_failed} failed / {tests_baseline_passed} passed; "
                f"patched {patched_failed} failed / {tests_patched_passed} passed",
            )
        )
        if not ok:
            reasons.append("patched tree fails more upstream tests than baseline")

    diff_ok = diff_unique_inputs >= diff_min_unique and diff_mismatches == 0
    gates.append(
        Gate(
            "T3-differential",
            diff_ok,
            f"{diff_unique_inputs} sha256-unique inputs (min {diff_min_unique}), "
            f"{diff_mismatches} byte-level mismatches",
        )
    )
    if diff_mismatches:
        reasons.append(f"{diff_mismatches} differential mismatches")
    elif diff_unique_inputs < diff_min_unique:
        reasons.append(
            f"only {diff_unique_inputs} unique inputs, below the {diff_min_unique} minimum"
        )

    per_scale = {name: float(s.get("speedup", 0.0)) for name, s in scales.items()}
    if per_scale:
        ordered = sorted(per_scale.values())
        n = len(ordered)
        mid = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
        worst = ordered[0]
    else:
        mid = None
        worst = None

    gates.append(
        Gate(
            "T4-median-speedup",
            mid is not None and mid >= keep_threshold,
            f"same-tree median speedup {mid if mid is None else round(mid, 4)} "
            f"vs declared bar {keep_threshold}",
        )
    )
    if mid is None:
        reasons.append("no scale produced a speedup")
    elif mid < keep_threshold:
        reasons.append(
            f"same-tree median speedup {mid:.4f}x is below the declared {keep_threshold}x bar"
        )

    gates.append(
        Gate(
            "T5-worst-case",
            worst is not None and worst >= worst_case_floor,
            f"worst scale {worst if worst is None else round(worst, 4)} "
            f"vs floor {worst_case_floor}",
        )
    )
    if worst is not None and worst < worst_case_floor:
        reasons.append(
            f"worst scale regresses to {worst:.4f}x, below the {worst_case_floor}x floor"
        )

    noisy = [
        name
        for name, s in scales.items()
        if max(float(s.get("baseline_rsd", 0.0)), float(s.get("candidate_rsd", 0.0))) > noise_rsd_limit
    ]
    gates.append(
        Gate(
            "T6-noise",
            not noisy,
            ("all scales within RSD %.0f%%" % (noise_rsd_limit * 100))
            if not noisy
            else "noisy scales: " + ", ".join(sorted(noisy)),
        )
    )

    hard_failed = [g for g in gates if g.name != "T6-noise" and not g.passed]
    if hard_failed:
        return Verdict(RETRACT, keep_threshold, worst_case_floor, mid, worst, gates, reasons)
    if noisy:
        # Measurements disagree with themselves; do not claim a win.
        reasons.append("measurement noise too high to decide")
        return Verdict(INCONCLUSIVE, keep_threshold, worst_case_floor, mid, worst, gates, reasons)
    return Verdict(KEEP, keep_threshold, worst_case_floor, mid, worst, gates, reasons)
