"""
Runs the detector against the real-world workflow corpus and produces
a metrics report: findings per category, per-repo breakdown, and timing.
"""

import glob
import json
import time
import sys

sys.path.insert(0, "/home/claude/project")
from coupling_detector.detect import detect_hidden_coupling  # noqa: E402

files = sorted(glob.glob("/home/claude/project/real_world/downloaded/*.yml"))

results_per_file = []
all_findings = []
total_time = 0.0

for f in files:
    t0 = time.perf_counter()
    findings = detect_hidden_coupling([f])
    elapsed = time.perf_counter() - t0
    total_time += elapsed
    results_per_file.append({
        "file": f.split("/")[-1],
        "findings": len(findings),
        "categories": sorted({fi.category for fi in findings}),
        "elapsed_ms": round(elapsed * 1000, 2),
    })
    all_findings.extend(findings)

# Aggregate by category
by_category = {}
for fi in all_findings:
    by_category[fi.category] = by_category.get(fi.category, 0) + 1

by_severity = {}
for fi in all_findings:
    by_severity[fi.severity] = by_severity.get(fi.severity, 0) + 1

print("=" * 70)
print(f"CORPUS: {len(files)} real-world workflow files from 8 open-source repos")
print("=" * 70)
for r in results_per_file:
    marker = " <-- issues found" if r["findings"] else ""
    print(f"  {r['file']:45s} {r['findings']:3d} findings  {r['elapsed_ms']:6.2f}ms{marker}")

print()
print(f"Total findings: {len(all_findings)}")
print(f"By category: {json.dumps(by_category, indent=2)}")
print(f"By severity: {json.dumps(by_severity, indent=2)}")
print(f"Total analysis time: {total_time*1000:.2f}ms across {len(files)} files "
      f"({(total_time*1000/len(files)):.2f}ms avg/file)")

# Dump full findings for manual review
with open("/home/claude/project/real_world/all_findings.json", "w") as out:
    json.dump([fi.to_dict() for fi in all_findings], out, indent=2)

with open("/home/claude/project/real_world/per_file_summary.json", "w") as out:
    json.dump(results_per_file, out, indent=2)

print("\nWrote all_findings.json and per_file_summary.json")
