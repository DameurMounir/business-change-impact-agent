"""Command-line interface for the local impact assessment vertical."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from .canonical import pretty_json
from .case_validation import validate_case
from .domain import AnalysisResult, ReviewAction
from .errors import ImpactAgentError, ReviewConflictError, ValidationError
from .exporters import verify_export_equivalence, write_exports
from .paths import packaged_case_dir, packaged_design_dir, validate_identifier
from .review import ReviewRecord
from .serialization import analysis_from_dict
from .service import ImpactAnalysisService
from .store import ReviewStore


def _load_mapping(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValidationError(f"expected JSON object: {path}")
    return cast(Mapping[str, Any], value)


def _analysis(path: Path) -> AnalysisResult:
    return analysis_from_dict(_load_mapping(path))


def _case_path(value: str | None) -> Path:
    return Path(value) if value else packaged_case_dir()


def _design_path(value: str | None) -> Path:
    return Path(value) if value else packaged_design_dir()


def _print_review(record: ReviewRecord) -> None:
    print(pretty_json(record.as_dict()), end="")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="business-change-impact-agent",
        description="Trace evidence-linked direct and indirect business change impacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="verify a frozen case")
    validate.add_argument("--case")

    analyse = subparsers.add_parser("analyse", help="run the provider-free analysis")
    analyse.add_argument("--case")
    analyse.add_argument("--design")
    analyse.add_argument("--output", required=True)
    analyse.add_argument("--db")
    analyse.add_argument("--run-id", default="atlasbridge-default")

    review_init = subparsers.add_parser("review-init", help="issue a digest-bound review challenge")
    review_init.add_argument("--db", required=True)
    review_init.add_argument("--analysis", required=True)
    review_init.add_argument("--run-id", required=True)
    review_init.add_argument("--ttl-seconds", type=int, default=600)

    review = subparsers.add_parser("review", help="record one terminal human review")
    review.add_argument("--db", required=True)
    review.add_argument("--run-id", required=True)
    review.add_argument("--analysis-digest", required=True)
    review.add_argument("--nonce", required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--action", choices=[item.value for item in ReviewAction], required=True)
    review.add_argument("--comment", default="")
    review.add_argument("--edits")

    export = subparsers.add_parser("export", help="write equivalent JSON, Markdown and HTML")
    export.add_argument("--db", required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--output-dir", required=True)

    ledger = subparsers.add_parser("verify-ledger", help="verify the local event hash chain")
    ledger.add_argument("--db", required=True)

    verify_exports = subparsers.add_parser("verify-exports", help="verify export equivalence")
    verify_exports.add_argument("--json", required=True)
    verify_exports.add_argument("--markdown", required=True)
    verify_exports.add_argument("--html", required=True)

    demo = subparsers.add_parser("demo", help="run the complete provider-free local journey")
    demo.add_argument("--workspace", required=True)
    demo.add_argument("--reviewer", default="Mounir Dameur")
    return parser


def run_command(args: argparse.Namespace) -> int:
    command = str(args.command)
    if command == "validate":
        summary = validate_case(_case_path(args.case))
        print(pretty_json(summary.as_dict()), end="")
        return 0
    if command == "analyse":
        run_id = validate_identifier(str(args.run_id), label="run ID")
        result = ImpactAnalysisService(_design_path(args.design)).analyse(_case_path(args.case))
        output = Path(str(args.output))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(pretty_json(result.as_dict()), encoding="utf-8")
        if args.db:
            ReviewStore(Path(str(args.db))).create_run(run_id, result)
        print(
            pretty_json({"analysis_digest": result.analysis_digest, "summary": result.summary}),
            end="",
        )
        return 0
    if command == "review-init":
        analysis = _analysis(Path(str(args.analysis)))
        store = ReviewStore(Path(str(args.db)))
        store.create_run(str(args.run_id), analysis)
        challenge = store.issue_challenge(
            str(args.run_id), analysis.analysis_digest, ttl_seconds=int(args.ttl_seconds)
        )
        print(pretty_json(challenge.as_dict()), end="")
        return 0
    if command == "review":
        raw_edits: Sequence[Mapping[str, object]] = ()
        if args.edits:
            value = json.loads(Path(str(args.edits)).read_text(encoding="utf-8"))
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise ValidationError("edits file must contain a JSON list of objects")
            raw_edits = cast(Sequence[Mapping[str, object]], value)
        record = ReviewStore(Path(str(args.db))).record_review(
            run_id=str(args.run_id),
            analysis_digest=str(args.analysis_digest),
            nonce=str(args.nonce),
            reviewer=str(args.reviewer),
            action=ReviewAction(str(args.action)),
            comment=str(args.comment),
            edits=raw_edits,
        )
        _print_review(record)
        return 0
    if command == "export":
        paths = write_exports(
            ReviewStore(Path(str(args.db))), str(args.run_id), Path(str(args.output_dir))
        )
        print(pretty_json({key: str(value) for key, value in paths.items()}), end="")
        return 0
    if command == "verify-ledger":
        count = ReviewStore(Path(str(args.db))).verify_ledger()
        print(pretty_json({"verified_events": count}), end="")
        return 0
    if command == "verify-exports":
        digest = verify_export_equivalence(
            Path(str(args.json)), Path(str(args.markdown)), Path(str(args.html))
        )
        print(pretty_json({"snapshot_digest": digest}), end="")
        return 0
    if command == "demo":
        from .demo import run_demo

        transcript = run_demo(Path(str(args.workspace)), reviewer=str(args.reviewer))
        print(pretty_json(transcript), end="")
        return 0
    raise ValidationError(f"unsupported command: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_command(args)
    except ReviewConflictError as exc:
        print(f"BLOCKED_REVIEW_CONFLICT: {exc}", file=sys.stderr)
        return 3
    except (ImpactAgentError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"BLOCKED_INVALID_INPUT: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
