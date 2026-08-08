from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_change_impact_agent.cli import main
from business_change_impact_agent.domain import ReviewAction
from business_change_impact_agent.errors import ValidationError
from business_change_impact_agent.exporters import verify_export_equivalence, write_exports
from business_change_impact_agent.service import ImpactAnalysisService
from business_change_impact_agent.store import ReviewStore

ROOT = Path(__file__).resolve().parents[1]


def analysis():
    return ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")


def test_draft_and_confirmed_exports_are_equivalent_and_safe(tmp_path: Path) -> None:
    db = tmp_path / "review.sqlite3"
    store = ReviewStore(db)
    result = analysis()
    store.create_run("export-run", result)
    draft_paths = write_exports(store, "export-run", tmp_path / "draft")
    draft = json.loads(draft_paths["json"].read_text(encoding="utf-8"))
    assert draft["export_status"] == "DRAFT_NOT_APPROVED"

    challenge = store.issue_challenge(
        "export-run", result.analysis_digest,
        nonce_factory=lambda: "export-review-nonce-00000000000001",
    )
    store.record_review(
        run_id="export-run", analysis_digest=result.analysis_digest, nonce=challenge.nonce,
        reviewer="<Reviewer>", action=ReviewAction.CONFIRM,
        comment="<script>alert('x')</script>",
    )
    confirmed_paths = write_exports(store, "export-run", tmp_path / "confirmed")
    confirmed = json.loads(confirmed_paths["json"].read_text(encoding="utf-8"))
    html = confirmed_paths["html"].read_text(encoding="utf-8")
    assert confirmed["export_status"] == "CONFIRMED_HUMAN_REVIEW"
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html
    assert verify_export_equivalence(
        confirmed_paths["json"], confirmed_paths["markdown"], confirmed_paths["html"]
    ) == confirmed["snapshot_digest"]


def test_export_tampering_is_detected(tmp_path: Path) -> None:
    store = ReviewStore(tmp_path / "review.sqlite3")
    result = analysis()
    store.create_run("tamper-export", result)
    paths = write_exports(store, "tamper-export", tmp_path / "exports")
    paths["markdown"].write_text("<!-- impact-snapshot-sha256:" + "0" * 64 + " -->\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="not equivalent"):
        verify_export_equivalence(paths["json"], paths["markdown"], paths["html"])


def test_cli_validate_analyse_review_export_and_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    analysis_path = tmp_path / "analysis.json"
    db = tmp_path / "review.sqlite3"
    assert main(["validate", "--case", str(ROOT / "cases" / "atlasbridge")]) == 0
    assert main([
        "analyse", "--case", str(ROOT / "cases" / "atlasbridge"),
        "--design", str(ROOT / "design"), "--output", str(analysis_path),
        "--db", str(db), "--run-id", "cli-run",
    ]) == 0
    assert analysis_path.exists()
    assert main([
        "review-init", "--db", str(db), "--analysis", str(analysis_path),
        "--run-id", "cli-run", "--ttl-seconds", "600",
    ]) == 0
    output = capsys.readouterr().out
    challenge = json.loads(output[output.rfind("{\n"):])
    payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert main([
        "review", "--db", str(db), "--run-id", "cli-run",
        "--analysis-digest", payload["analysis_digest"], "--nonce", challenge["nonce"],
        "--reviewer", "CLI Reviewer", "--action", "CONFIRM",
    ]) == 0
    assert main([
        "export", "--db", str(db), "--run-id", "cli-run",
        "--output-dir", str(tmp_path / "exports"),
    ]) == 0
    assert main(["verify-ledger", "--db", str(db)]) == 0


def test_cli_demo_and_invalid_review_exit_codes(tmp_path: Path) -> None:
    assert main(["demo", "--workspace", str(tmp_path / "demo")]) == 0
    assert (tmp_path / "demo" / "demo-transcript.json").is_file()
    assert main([
        "review", "--db", str(tmp_path / "missing.sqlite3"), "--run-id", "missing",
        "--analysis-digest", "0" * 64, "--nonce", "x" * 32,
        "--reviewer", "Reviewer", "--action", "CONFIRM",
    ]) == 2
