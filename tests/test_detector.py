"""
Automated tests validating the correctness properties claimed in the report:

  Soundness:    0 findings on the clean control workflow.
  Completeness: all 9 seeded issues, across all 5 categories, are detected.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coupling_detector.detect import detect_hidden_coupling  # noqa: E402

WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "workflows")
CLEAN = os.path.join(WORKFLOWS_DIR, "clean.yml")
SEEDED = os.path.join(WORKFLOWS_DIR, "seeded.yml")


def test_soundness_no_false_positives_on_clean_workflow():
    findings = detect_hidden_coupling([CLEAN])
    assert findings == [], f"expected 0 findings, got {len(findings)}: {findings}"


def test_completeness_all_seeded_issues_detected():
    findings = detect_hidden_coupling([SEEDED])
    assert len(findings) == 9, f"expected 9 findings, got {len(findings)}"


def test_completeness_all_five_categories_present():
    findings = detect_hidden_coupling([SEEDED])
    categories = {f.category for f in findings}
    expected = {
        "ENV_MUTATION",
        "DANGLING_OUTPUT",
        "IMPLICIT_ENV_READ",
        "UNDECLARED_NEEDS",
        "SHARED_WORKDIR_WRITE",
    }
    assert categories == expected, f"missing categories: {expected - categories}"


def test_parse_error_reported_for_invalid_workflow(tmp_path):
    bad_file = tmp_path / "broken.yml"
    bad_file.write_text("jobs:\n  build:\n    steps: [unterminated")
    findings = detect_hidden_coupling([str(bad_file)])
    assert len(findings) == 1
    assert findings[0].category == "PARSE_ERROR"
    assert findings[0].severity == "HIGH"


def test_severity_distribution_on_seeded_workflow():
    findings = detect_hidden_coupling([SEEDED])
    counts = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    assert counts == {"HIGH": 3, "MEDIUM": 3, "LOW": 3}
