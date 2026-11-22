"""
Batch scan + seed + clean demo for the hidden-coupling detector.

For every workflow YAML you give it, the tool:
  1. SCAN     the original file                    -> findings (original)
  2. SEED     inject known hidden-coupling steps   -> findings (seeded)
  3. CLEAN    remove exactly what was injected     -> findings (cleaned)

Seeded steps are named "[SEEDED] ..." and the extra job is named "seeded_consumer",
so cleaning removes only what seeding added. The seeded issues are real patterns the
detector looks for; the point of the demo is to show detection appearing after seeding
and disappearing after cleaning, on ANY yaml file you drop in.

Usage:
    python tools/seed_and_clean.py scan  <files|dirs|globs>              # many files, one table
    python tools/seed_and_clean.py seed  <in.yml> <out.yml>
    python tools/seed_and_clean.py clean <seeded.yml> <out.yml>
    python tools/seed_and_clean.py demo  <files|dirs|globs> [--out OUTDIR]   # scan+seed+clean for all
"""
import argparse
import glob
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from coupling_detector.detect import detect_hidden_coupling  # noqa: E402

TAG = "[SEEDED]"
SEED_JOB = "seeded_consumer"


# ---------------------------------------------------------------- YAML helpers
class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps the GitHub Actions key `on:` as the string 'on'."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:bool"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))


def load_yaml(path):
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=_Loader)


def dump_yaml(doc, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(doc, fh, sort_keys=False, default_flow_style=False, width=200, allow_unicode=True)


def collect(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += sorted(glob.glob(os.path.join(p, "*.yml")) + glob.glob(os.path.join(p, "*.yaml")))
        elif any(c in p for c in "*?["):
            files += sorted(glob.glob(p))
        else:
            files.append(p)
    return files


# ---------------------------------------------------------------- seed / clean
def _seed_steps(first_job):
    return [
        {"name": f"{TAG} export variable", "id": "seeded_setup", "shell": "bash",
         "run": 'echo "SEEDED_BUILD_ID=abc123" >> $GITHUB_ENV'},
        {"name": f"{TAG} read exported variable", "shell": "bash",
         "run": 'echo "build $SEEDED_BUILD_ID"'},
        {"name": f"{TAG} reference missing step", "shell": "bash",
         "run": 'echo "${{ steps.seeded_missing.outputs.value }}"'},
        {"name": f"{TAG} undeclared variable", "shell": "bash",
         "run": 'echo "key $SEEDED_SECRET_KEY"'},
        {"name": f"{TAG} write shared file", "shell": "bash",
         "run": "echo data > seeded_shared.txt"},
    ]


def seed(doc):
    """Return a copy of doc with hidden-coupling steps/job injected, or None if no job has steps."""
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return None
    first = next((k for k, j in jobs.items() if isinstance(j, dict) and isinstance(j.get("steps"), list)), None)
    if first is None:
        return None
    jobs[first]["steps"] = list(jobs[first]["steps"]) + _seed_steps(first)
    jobs[SEED_JOB] = {
        "runs-on": "ubuntu-latest",
        "steps": [
            {"name": f"{TAG} read file from another job", "shell": "bash", "run": "cat seeded_shared.txt"},
            {"name": f"{TAG} read output of undeclared needs", "shell": "bash",
             "run": 'echo "${{ needs.%s.outputs.result }}"' % first},
        ],
    }
    return doc


def clean(doc):
    """Remove everything seed() added; leave the original content untouched."""
    jobs = doc.get("jobs", {})
    jobs.pop(SEED_JOB, None)
    for j in jobs.values():
        if isinstance(j, dict) and isinstance(j.get("steps"), list):
            j["steps"] = [s for s in j["steps"]
                          if not (isinstance(s, dict) and str(s.get("name", "")).startswith(TAG))]
    return doc


# ---------------------------------------------------------------- scanning
def scan(path):
    return detect_hidden_coupling([path])


def _sev(findings):
    c = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        c[f.severity] = c.get(f.severity, 0) + 1
    return c


def cmd_scan(args):
    files = collect(args.paths)
    if not files:
        print("No workflow files found.", file=sys.stderr); return 2
    print(f"{'File':52s} {'Findings':>8s}  {'HIGH':>4s} {'MED':>4s} {'LOW':>4s}")
    print("-" * 80)
    tot = 0
    for f in files:
        fi = scan(f); c = _sev(fi); tot += len(fi)
        print(f"{os.path.basename(f)[:52]:52s} {len(fi):8d}  {c['HIGH']:4d} {c['MEDIUM']:4d} {c['LOW']:4d}")
    print("-" * 80)
    print(f"{len(files)} file(s) scanned, {tot} finding(s) in total")
    return 0


def cmd_seed(args):
    doc = seed(load_yaml(args.input))
    if doc is None:
        print("No job with steps found; nothing seeded.", file=sys.stderr); return 2
    dump_yaml(doc, args.output); print(f"Seeded -> {args.output}"); return 0


def cmd_clean(args):
    dump_yaml(clean(load_yaml(args.input)), args.output); print(f"Cleaned -> {args.output}"); return 0


def cmd_demo(args):
    files = collect(args.paths)
    if not files:
        print("No workflow files found.", file=sys.stderr); return 2
    out = args.out
    rows = []
    for f in files:
        name = os.path.basename(f)
        try:
            orig = scan(f)
            doc = seed(load_yaml(f))
            if doc is None:
                rows.append({"file": name, "original": len(orig), "seeded": None, "cleaned": None,
                             "note": "no job with steps (e.g. reusable workflow) - not seeded"}); continue
            sp = os.path.join(out, "seeded", name); dump_yaml(doc, sp)
            seeded = scan(sp)
            cp = os.path.join(out, "cleaned", name); dump_yaml(clean(load_yaml(sp)), cp)
            cleaned = scan(cp)
            cats = sorted({x.category for x in seeded} - {x.category for x in orig})
            rows.append({"file": name, "original": len(orig), "seeded": len(seeded), "cleaned": len(cleaned),
                         "caught": len(seeded) - len(orig), "new_categories": cats, "note": ""})
        except Exception as e:  # keep going on odd files
            rows.append({"file": name, "original": None, "seeded": None, "cleaned": None, "note": f"error: {e}"})

    print(f"{'File':44s} {'Original':>8s} {'Seeded':>7s} {'Cleaned':>8s} {'Caught':>7s}")
    print("-" * 80)
    for r in rows:
        if r.get("seeded") is None:
            print(f"{r['file'][:44]:44s} {str(r['original']):>8s} {'-':>7s} {'-':>8s} {'-':>7s}  {r['note']}")
        else:
            print(f"{r['file'][:44]:44s} {r['original']:8d} {r['seeded']:7d} {r['cleaned']:8d} {r['caught']:7d}")
    done = [r for r in rows if r.get("seeded") is not None]
    if done:
        ok = sum(1 for r in done if r["cleaned"] == r["original"])
        caught = sum(r["caught"] for r in done)
        print("-" * 80)
        print(f"{len(done)} file(s) seeded: {caught} injected issue(s) detected; "
              f"{ok}/{len(done)} files back to their original finding count after cleaning")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "summary.json"), "w") as fh:
        json.dump(rows, fh, indent=2)
    write_html(rows, os.path.join(out, "report.html"))
    print(f"\nSeeded files : {os.path.join(out, 'seeded')}\nCleaned files: {os.path.join(out, 'cleaned')}"
          f"\nReport       : {os.path.join(out, 'report.html')}")
    return 0


def write_html(rows, path):
    def cell(v):
        return "-" if v is None else str(v)
    body = "".join(
        f"<tr><td>{r['file']}</td><td>{cell(r['original'])}</td><td class='s'>{cell(r['seeded'])}</td>"
        f"<td class='c'>{cell(r['cleaned'])}</td><td>{cell(r.get('caught'))}</td><td>{', '.join(r.get('new_categories', []))}{r.get('note','')}</td></tr>"
        for r in rows)
    html = f"""<!doctype html><meta charset="utf-8"><title>Seed and clean report</title>
<style>body{{font-family:Arial,sans-serif;margin:30px;color:#1b1b1b}}table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #9db8da;padding:8px 10px;text-align:left;font-size:15px}}th{{background:#dce9f7;color:#1f3864}}
.s{{color:#c0392b;font-weight:700}}.c{{color:#2e8b57;font-weight:700}}</style>
<h2>Hidden coupling: original, seeded, cleaned</h2>
<p>Original = findings in the file as given. Seeded = after injecting known issues. Cleaned = after removing the injected steps.</p>
<table><tr><th>File</th><th>Original</th><th>Seeded</th><th>Cleaned</th><th>Injected issues caught</th><th>New categories / note</th></tr>{body}</table>"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("paths", nargs="+"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("seed"); s.add_argument("input"); s.add_argument("output"); s.set_defaults(fn=cmd_seed)
    s = sub.add_parser("clean"); s.add_argument("input"); s.add_argument("output"); s.set_defaults(fn=cmd_clean)
    s = sub.add_parser("demo"); s.add_argument("paths", nargs="+"); s.add_argument("--out", default="demo_output"); s.set_defaults(fn=cmd_demo)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
