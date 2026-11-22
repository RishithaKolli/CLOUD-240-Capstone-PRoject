"""
Extraction primitives used by the detection engine.
Regex-based static analysis of shell `run:` blocks and related fields.
"""

import re

PREDEFINED = {
    "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_WORKSPACE", "GITHUB_SHA",
    "GITHUB_REF", "GITHUB_REPOSITORY", "GITHUB_ACTOR", "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER", "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH",
    "GITHUB_TOKEN", "GITHUB_JOB", "GITHUB_ACTION", "GITHUB_WORKFLOW",
    "GITHUB_BASE_REF", "GITHUB_HEAD_REF", "GITHUB_STEP_SUMMARY",
    "GITHUB_PATH", "GITHUB_REF_NAME", "GITHUB_SERVER_URL", "GITHUB_API_URL",
    "GITHUB_ACTIONS", "GITHUB_REPOSITORY_OWNER", "RUNNER_OS", "RUNNER_TEMP",
    "RUNNER_ARCH", "RUNNER_TOOL_CACHE", "CI", "HOME", "PATH", "PWD",
    "USER", "IFS", "LANG", "TERM", "SHELL", "TMPDIR", "TZ",
}

_ENV_WRITE_RE = re.compile(
    r'echo\s+["\']?([A-Za-z_][A-Za-z0-9_]*)=.*?["\']?\s*>>\s*\$?\{?(GITHUB_ENV|GITHUB_OUTPUT|GITHUB_PATH)\}?'
)


def extract_github_env_writes(run_text):
    if not run_text:
        return set()
    return {m.group(1) for m in _ENV_WRITE_RE.finditer(run_text)}


_STEP_OUTPUT_RE = re.compile(
    r'\$\{\{\s*steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)\s*\}\}'
)


def extract_step_output_refs(run_text):
    if not run_text:
        return set()
    return {(m.group(1), m.group(2)) for m in _STEP_OUTPUT_RE.finditer(run_text)}


_SHELL_VAR_RE = re.compile(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?')


def extract_shell_var_refs(run_text):
    if not run_text:
        return set()
    return {m.group(1) for m in _SHELL_VAR_RE.finditer(run_text)}


_READ_VAR_RE = re.compile(r'\bread\b[^\n|;]*?(?:-[A-Za-z]+\s+(?:\S+\s+)?)*([A-Za-z_][A-Za-z0-9_]*)\s*(?:$|[;\n])')
_POWERSHELL_ASSIGN_RE = re.compile(r'(?:^|\n|;)\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*=')
_LOCAL_ASSIGN_RE = re.compile(r'(?:^|\n|;)\s*([A-Za-z_][A-Za-z0-9_]*)=', re.MULTILINE)

NON_BASH_SHELLS = {"pwsh", "powershell", "cmd"}


def extract_local_assignments(run_text):
    if not run_text:
        return set()
    found = {m.group(1) for m in _LOCAL_ASSIGN_RE.finditer(run_text)}
    # bash `while ... read -r -d '' file; do ... done` declares `file` as a loop variable
    found |= {m.group(1) for m in _READ_VAR_RE.finditer(run_text)}
    return found


def is_non_bash_shell(step, job, doc):
    """Resolve the effective shell for a step, honoring GitHub Actions'
    step > job.defaults.run.shell > workflow.defaults.run.shell precedence."""
    shell = (
        step.get("shell")
        or (job.get("defaults", {}) or {}).get("run", {}).get("shell")
        or (doc.get("defaults", {}) or {}).get("run", {}).get("shell")
        or ""
    )
    shell = shell.lower().split()[0] if shell else ""
    return shell in NON_BASH_SHELLS


_FILE_WRITE_RE = re.compile(r'(?:>>?|tee)\s+([./\w-]+\.\w+)')
_FILE_READ_RE = re.compile(r'(?:cat|source|\.)\s+([./\w-]+\.\w+)')


def extract_file_writes(run_text):
    if not run_text:
        return set()
    return {m.group(1) for m in _FILE_WRITE_RE.finditer(run_text)
            if m.group(1) not in ("$GITHUB_ENV", "$GITHUB_OUTPUT", "$GITHUB_PATH")}


def extract_file_reads(run_text):
    if not run_text:
        return set()
    return set(_FILE_READ_RE.findall(run_text))


_NEEDS_REF_RE = re.compile(r'needs\.([A-Za-z0-9_-]+)')


def extract_needs_refs(job):
    refs = set()
    for step in job.get("steps", []) or []:
        text = " ".join(filter(None, [step.get("run", ""), str(step.get("if", ""))]))
        refs |= set(_NEEDS_REF_RE.findall(text))
    return refs
