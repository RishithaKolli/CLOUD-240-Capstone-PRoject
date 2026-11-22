# Hidden Coupling Detector

A static analysis tool for GitHub Actions workflows that detects **implicit,
undeclared dependencies** between CI pipeline steps and jobs — coupling that
works today but silently breaks the moment someone reorders a step, splits a
job, or changes runners.

Unlike existing tools such as `actionlint` (schema/type correctness) or
`zizmor` (security), this tool focuses on **maintainability**: it flags
places where correctness depends on *implicit execution order or shared
state* rather than declared dependencies (`outputs:`, `needs:`, `env:`,
artifacts).

## What it detects

| Category | Meaning |
|---|---|
| `ENV_MUTATION` | A step reads a variable that was set implicitly via `$GITHUB_ENV` by an earlier step, instead of via a declared `outputs:` |
| `DANGLING_OUTPUT` | A step references `steps.<id>.outputs.<name>` for a step id that doesn't exist (typo, renamed, or removed step) |
| `IMPLICIT_ENV_READ` | A shell variable is read with no visible declaration anywhere (`env:`, a prior `$GITHUB_ENV` write, or a local assignment) |
| `UNDECLARED_NEEDS` | A job references `needs.<job>.*` without declaring that job in its own `needs:` list |
| `SHARED_WORKDIR_WRITE` | A file is written by one job and read by another, but the workflow doesn't use `upload-artifact`/`download-artifact` — jobs run on isolated runners and share nothing by default |

## Install

```bash
git clone <this repo>
cd coupling-detector
pip install pyyaml
```

## Usage

```bash
# scan a directory of workflow files
python3 -m coupling_detector.cli .github/workflows/

# scan specific files
python3 -m coupling_detector.cli .github/workflows/build.yml .github/workflows/deploy.yml

# machine-readable output (for CI integration / the web demo)
python3 -m coupling_detector.cli .github/workflows/ --format json

# fail CI if any HIGH severity issue is found
python3 -m coupling_detector.cli .github/workflows/ --fail-on HIGH
```

## Project structure

```
coupling_detector/
  __init__.py     public API: detect_hidden_coupling(), Finding
  extract.py       extraction primitives (env writes, output refs, shell var refs, file I/O)
  detect.py         the 3-phase algorithm (Phase 1: reference tables, Phase 2: intra-job,
                     Phase 3: inter-job filesystem coupling)
  cli.py             command-line interface

tests/
  workflows/clean.yml    control workflow — should produce 0 findings (soundness)
  workflows/seeded.yml   9 intentionally-seeded issues across all 5 categories (completeness)
  test_detector.py       automated pytest suite validating both properties

web-demo/
  index.html         self-contained, client-side interactive demo (no server needed)
```

## Validation results

Run `python3 -m pytest tests/ -v` to reproduce:

- **Soundness**: 0 findings on `clean.yml` ✅
- **Completeness**: 9/9 seeded issues detected on `seeded.yml`, across all 5 categories ✅

## Complexity

Let `n` = total steps across all workflows, `m` = average script length.

- Phase 1 & 2: `O(n·m)` — linear pass per step, constant-time hash-map lookups
- Phase 3: `O(n²)` worst case — pairwise writer/reader matching within a workflow
- Overall: `O(n·m + n²)`, effectively linear for realistic repo sizes (tens to
  low hundreds of steps)

## Limitations / future work

- Extraction is regex-based static analysis, not a full shell parser — deeply
  nested or dynamically-constructed variable names may be missed.
- Reusable workflows (`workflow_call`) and composite actions are not yet
  expanded/traced across file boundaries.
- No SARIF output yet for native GitHub code-scanning integration.

## Many files, seed and clean (for demos)

Scan many workflow files at once (files, folders or globs):

    python3 tools/seed_and_clean.py scan real_world/downloaded tests/workflows

Insert known hidden-coupling issues into every file, detect them, then clean them out again:

    python3 tools/seed_and_clean.py demo tests/workflows real_world/downloaded --out demo_output

This prints Original / Seeded / Cleaned finding counts per file and writes
`demo_output/seeded/`, `demo_output/cleaned/`, `summary.json` and `report.html`.
Files that already use upload/download-artifact do not get the shared-file finding
(by design), so they show 4 seeded issues instead of 5.

Single file: `seed <in.yml> <out.yml>` and `clean <seeded.yml> <out.yml>`.

In the web demo (`web-demo/index.html`): "Upload YAML file(s)" loads many files,
"Seed issues" / "Clean seeded" work on the editor, and "Seed → Clean all files"
shows the Original / Seeded / Cleaned table for every uploaded file.
