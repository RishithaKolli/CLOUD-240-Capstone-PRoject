# Real-World Validation Report — Review 2

**CouplingLens · Hidden Coupling Detector**

This report documents the first real-world validation of the detector,
going beyond the synthetic clean/seeded test workflows used for Review 1.

---

## Methodology

- **Corpus**: 19 real `.github/workflows/*.yml` files pulled directly from
  7 popular open-source repositories on GitHub (not written by us):
  `actions/checkout`, `actions/upload-artifact`, `pytest-dev/pytest`,
  `sveltejs/svelte`, `tiangolo/fastapi`, `vitejs/vite`, `vuejs/core`.
- **Procedure**: ran the detector, unmodified, against every file with no
  per-repo tuning. Every finding was then manually inspected against the
  original source to classify it as a true or false positive.

This corpus is intentionally independent of the synthetic `clean.yml` /
`seeded.yml` test cases — it tests whether the detector generalizes to code
we didn't design around.

---

## Round 1 results (before fixes)

| Metric | Value |
|---|---|
| Files analyzed | 19 |
| Files with 0 findings | 16 / 19 (84%) |
| Total findings | 16 |
| Findings by category | `IMPLICIT_ENV_READ`: 16 — all other 4 categories: 0 |
| Total analysis time | 118 ms (19 files) |
| Avg time / file | 6.2 ms |

**Manual review of all 16 findings found 0 true positives** — 100% false
positive rate, concentrated entirely in one detector. Root-cause analysis
traced every finding to one of three shell-syntax patterns the regex
extraction did not originally account for:

| Root cause | Files affected | Findings |
|---|---|---|
| PowerShell assignment (`$var = value`) misread as an undeclared read | `actions/upload-artifact` | 14 |
| Bash `read -r -d '' file` loop variable not recognized as a declaration | `tiangolo/fastapi` | 1 |
| PowerShell `$env:VAR` access syntax misparsed as a bash variable | `vitejs/vite` | 1 |

Note what this table also shows: the other four detectors
(`ENV_MUTATION`, `DANGLING_OUTPUT`, `UNDECLARED_NEEDS`,
`SHARED_WORKDIR_WRITE`) produced **zero false positives** across all 19
real files in this round — the false-positive problem was fully isolated
to `IMPLICIT_ENV_READ`.

---

## Fix applied

Two of the three root causes are unambiguous shell-syntax gaps and were
fixed directly in the extraction layer:

1. **Shell-aware suppression** — the detector now resolves each step's
   effective shell (`step.shell` → `job.defaults.run.shell` →
   `workflow.defaults.run.shell`, matching GitHub Actions' own precedence
   rules) and skips `IMPLICIT_ENV_READ` for `pwsh` / `powershell` / `cmd`
   steps, since the regex extraction targets bash syntax specifically.
2. **`read` loop variables** — `extract_local_assignments` now also
   recognizes bash `read -r -d '' varname` as declaring `varname`, covering
   the common "iterate over null-delimited output" idiom.

## Round 2 results (after fixes)

| Metric | Round 1 | Round 2 |
|---|---|---|
| Total findings | 16 | **1** |
| False positives eliminated | — | 15 / 16 (94%) |
| Avg time / file | 6.2 ms | 5.9 ms (no meaningful change) |

**Regression check**: re-ran the full existing test suite (soundness on
`clean.yml`, completeness on `seeded.yml`, all 5 categories) — all pass,
0 findings on clean, 9/9 seeded issues still caught. The fix did not
weaken detection on the original test cases.

---

## Remaining known limitation (documented, not fixed)

One finding remains, in `vitejs/vite`'s CI workflow: a step guarded by
`if: runner.os == 'Windows'` with no explicit `shell:` field. GitHub
Actions defaults Windows runners to PowerShell when no shell is declared —
but the actual OS is only known at runtime, via a matrix variable
(`runs-on: ${{ matrix.os }}`). Detecting this would require inferring the
runner OS from a conditional expression, which is a meaningfully deeper
static-analysis problem than the other two fixes.

This is intentionally left as a documented limitation rather than patched
with a fragile heuristic — it's a clean illustration of exactly where
regex-based static analysis reaches its limit, and directly motivates the
AST-based parsing already flagged as future work (Risk R1 in the risk
register).

---

## Takeaways for Review 2

- The detector generalizes beyond synthetic test cases: 0 false positives
  on 4 of 5 categories, on real code, with no tuning.
- Real-world testing surfaced a genuine limitation invisible in synthetic
  tests — the detector implicitly assumed bash throughout — and that
  limitation has now been diagnosed, fixed for the common cases, and
  regression-tested.
- One edge case remains, is understood, and is explicitly scoped as future
  work rather than silently ignored.

---

## Supplementary Mac Benchmark (Post-Fix)

A supplementary benchmark was executed on the final local Mac environment
using `real_world/run_corpus_mac.py`.

### Machine configuration

| Component | Configuration |
|---|---|
| Computer | MacBook Air (Mac15,12) |
| Processor | Apple M3 |
| CPU cores | 8 (4 performance, 4 efficiency) |
| Memory | 16 GB |
| Architecture | ARM64 |
| Operating system | macOS 27.2.1 |
| Python | 3.14.2 |

### Benchmark results

| Metric | Measured result |
|---|---:|
| Workflow files analyzed | 19 |
| Open-source repositories | 7 |
| Total findings | 1 |
| Sum of per-file timings | 63.424 ms |
| Wall-clock total | 63.515 ms |
| Average per file | 3.338 ms |

The benchmark processed all 19 workflow files and reported one
`IMPLICIT_ENV_READ` finding in the Vite workflow.

These figures represent one supplementary post-fix benchmark run on the
MacBook Air. They are not repeated-trial averages and are not presented
as replacements for the historical Round 1 and Round 2 measurements.

### Raw timing evidence

The benchmark script is `real_world/run_corpus_mac.py`.
Its machine-specific results, including individual file timings, are saved
in `real_world/mac_benchmark_results.json`.

The previously retained `real_world/per_file_summary.json` contains
19 individual timings totaling 174.02 ms (average 9.16 ms per file).
These do not reproduce the historical timing figures above. Therefore,
the historical Round 1 and Round 2 timing figures should be treated as
previously reported results, not independently verified by that file.
