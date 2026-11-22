"""
Command-line interface for the hidden-coupling detector.

Usage:
    python -m coupling_detector.cli path/to/workflows/*.yml
    python -m coupling_detector.cli path/to/workflows/ --format json
"""

import argparse
import glob
import json
import os
import sys

from .detect import detect_hidden_coupling

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
SEVERITY_COLOR = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[94m"}
RESET = "\033[0m"


def collect_workflow_files(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files.extend(sorted(glob.glob(os.path.join(p, "*.yml"))))
            files.extend(sorted(glob.glob(os.path.join(p, "*.yaml"))))
        elif "*" in p:
            files.extend(sorted(glob.glob(p)))
        else:
            files.append(p)
    return files


def print_text(findings, use_color=True):
    if not findings:
        print("No hidden coupling issues found. ✅")
        return
    findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    for f in findings:
        color = SEVERITY_COLOR.get(f.severity, "") if use_color else ""
        reset = RESET if use_color else ""
        loc = f"{f.workflow}"
        if f.job:
            loc += f" :: job '{f.job}'"
        if f.step:
            loc += f" :: step '{f.step}'"
        print(f"{color}[{f.severity}] {f.category}{reset}  {loc}")
        print(f"    {f.message}")
        if f.suggestion:
            print(f"    → suggestion: {f.suggestion}")
        print()
    counts = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda kv: SEVERITY_ORDER.get(kv[0], 9)))
    print(f"Total: {len(findings)} finding(s) — {summary}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="coupling-check",
        description="Detect hidden coupling in GitHub Actions workflow files.",
    )
    parser.add_argument("paths", nargs="+", help="workflow files, glob, or a directory")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--fail-on", choices=["HIGH", "MEDIUM", "LOW", "none"], default="none",
                         help="exit non-zero if a finding of this severity or higher is found")
    args = parser.parse_args(argv)

    files = collect_workflow_files(args.paths)
    if not files:
        print("No workflow files found for the given path(s).", file=sys.stderr)
        return 2

    findings = detect_hidden_coupling(files)

    if args.format == "json":
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    else:
        print_text(findings, use_color=not args.no_color)

    if args.fail_on != "none":
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER.get(f.severity, 9) <= threshold for f in findings):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
