import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coupling_detector.detect import detect_hidden_coupling

CORPUS = ROOT / "real_world" / "downloaded"
OUTPUT = ROOT / "real_world" / "mac_benchmark_results.json"

files = sorted(CORPUS.glob("*.yml"))

if not files:
    raise SystemExit("ERROR: No workflow YAML files found.")

results = []
total_findings = 0
category_counts = {}
start_all = time.perf_counter()

for path in files:
    start = time.perf_counter()
    findings = detect_hidden_coupling([str(path)])
    elapsed_ms = (time.perf_counter() - start) * 1000

    categories = sorted({finding.category for finding in findings})
    total_findings += len(findings)

    for category in categories:
        category_counts[category] = category_counts.get(category, 0) + sum(
            finding.category == category for finding in findings
        )

    results.append({
        "file": path.name,
        "findings": len(findings),
        "categories": categories,
        "elapsed_ms": round(elapsed_ms, 3)
    })

wall_total_ms = (time.perf_counter() - start_all) * 1000
sum_file_ms = sum(item["elapsed_ms"] for item in results)

repositories = {path.name.split("__", 1)[0] for path in files}

report = {
    "timestamp": datetime.now().astimezone().isoformat(),
    "machine": platform.platform(),
    "architecture": platform.machine(),
    "python_version": platform.python_version(),
    "workflow_files": len(files),
    "repository_count": len(repositories),
    "total_findings": total_findings,
    "category_counts": category_counts,
    "sum_of_per_file_timings_ms": round(sum_file_ms, 3),
    "wall_clock_total_ms": round(wall_total_ms, 3),
    "average_per_file_ms": round(sum_file_ms / len(files), 3),
    "per_file_results": results
}

OUTPUT.write_text(json.dumps(report, indent=2) + "\n")

print("\nMAC REAL-WORLD BENCHMARK")
print("=" * 65)
print(f"Workflow files: {len(files)}")
print(f"Repositories: {len(repositories)}")
print(f"Total findings: {total_findings}")
print("\nIndividual timings:")

for item in results:
    print(
        f"{item['file']:45s} "
        f"{item['findings']:3d} findings "
        f"{item['elapsed_ms']:8.3f} ms"
    )

print("\nSUMMARY")
print(f"Sum of per-file timings: {sum_file_ms:.3f} ms")
print(f"Wall-clock total:        {wall_total_ms:.3f} ms")
print(f"Average per file:        {sum_file_ms / len(files):.3f} ms")
print(f"Results saved to:        {OUTPUT}")
