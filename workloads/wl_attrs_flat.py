"""Workload: ``attrs.asdict`` over a *flat* corpus of many 20-field objects.

This is the second attrs corpus shape. The nested PyPI-shape corpus in
``wl_attrs`` has expensive collection work per node; this one is the shape the
PR's "skip ``fields()`` and keyword plumbing per node" change should help most:
many small, wide attrs objects with no nested attrs. It exists so a zero result
cannot be blamed on one unfavourable corpus.
"""

from __future__ import annotations

import sys

import attrs

import _common
import wl_attrs

TARGET_ITEMS = {"small": 2000, "medium": 8000, "large": 32000}
FIELDS = 20


@attrs.define
class Flat:
    f00: int
    f01: str
    f02: float
    f03: bool
    f04: int
    f05: str
    f06: float
    f07: bool
    f08: int
    f09: str
    f10: float
    f11: bool
    f12: int
    f13: str
    f14: float
    f15: bool
    f16: int
    f17: str
    f18: float
    f19: bool


@attrs.define
class Bundle:
    items: list


def build(n: int) -> Bundle:
    return Bundle(
        items=[
            Flat(
                i, f"s{i}", i * 1.5, bool(i % 2), -i, "x" * 8, i / 7, i % 3 == 0,
                i, f"t{i}", i * 2.5, i % 5 == 0, i, "y" * 4, i / 11, i % 7 == 0,
                i, f"u{i}", i * 3.5, i % 11 == 0,
            )
            for i in range(n)
        ]
    )


def main() -> None:
    args = _common.parse_common("wl_attrs_flat")
    if args.mode == "bench":
        n = TARGET_ITEMS[args.scale]
        bundle = build(n)
        payload = _common.timed_bench(
            lambda: (lambda: attrs.asdict(bundle)), args.warmups, args.samples
        )
        payload.update({"scale": args.scale, "items": n, "fields": FIELDS, "seed": args.seed})
    else:
        payload = _common.diff_cases(wl_attrs.case_at(i, args.seed) for i in range(args.cases))
        payload.update({"cases_requested": args.cases, "seed": args.seed})
    _common.emit(args.out, payload)


if __name__ == "__main__":
    sys.exit(main())
