"""Workload: ``JsonPatch.from_diff`` on realistic document pairs.

The "realistic" corpus is a synthetic-but-structured service model of the same
shape as the Botocore files the PR itself used (nested ``items`` list plus an
``index`` map). The ``near_identical`` scale reproduces the PR's own honest
negative: a large pair whose two sides differ in only a couple of places, where
the removed copies are proportional to changed subtrees rather than to size.
"""

from __future__ import annotations

import copy
import json
import random
import sys

from jsonpatch import JsonPatch

import _common

LEAVES = {"small": 120, "medium": 600, "large": 3000, "near_identical": 3000}
ITEMS_PER_LEAF = 12


def _make_doc(rng: random.Random, leaf_target: int) -> dict:
    n_items = max(2, leaf_target // ITEMS_PER_LEAF)
    items = []
    for i in range(n_items):
        items.append(
            {
                "id": i,
                "name": f"item-{i:05d}",
                "value": rng.random(),
                "tags": [f"t{j}" for j in range(3)],
                "nested": {"a": i, "b": {"c": [i, i + 1], "d": f"ünïcode-{i}"}},
            }
        )
    index = {f"k{i}": i for i in range(n_items)}
    return {
        "metadata": {"model": "svc", "version": "2016-09-15", "unicode": "日本語 ✓"},
        "items": items,
        "index": index,
    }


def _mutate(rng: random.Random, src: dict, n_changes: int) -> dict:
    dst = copy.deepcopy(src)
    items = dst["items"]
    for _ in range(n_changes):
        op = rng.randrange(3)
        if op == 0 and items:
            items.pop(rng.randrange(len(items)))
        elif op == 1:
            items.insert(
                rng.randrange(len(items) + 1),
                {"id": rng.randrange(10_000), "name": "added", "value": rng.random(),
                 "tags": ["new"], "nested": {"a": 1, "b": {"c": [1], "d": "x"}}},
            )
        else:
            idx = rng.randrange(len(items))
            items[idx] = dict(items[idx], value=rng.random(), name=f"changed-{idx}")
        dst["index"][f"m{rng.randrange(1000)}"] = rng.randrange(1000)
        dst["metadata"]["version"] = f"2016-09-{rng.randrange(10, 28)}"
    return dst


def _pair(scale: str, seed: int):
    rng = random.Random(seed)
    leaves = LEAVES[scale]
    src = _make_doc(rng, leaves)
    if scale == "near_identical":
        dst = copy.deepcopy(src)
        dst["metadata"]["version"] = "2016-11-15"
        dst["items"][0]["value"] = 42.0
    else:
        dst = _mutate(rng, src, max(4, leaves // 150))
    return src, dst


_BIG = "x" * 4096
_EDGE_CASES = [
    ({}, []),
    ({}, {"a": 1}),
    ({"a": 1}, {}),
    ({"a": True}, {"a": 1}),
    ({"a": 1}, {"a": 1.0}),
    ({"a": -0.0}, {"a": 0.0}),
    ({"ünïcode ✓": "日本語"}, {"ünïcode ✓": "中文"}),
    ({"a": "x\x00y"}, {"a": "x\x00z"}),
    ({"a": _BIG}, {"a": _BIG + "y"}),
    ([], []),
    ([1, 2, 3], [3, 2, 1]),
    ({"a": [{"b": None}]}, {"a": [{"b": [None]}]}),
]


def _rand_json(rng: random.Random, depth: int = 0):
    if depth >= 3:
        return rng.choice([None, True, False, 0, 1, -1, 1.5, "s", "日本", [], {}])
    kind = rng.randrange(4)
    if kind == 0:
        return {f"k{rng.randrange(20)}": _rand_json(rng, depth + 1) for _ in range(rng.randrange(4))}
    if kind == 1:
        return [_rand_json(rng, depth + 1) for _ in range(rng.randrange(4))]
    if kind == 2:
        return rng.randrange(-100, 100)
    return rng.choice([None, True, "text", "ünïcode"])


def _mutate_json(v, rng: random.Random):
    """One structural edit of a random JSON value (exercises move detection)."""
    if isinstance(v, dict) and v:
        out = dict(v)
        k = rng.choice(sorted(out))
        op = rng.randrange(3)
        if op == 0:
            out.pop(k)
        elif op == 1:
            out[f"new-{k}-{rng.randrange(1000)}"] = _rand_json(rng, 2)
        else:
            out[k] = _rand_json(rng, 2)
        return out
    if isinstance(v, list) and v:
        out = list(v)
        i = rng.randrange(len(out))
        op = rng.randrange(3)
        if op == 0:
            out.pop(i)
        elif op == 1:
            out.insert(i, _rand_json(rng, 2))
        else:
            out[i] = _rand_json(rng, 2)
        return out
    return _rand_json(rng)


def _case_at(i: int, seed: int):
    rng = random.Random(seed * 1_000_003 + i)
    mode = i % 3
    if mode == 2:
        a, b = _EDGE_CASES[i % len(_EDGE_CASES)]
        # The unique marker keeps the input content-addressed and unique while
        # still exercising the edge value pair itself.
        src, dst = {"marker": i, "value": a}, {"marker": i, "value": b}
    elif mode == 0:
        base = _rand_json(rng)
        src, dst = base, _mutate_json(base, rng)
    else:
        src, dst = _rand_json(rng), _rand_json(rng)
    raw = json.dumps([src, dst], sort_keys=True, ensure_ascii=False, default=repr).encode()
    patch = JsonPatch.from_diff(src, dst)
    text = patch.to_string()
    try:
        applied = patch.apply(src, in_place=False)
        # `==` is the documented "patch re-applies to dst" guarantee;
        # `canon` additionally requires key order, which jsonpatch's move
        # optimisation is free to change for dicts.
        reapply = (applied == dst, _common.canon(applied) == _common.canon(dst))
    except Exception:  # noqa: BLE001 - recorded, not raised
        reapply = (False, False)
    return raw, text.encode(), reapply


def main() -> None:
    args = _common.parse_common("wl_jsonpatch")
    if args.mode == "bench":
        src, dst = _pair(args.scale, args.seed)
        payload = _common.timed_bench(
            lambda: (lambda: JsonPatch.from_diff(src, dst)),
            args.warmups,
            args.samples,
            digest=lambda p: p.to_string().encode(),
        )
        payload.update({"scale": args.scale, "leaves": LEAVES[args.scale], "seed": args.seed})
    else:
        table = {}
        reapply_equal = 0
        reapply_canonical = 0
        for i in range(args.cases):
            raw, out, ok = _case_at(i, args.seed)
            table[_common.sha256_bytes(raw)] = _common.sha256_bytes(out)
            reapply_equal += bool(ok[0])
            reapply_canonical += bool(ok[1])
        payload = {
            "unique_inputs": len(table),
            "cases": table,
            "cases_requested": args.cases,
            "reapply_equal": reapply_equal,
            "reapply_canonical": reapply_canonical,
            "seed": args.seed,
        }
    _common.emit(args.out, payload)


if __name__ == "__main__":
    sys.exit(main())
