# pr-evidence-recheck

**Re-measure an already-open pull request's speedup claim on the PR's own git
tree, and emit a KEEP / RETRACT certificate that anyone can re-verify offline.**

Many "X is 1.9x faster" claims are measured against a *different* build than
the patched one — a PyPI wheel, a released tag, a stale checkout — and the
result is re-advertised as the PR's speedup. This tool removes that ambiguity
mechanically: it clones the PR's base commit, applies the PR's own diff, and
refuses to accept the measurement unless the resulting git tree hash equals the
tree hash of the PR head commit reported by the GitHub API. Only then does it
report a same-tree number, run the upstream test suite on both trees, run a
sha256-unique differential, and fold everything into a verdict against
thresholds declared up front.

Upstream: none

This repository is original work; it is not a fork and patches nothing. It is
also **not** an `-opt-lab`: it does not claim a speedup of its own. It contains
three verbatim third-party PR diffs under `patches/` as the inputs it
re-measures, and publishes the resulting verdicts as evidence.

**Quick start / 怎么跑:**
`python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/python -m unittest discover -s tests -v`,
then `python -m prrecheck verify evidence/croniter-298.json` to re-check a
published verdict offline. Full re-run commands and the raw evidence tables are
in *Reproduce* and *Results* below.

## 本轮创新

**B 档：把「已开 PR 的 baseline / patched 是否同树」做成可执行的撤回判据。**
以前的台账条目各自解决一个问题——`hunk-ablation` 做逐 hunk 归因、
`perfclaim-guard` 在运行时拒绝假声明、`caseproof` 做用例数内容寻址、`crossover-cert`
做规模交叉点——但没有任何一条把「一个**已经打开的** PR 所声称的加速比，是否站在
同一棵 git 树（base 提交 + 该 PR 自己的 diff）上，并且是否达到事前声明的门槛」
做成独立复核器。本仓库给三者都做了同树复算，并给出 `KEEP`/`RETRACT` 判决：
`croniter#298` 复现（2.12x，保留），`attrs#1660`（0.985x）与
`jsonpatch#274`（1.006x）未达 1.30x 门槛（撤回）。和谁不一样：不复述 PR 正文的
数字，也不靠"换一个上游再跑一遍"；结论全部由本机真实运行得到，且每个证书都能
离线复算摘要、逐样本重算中位数。

## Results — claim vs. same-tree re-measurement

Every number below was produced on this machine by `prrecheck run` and is stored
verbatim in `evidence/<spec>.json` (raw per-call samples and raw differential
tables in `evidence/raw/<spec>/*.json`). "Same-tree" means the
measured patched tree hash equals the PR head tree hash, proven by `git
write-tree`, not asserted.

| PR | PR claims | scale 1 | scale 2 | scale 3 | scale 4 | same-tree median | worst scale | verdict |
|---|---|---|---|---|---|---|---|---|
| [`attrs#1660`](https://github.com/python-attrs/attrs/pull/1660) — nested corpus | **1.98x** (1.96–2.06) | small 0.985x | medium 1.023x | large 0.965x | — | **0.985x** | 0.965x | **RETRACT** |
| [`attrs#1660`](https://github.com/python-attrs/attrs/pull/1660) — flat 20-field corpus | same claim | small 0.988x | medium 0.985x | large 0.982x | — | **0.985x** | 0.982x | **RETRACT** |
| [`croniter#298`](https://github.com/pallets-eco/croniter/pull/298) | **2.29x** (1.57–3.26) | small 1.988x | medium 2.243x | large 2.368x | dst 1.897x | **2.116x** | 1.897x | **KEEP** |
| [`jsonpatch#274`](https://github.com/stefankoegl/python-json-patch/pull/274) | **1.33x** (1.02–1.40) | small 1.028x | medium 1.014x | large 0.997x | near-identical 0.997x | **1.006x** | 0.997x | **RETRACT** |

Declared thresholds for all three runs: `--keep-threshold 1.30`,
`--worst-case-floor 1.00`, `diff_min_unique 1000`. They are stored in each spec
file *before* the run, so the verdict is not tuned after seeing the numbers.

What this means, stated carefully:

* **croniter#298 reproduces.** 2000 sha256-unique differential cases,
  byte-identical output, 267 upstream tests green on both trees, 1.90–2.37x on
  four workloads. This PR's headline claim survives an independent same-tree
  re-measurement.
* **attrs#1660 does not reproduce on the declared corpora.** The PR body
  advertises 1.98x from "8 live PyPI JSON documents (12,831,175 bytes) loaded
  into nested attrs models". Those documents are not redistributable here, so
  this recheck uses two deterministic reconstructions: the same document shape
  (`info`/`releases`/`urls`/`meta`, 599–9,601 model objects) and a second,
  deliberately PR-favourable shape — 2,000 / 8,000 / 32,000 flat attrs objects
  with 20 scalar fields each, where the removed per-node `fields()` call and
  keyword plumbing should matter most. Both give the same answer:
  0.96–1.02x and 0.988/0.985/0.982x respectively, i.e. the patched tree is
  **not** faster (the flat corpus is quiet: RSD ≤ 2.5%, so gate T6 passes and
  the retract rests on T4/T5 alone, not on noise). This is a non-reproduction
  on our declared workloads, not a proof about the PR author's private corpus;
  but it does mean the advertised number cannot be used as the PR's
  justification, and the retract criterion fires.
* **jsonpatch#274 also retracts.** The PR's own honest negative (1.02x on
  near-identical inputs) turns out to be the *general* case on our service-model
  corpus: 0.997–1.028x across four scales, median 1.006x. The fast path is
  real but its payoff is proportional to added/removed subtrees, which this
  corpus does not have in bulk.

## Gates (per PR)

`T1`..`T6` are the tool's declared gates; every one has a copy-paste command in
*Reproduce* below.

| gate | attrs#1660 | croniter#298 | jsonpatch#274 |
|---|---|---|---|
| T1 same-tree (patched tree == PR head tree) | ✅ `1655912b…` | ✅ `7ae0ac41…` | ✅ `9b281368…` |
| T2 upstream tests | ✅ 1401 passed / 0 failed (both trees) | ✅ 267 passed / 0 failed (both trees) | ✅ 345 passed / 1 failed (identical failure on **both** trees: `DocumentationTests::test_tutorial`) |
| T3 differential (sha256-unique, byte-identical) | ✅ 2000 unique / 0 mismatch | ✅ 2000 unique / 0 mismatch | ✅ 1823 unique / 0 mismatch, reapply 2000/2000 (`==`) |
| T4 same-tree median ≥ 1.30x | ❌ 0.985x | ✅ 2.116x | ❌ 1.006x |
| T5 worst scale ≥ 1.00x | ❌ 0.965x | ✅ 1.897x | ❌ 0.997x |
| T6 noise (RSD ≤ 10%) | ❌ large, medium (nested) / ✅ (flat) | ✅ | ✅ |
| **verdict** | **RETRACT** (both corpora) | **KEEP** | **RETRACT** |

Differential coverage is content-addressed on the *input*: `unique_inputs` is
the number of distinct sha256 digests of generated inputs, so repeating one
frozen input cannot inflate the count (`wl_jsonpatch` produces 2000 cases of
which 1823 are distinct; `wl_attrs`/`wl_croniter` produce 2000 distinct).

## Reproduce

```bash
# 1. install the tool (stdlib only, no runtime dependencies)
python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/python -m unittest discover -s tests -v

# 2. verify a published certificate's digest offline (no network)
.venv/bin/python -m prrecheck verify evidence/croniter-298.json

# 3. re-run the whole recheck for one PR (needs git + an interpreter with the
#    upstream test deps installed; see Environment). --git-url is only needed
#    when GitHub HTTPS is blocked.
.venv/bin/python -m prrecheck run specs/croniter-298.json \
    --workspace /tmp/prr --raw-dir /tmp/prr-raw --out /tmp/croniter-298.json \
    --python "$(command -v python3)" --reps 3 \
    --git-url git@github.com:pallets-eco/croniter.git
```

The specs shipped here use `git@github-linluozi:<owner>/<repo>.git`, a local
SSH alias, because `github.com:443` is blocked in the authoring environment;
substitute `git@github.com:<owner>/<repo>.git` anywhere else.

To recompute the numbers from the raw samples alone (no benchmark re-run):

```bash
.venv/bin/python - <<'EOF'
import json; from prrecheck import stats
c = json.load(open("evidence/croniter-298.json"))
for name, s in c["scales"].items():
    print(name, round(stats.speedup(s["baseline_ns"], s["candidate_ns"]), 4))
EOF
```

## Environment

* CPU: AMD EPYC 7K62 48-Core Processor (4 vCPU), 3.7 GiB RAM, Ubuntu 24.04
* Python: 3.12.3 (`/usr/bin/python3.12`); no other interpreter is installed on
  this machine, so no 3.10/3.11 cross-run is possible and none is claimed.
* Node: n/a (Python-only tool)
* Test deps used in the reference runs: `pytest`, `hypothesis`,
  `pytest-subtests`, `cloudpickle`, `pympler`, `python-dateutil`, `pytz`,
  `jsonpointer`
* Timing: `time.perf_counter_ns()`, 3 warmups (untimed) + 5 timed samples per
  launch, 3 alternating base/patched launches per scale (15 samples per side),
  fixed seed 20261116, `PYTHONHASHSEED=0`.
* Reported statistic: median with p25/p75; 2000-iteration percentile bootstrap
  95% CI on the median ratio.
* Noise disclosure: attrs `large` RSD is 11.6%/13.8% and `medium` 14.2% (the
  21 ms workload includes allocator and page-fault effects); those scales are
  flagged by gate T6 and the attrs verdict would be INCONCLUSIVE on T6 alone,
  but it is RETRACT on T4/T5 regardless.

## Layout

```
prrecheck/          the tool: stats, verdict, certificate, two-tree harness, CLI
workloads/          three benchmark/differential workloads (attrs, croniter, jsonpatch)
specs/              per-PR spec: base/head/tree SHA, thresholds, corpus notes
patches/            verbatim PR diffs (third-party, licence of each upstream applies)
evidence/           certificates + raw samples + raw differential tables
tests/              56 unittest cases over stats, verdict logic, certificates, tree proof
```

## Limits (read before trusting a verdict)

* A RETRACT verdict is a statement about *this tool's declared workload and
  thresholds*, not proof that a patch is worthless. The specs encode the
  workload; a different corpus can give a different median. The point is that
  the workload and the bar are fixed before the numbers are read.
* Synthetic corpora are reconstructions of the shape described in each PR body
  (PyPI-document shape for attrs, service-model shape for jsonpatch). The PRs'
  original real-file corpora are not committed here.
* The certificates are self-authenticating (canonical-JSON sha256), which
  detects edits but not a malicious producer.

## Licence

MIT for this tool (see `LICENSE`). The files under `patches/` are verbatim
third-party diffs and remain under their upstream licences (attrs: MIT;
croniter: MIT; python-json-patch: BSD-3-Clause).
