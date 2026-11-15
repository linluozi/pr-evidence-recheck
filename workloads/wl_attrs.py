"""Workload: ``attrs.asdict`` over a nested attrs model.

The corpus reconstructs the shape of the PR's own "8 live PyPI JSON documents"
corpus (info / releases / urls / meta) with a deterministic generator, because
redistributing the 12.8 MB of upstream PyPI JSON is not appropriate here. Node
counts are reported in the certificate so the corpus size is auditable.
"""

from __future__ import annotations

import random
import sys

import attrs
import attr

import _common

TARGET_NODES = {"small": 600, "medium": 2400, "large": 9600}
RELEASES_PER_PROJECT = 12


@attrs.define
class Digest:
    md5: str
    sha256: str


@attrs.define
class Release:
    filename: str
    size: int
    upload_time: str
    digests: Digest
    yanked: bool


@attrs.define
class Info:
    name: str
    version: str
    summary: str
    keywords: tuple
    classifiers: tuple
    requires: tuple


@attrs.define
class Project:
    info: Info
    releases: list
    urls: list
    meta: dict


@attrs.define
class Bundle:
    """Top-level document, mirroring `asdict()` over a loaded JSON payload."""

    projects: list
    source: str


def _digest(rng: random.Random) -> Digest:
    return Digest(f"{rng.getrandbits(64):016x}", f"{rng.getrandbits(128):032x}")


def _project(idx: int, rng: random.Random) -> Project:
    name = f"project-{idx:05d}"
    releases = []
    for j in range(RELEASES_PER_PROJECT):
        releases.append(
            Release(
                filename=f"{name}-{j}.tar.gz",
                size=rng.randrange(1_000, 5_000_000),
                upload_time=f"2026-0{(j % 9) + 1}-1{j % 10}T0{j % 10}:00:00",
                digests=_digest(rng),
                yanked=bool(j % 7 == 0),
            )
        )
    return Project(
        info=Info(
            name=name,
            version=f"{1 + idx % 5}.{idx % 100}.{idx % 10}",
            summary=f"summary for {name} — non-ASCII ✓ ünïcode {idx}",
            keywords=("alpha", "beta", f"kw{idx}"),
            classifiers=tuple(f"Class :: {k}" for k in range(6)),
            requires=("dep-a>=1", "dep-b<3") if idx % 2 else (),
        ),
        releases=releases,
        urls=[{"url": f"https://files.example/{name}/{j}", "packagetype": "sdist"} for j in range(4)],
        meta={"downloads": {"last_day": rng.randrange(10_000)}, "yanked": False, "tags": {f"t{j}" for j in range(4)}},
    )


def build_corpus(seed: int, target_nodes: int) -> list:
    rng = random.Random(seed)
    per_project = 2 + 2 * RELEASES_PER_PROJECT
    n_projects = max(1, target_nodes // per_project)
    return [_project(i, rng) for i in range(n_projects)]


def node_count(corpus: list) -> int:
    return 1 + len(corpus) * (2 + 2 * RELEASES_PER_PROJECT)


def _edge_instance(kind: int, rng: random.Random, idx: int):
    """Small instances covering the odd values ``asdict`` must preserve."""
    nan = float("nan")

    @attrs.define
    class Edge:
        a: object
        b: object
        c: object
        d: object
        e: object

    payloads = [
        (nan, float("inf"), -0.0, None),
        (b"\x00\xff", "日本語テキスト", (), []),
        ({("k", 1): "tuple-key"}, {"nested": {"deep": [1, 2, {"x": None}]}}, set(), frozenset()),
        (True, 1, 1.0, "1"),
        ("", [], {}, ()),
        (rng.random(), rng.randrange(-10**9, 10**9), "\x00", "ünïcode ✓"),
    ]
    return Edge(*payloads[kind % len(payloads)], e=f"edge-{idx}")


def case_at(i: int, seed: int):
    """One deterministic differential case: (input_bytes, output_bytes, reapply)."""
    rng = random.Random(seed * 1_000_003 + i)
    kind = i % 3
    if kind == 0:
        obj = _edge_instance(i, rng, i)
        opts = {}
    elif kind == 1:
        obj = _project(i, rng)
        opts = {}
    else:
        obj = _project(i, rng)
        opts = {"retain_collection_types": i % 2 == 0}
        if i % 3 == 0:
            opts["filter"] = lambda a, v: a.name != "meta"
        if i % 5 == 0:
            opts["dict_factory"] = lambda items=(): {
                "|".join(str(k) for k, _ in items): v for k, v in items
            }
        if i % 7 == 0:
            opts["value_serializer"] = lambda inst, field, value: (
                field.name if field is not None else None,
                value,
            )
    raw = _common.canon(obj) + _common.canon(sorted(opts.keys()))
    # `attrs.asdict` only exposes the default options; `attr.asdict` is the
    # same implementation and lets the case exercise the non-default paths.
    out = attr.asdict(obj, **opts)
    return raw, _common.canon(out), None


def main() -> None:
    args = _common.parse_common("wl_attrs")
    if args.mode == "bench":
        corpus = build_corpus(args.seed, TARGET_NODES[args.scale])
        bundle = Bundle(projects=corpus, source=f"pypi-shape-{args.scale}")
        payload = _common.timed_bench(
            lambda: (lambda: attrs.asdict(bundle)), args.warmups, args.samples
        )
        payload.update({"scale": args.scale, "nodes": node_count(corpus), "seed": args.seed})
    else:
        payload = _common.diff_cases(case_at(i, args.seed) for i in range(args.cases))
        payload.update({"cases_requested": args.cases, "seed": args.seed})
    _common.emit(args.out, payload)


if __name__ == "__main__":
    sys.exit(main())
