#!/usr/bin/env python3
"""Complete deterministic release gate."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts" / "release-evidence"


def run(
    command: Sequence[str], *, capture: Path | None = None, env: dict[str, str] | None = None
) -> None:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(
        list(command),
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if capture is not None:
        capture.parent.mkdir(parents=True, exist_ok=True)
        capture.write_text(completed.stdout or "", encoding="utf-8")
    if completed.returncode != 0:
        if capture is not None:
            print(capture.read_text(encoding="utf-8"), file=sys.stderr)
        raise SystemExit(completed.returncode)


def _detect_secrets() -> None:
    output = EVIDENCE / "detect-secrets.json"
    command = [
        "detect-secrets",
        "scan",
        "--all-files",
        "--exclude-files",
        "(^|/)(\\.git|\\.venv|\\.mypy_cache|\\.pytest_cache|\\.ruff_cache|__pycache__|\\.tox|\\.nox|evaluation|cases|tests|artifacts|dist|build|htmlcov|src/business_change_impact_agent/sample_case)(/|$)|(^|/)(uv\\.lock|\\.coverage(?:\\..*)?|coverage\\.xml)$",
    ]
    run(command, capture=output)
    payload = json.loads(output.read_text(encoding="utf-8"))
    results = payload.get("results", {})
    if not isinstance(results, dict):
        raise SystemExit("detect-secrets returned malformed output")
    active = {path: rows for path, rows in results.items() if rows}
    if active:
        print(json.dumps(active, indent=2, sort_keys=True), file=sys.stderr)
        raise SystemExit("detect-secrets findings require review")
    print("PASS: detect-secrets found no unexcluded candidate")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--skip-network-audit", action="store_true")
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    env = {"PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}

    run([sys.executable, "scripts/build_case.py", "--check"], env=env)
    run([sys.executable, "scripts/verify_case.py"], env=env)
    run([sys.executable, "scripts/generate_contracts.py", "--check"], env=env)
    run([sys.executable, "scripts/sync_package_assets.py", "--check"], env=env)
    run([sys.executable, "scripts/evaluate.py", "--check"], env=env)
    public_generator = ROOT / "scripts" / "generate_public_artifacts.py"
    public_verifier = ROOT / "scripts" / "verify_public_claims.py"
    if public_generator.exists():
        run([sys.executable, str(public_generator.relative_to(ROOT)), "--check"], env=env)
    if public_verifier.exists():
        run([sys.executable, str(public_verifier.relative_to(ROOT))], env=env)
    run([sys.executable, "scripts/scan_public_boundary.py"], env=env)
    run([sys.executable, "scripts/check_links.py"], env=env)
    run([sys.executable, "-m", "ruff", "format", "--check", "."], env=env)
    run([sys.executable, "-m", "ruff", "check", "."], env=env)
    run([sys.executable, "-m", "mypy", "src", "scripts"], env=env)
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=business_change_impact_agent",
            "--cov-branch",
            "--cov-report=term-missing",
            "--cov-report=xml:artifacts/release-evidence/coverage.xml",
            "--cov-fail-under=90",
        ],
        env=env,
    )
    run(
        [sys.executable, "-m", "bandit", "-q", "-r", "src", "-lll"],
        capture=EVIDENCE / "bandit.txt",
        env=env,
    )
    _detect_secrets()
    if not args.skip_network_audit:
        run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--local",
                "--skip-editable",
                "--format",
                "json",
            ],
            capture=EVIDENCE / "pip-audit.json",
            env=env,
        )

    shutil.rmtree(ROOT / "dist", ignore_errors=True)
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    run([sys.executable, "-m", "build"], env=env)
    archives = [str(path) for path in sorted((ROOT / "dist").glob("*"))]
    run([sys.executable, "-m", "twine", "check", *archives], env=env)
    run([sys.executable, "scripts/check_dist.py", "dist"], env=env)

    with tempfile.TemporaryDirectory(prefix="bcia-wheel-smoke-") as temporary:
        venv = Path(temporary) / "venv"
        run(["uv", "venv", "--python", sys.executable, str(venv)], env=env)
        python = venv / "bin" / "python"
        wheel = next((ROOT / "dist").glob("*.whl"))
        run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            env=env,
        )
        run(
            [
                str(python),
                "-c",
                "from business_change_impact_agent.service import ImpactAnalysisService; "
                "from business_change_impact_agent.paths import packaged_case_dir, packaged_design_dir; "
                "r=ImpactAnalysisService(packaged_design_dir()).analyse(packaged_case_dir()); "
                "assert r.summary['direct']==36; print(r.analysis_digest)",
            ],
            env={"PYTHONDONTWRITEBYTECODE": "1"},
        )
    print("PASS: complete deterministic release gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
