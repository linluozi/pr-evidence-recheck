"""Workload: ``croniter.get_next`` / ``get_prev`` over real crontab expressions.

Expressions are the ones exercised by the upstream test-suite/README for the
regex-free paths this PR changes (weekday ``#``/``L``, day-of-month ``*/n``,
6-field seconds). Random-field (``R``) expressions are deliberately excluded:
they are non-deterministic in upstream too.
"""

from __future__ import annotations

import datetime as dt
import random
import sys
from zoneinfo import ZoneInfo

from croniter import croniter

import _common

EXPRESSIONS = [
    "* * * * *",
    "*/5 * * * *",
    "0 0 * * *",
    "0 9-17 * * 1-5",
    "0 0 1 * *",
    "0 0 1 */3 *",
    "0 0 * * 5#5",
    "0 0 * * 1#1",
    "0 0 L * *",
    "0 0 * * L5",
    "0 2 * * *",
    "*/10 * * * * *",
    "0 0 1 1 *",
    "0 12 * * 0",
    "15 14 1 * *",
    "0 22 * * 1-5",
    "23 5 * * *",
    "5 4 * * 0",
    "0 0,12 * * *",
    "0 0 1 1,7 *",
    "0 0 29 2 *",
    "30 3 15 * *",
]
STEPS = {"small": 200, "medium": 800, "large": 2400, "dst": 800}
BASE = dt.datetime(2026, 3, 1, 0, 0, 0)
END = dt.datetime(2026, 6, 15, 12, 0, 0)


def _sweep(steps: int, tz_name: str | None) -> list:
    per = max(1, steps // len(EXPRESSIONS))
    tz = ZoneInfo(tz_name) if tz_name else None
    out = []
    for expr in EXPRESSIONS:
        start = BASE.replace(tzinfo=tz) if tz else BASE
        end = END.replace(tzinfo=tz) if tz else END
        it = croniter(expr, start)
        for _ in range(per):
            out.append(it.get_next(dt.datetime).isoformat())
        rev = croniter(expr, end)
        for _ in range(max(1, per // 3)):
            out.append(rev.get_prev(dt.datetime).isoformat())
    return out


def _case_at(i: int, seed: int):
    rng = random.Random(seed * 1_000_003 + i)
    expr = EXPRESSIONS[i % len(EXPRESSIONS)]
    tz_name = [None, "UTC", "America/New_York", "Europe/Berlin", "Asia/Shanghai"][i % 5]
    tz = ZoneInfo(tz_name) if tz_name else None
    start = dt.datetime(2026, 1 + (i % 12), 1 + (i % 27), i % 24, (i * 7) % 60, (i * 13) % 60)
    if tz:
        start = start.replace(tzinfo=tz)
    count = 3 + i % 40
    direction = "next" if i % 3 else "prev"
    it = croniter(expr, start)
    method = it.get_next if direction == "next" else it.get_prev
    stamps = [method(dt.datetime).isoformat() for _ in range(count)]
    raw = repr((expr, start.isoformat(), tz_name, direction, count)).encode()
    return raw, _common.canon(stamps), None


def main() -> None:
    args = _common.parse_common("wl_croniter")
    if args.mode == "bench":
        steps = STEPS[args.scale]
        tz_name = "America/New_York" if args.scale == "dst" else None
        payload = _common.timed_bench(
            lambda: (lambda: _sweep(steps, tz_name)), args.warmups, args.samples
        )
        payload.update({"scale": args.scale, "steps": steps, "tz": tz_name, "seed": args.seed})
    else:
        payload = _common.diff_cases(_case_at(i, args.seed) for i in range(args.cases))
        payload.update({"cases_requested": args.cases, "seed": args.seed})
    _common.emit(args.out, payload)


if __name__ == "__main__":
    sys.exit(main())
