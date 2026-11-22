"""
Core detection engine: DetectHiddenCoupling(W)
"""

from dataclasses import dataclass
from typing import Optional
import yaml

from . import extract as ex


@dataclass
class Finding:
    severity: str
    category: str
    workflow: str
    job: Optional[str]
    step: Optional[str]
    message: str
    suggestion: str = ""

    def to_dict(self):
        return {
            "severity": self.severity, "category": self.category,
            "workflow": self.workflow, "job": self.job, "step": self.step,
            "message": self.message, "suggestion": self.suggestion,
        }


ARTIFACT_ACTIONS = ("upload-artifact", "download-artifact")


def parse_yaml(path):
    try:
        with open(path, "r") as f:
            doc = yaml.safe_load(f)
        if not isinstance(doc, dict) or "jobs" not in doc:
            return None, "missing top-level 'jobs' key"
        return doc, None
    except yaml.YAMLError as e:
        return None, str(e)
    except Exception as e:
        return None, str(e)


def _step_label(step, idx):
    return step.get("id") or step.get("name") or f"step[{idx}]"


def detect_hidden_coupling(workflow_paths):
    findings = []

    for w in workflow_paths:
        doc, err = parse_yaml(w)
        if err:
            findings.append(Finding("HIGH", "PARSE_ERROR", w, None, None, err))
            continue

        jobs = doc.get("jobs", {}) or {}
        if not isinstance(jobs, dict):
            continue
        env_wf = set((doc.get("env") or {}).keys())

        step_ids = {}
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            ids = {s["id"] for s in (job.get("steps") or []) if isinstance(s, dict) and s.get("id")}
            step_ids[job_name] = ids

        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            seen = {}
            needs_field = job.get("needs")
            if isinstance(needs_field, list):
                needs = set(needs_field)
            elif needs_field:
                needs = {needs_field}
            else:
                needs = set()
            job_env = set((job.get("env") or {}).keys())

            for idx, step in enumerate(job.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                label = _step_label(step, idx)
                run_text = step.get("run", "") or ""
                step_env = set((step.get("env") or {}).keys())

                refs = ex.extract_shell_var_refs(run_text)
                for v, setter in list(seen.items()):
                    if v in refs:
                        findings.append(Finding(
                            "MEDIUM", "ENV_MUTATION", w, job_name, label,
                            f"reads var '{v}' set implicitly by step '{setter}'",
                            f"declare the value via `outputs:` and reference it as "
                            f"${{{{ steps.{setter}.outputs.{v.lower()} }}}} instead of $GITHUB_ENV",
                        ))

                mutations = ex.extract_github_env_writes(run_text)
                for v in mutations:
                    seen[v] = label

                for step_id, out in ex.extract_step_output_refs(run_text):
                    if step_id not in step_ids.get(job_name, set()):
                        findings.append(Finding(
                            "HIGH", "DANGLING_OUTPUT", w, job_name, label,
                            f"references steps.{step_id}.outputs.{out}, but step id "
                            f"'{step_id}' was not found in job '{job_name}'",
                            f"check for a typo, or add `id: {step_id}` to the intended step",
                        ))

                local_assignments = ex.extract_local_assignments(run_text)
                is_pwsh = ex.is_non_bash_shell(step, job, doc)
                if is_pwsh:
                    local_assignments |= {m.group(1) for m in ex._POWERSHELL_ASSIGN_RE.finditer(run_text)}
                for v in refs:
                    if is_pwsh:
                        continue  # regex extraction targets bash; skip IMPLICIT_ENV_READ for pwsh/cmd steps
                    if (v not in ex.PREDEFINED
                            and v not in (step_env | job_env | env_wf)
                            and v not in seen
                            and v not in mutations
                            and v not in local_assignments):
                        findings.append(Finding(
                            "LOW", "IMPLICIT_ENV_READ", w, job_name, label,
                            f"undeclared variable '{v}' referenced with no visible "
                            f"declaration in env:, a prior $GITHUB_ENV write, or a local assignment",
                            f"declare '{v}' explicitly under `env:` for this step or job",
                        ))

            for ref_job in ex.extract_needs_refs(job):
                if ref_job not in needs:
                    findings.append(Finding(
                        "HIGH", "UNDECLARED_NEEDS", w, job_name, None,
                        f"reads needs.{ref_job}, but '{ref_job}' is not declared in this job's `needs:`",
                        f"add '{ref_job}' to this job's `needs:` list",
                    ))

        writers, readers = {}, {}
        uses_artifact = False
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            for idx, step in enumerate(job.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                label = _step_label(step, idx)
                uses = step.get("uses", "") or ""
                if any(a in uses for a in ARTIFACT_ACTIONS):
                    uses_artifact = True
                run_text = step.get("run", "") or ""
                for p in ex.extract_file_writes(run_text):
                    writers.setdefault(p, []).append((job_name, label))
                for p in ex.extract_file_reads(run_text):
                    readers.setdefault(p, []).append((job_name, label))

        if not uses_artifact:
            for path in set(writers) & set(readers):
                for (jw, sw) in writers[path]:
                    for (jr, sr) in readers[path]:
                        if jw != jr:
                            findings.append(Finding(
                                "MEDIUM", "SHARED_WORKDIR_WRITE", w,
                                f"{jw}\u2192{jr}", f"{sw}\u2192{sr}",
                                f"file '{path}' is written in job '{jw}' and read in job "
                                f"'{jr}', but jobs run on isolated runners with no shared filesystem",
                                "use actions/upload-artifact + actions/download-artifact "
                                "to pass files between jobs",
                            ))

    return findings
