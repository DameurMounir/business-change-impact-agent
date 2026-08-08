"""Equivalent JSON, Markdown and safe standalone HTML exports."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .canonical import canonical_json_bytes, pretty_json, sha256_bytes
from .errors import ValidationError
from .store import ReviewStore

_MD_MARKER = re.compile(r"^<!-- impact-snapshot-sha256:([0-9a-f]{64}) -->$")
_HTML_MARKER = re.compile(r'<meta name="impact-snapshot-sha256" content="([0-9a-f]{64})">')


def build_export_snapshot(store: ReviewStore, run_id: str) -> Mapping[str, Any]:
    stored = store.get_snapshot(run_id)
    state = str(stored["state"])
    analysis = cast(Mapping[str, Any], stored["analysis"])
    review = stored["review"]
    status = "CONFIRMED_HUMAN_REVIEW" if state.startswith("CONFIRMED") else "DRAFT_NOT_APPROVED"
    material: dict[str, Any] = {
        "schema_version": "1.0.0",
        "export_status": status,
        "authority_boundary": (
            "This export records an impact assessment and human review state only. It is not a "
            "go-live, budget, staffing, vendor, risk-acceptance or implementation decision."
        ),
        "run_id": run_id,
        "review_state": state,
        "analysis": analysis,
        "review": review,
    }
    digest = sha256_bytes(canonical_json_bytes(material))
    material["snapshot_digest"] = digest
    return material


def export_json(snapshot: Mapping[str, Any]) -> str:
    return pretty_json(dict(snapshot))


def _impact_rows(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    analysis = cast(Mapping[str, Any], snapshot["analysis"])
    rows = analysis.get("impacts")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValidationError("export snapshot impacts are malformed")
    return cast(list[Mapping[str, Any]], rows)


def export_markdown(snapshot: Mapping[str, Any]) -> str:
    digest = str(snapshot["snapshot_digest"])
    analysis = cast(Mapping[str, Any], snapshot["analysis"])
    summary = cast(Mapping[str, Any], analysis["summary"])
    lines = [
        f"<!-- impact-snapshot-sha256:{digest} -->",
        "# Business Change Impact Assessment",
        "",
        f"**Status:** `{snapshot['export_status']}`  ",
        f"**Run:** `{snapshot['run_id']}`  ",
        f"**Analysis digest:** `{analysis['analysis_digest']}`  ",
        f"**Review state:** `{snapshot['review_state']}`",
        "",
        "> " + str(snapshot["authority_boundary"]),
        "",
        "## Summary",
        "",
    ]
    for key, value in sorted(summary.items()):
        lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
    lines.extend(
        [
            "",
            "## Impact register",
            "",
            "| Entity | Classification | Domain | Attention | Origin changes |",
            "|---|---|---|---|---|",
        ]
    )
    for row in _impact_rows(snapshot):
        origins = ", ".join(str(item) for item in cast(list[object], row["origin_change_ids"]))
        name = str(row["entity_name"]).replace("|", "\\|")
        lines.append(
            f"| {name} (`{row['target_entity_id']}`) | {row['classification']} | "
            f"{row['primary_domain']} | {row['attention_tier']} | {origins} |"
        )
    review = snapshot.get("review")
    lines.extend(["", "## Human review", ""])
    if isinstance(review, dict):
        lines.extend(
            [
                f"- Reviewer: {review['reviewer']}",
                f"- Action: `{review['action']}`",
                f"- State: `{review['state']}`",
                f"- Review ID: `{review['review_id']}`",
                f"- Comment: {review['comment'] or '(none)'}",
            ]
        )
    else:
        lines.append("No terminal human review has been recorded. This is a draft export.")
    lines.extend(["", "## Limitations", ""])
    for limitation in cast(list[object], analysis["limitations"]):
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def export_html(snapshot: Mapping[str, Any]) -> str:
    digest = html.escape(str(snapshot["snapshot_digest"]), quote=True)
    analysis = cast(Mapping[str, Any], snapshot["analysis"])
    summary = cast(Mapping[str, Any], analysis["summary"])
    summary_html = "".join(
        f"<li><strong>{html.escape(str(key).replace('_', ' ').title())}:</strong> "
        f"{html.escape(str(value))}</li>"
        for key, value in sorted(summary.items())
    )
    rows_html = []
    for row in _impact_rows(snapshot):
        origins = ", ".join(str(item) for item in cast(list[object], row["origin_change_ids"]))
        values = [
            f"{row['entity_name']} ({row['target_entity_id']})",
            row["classification"],
            row["primary_domain"],
            row["attention_tier"],
            origins,
        ]
        rows_html.append(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in values) + "</tr>"
        )
    review = snapshot.get("review")
    if isinstance(review, dict):
        review_html = (
            "<ul>"
            f"<li>Reviewer: {html.escape(str(review['reviewer']))}</li>"
            f"<li>Action: {html.escape(str(review['action']))}</li>"
            f"<li>State: {html.escape(str(review['state']))}</li>"
            f"<li>Review ID: {html.escape(str(review['review_id']))}</li>"
            f"<li>Comment: {html.escape(str(review['comment']) or '(none)')}</li>"
            "</ul>"
        )
    else:
        review_html = "<p>No terminal human review has been recorded. This is a draft export.</p>"
    limitations = "".join(
        f"<li>{html.escape(str(value))}</li>"
        for value in cast(list[object], analysis["limitations"])
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="impact-snapshot-sha256" content="{digest}">
<title>Business Change Impact Assessment</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:auto;padding:2rem;line-height:1.5;color:#172033}}
.banner{{border-left:6px solid #2264d1;background:#eef4ff;padding:1rem}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{border:1px solid #ccd3df;padding:.5rem;text-align:left;vertical-align:top}}th{{background:#172033;color:white}}
code{{overflow-wrap:anywhere}}.status{{font-weight:700}}@media(max-width:700px){{table{{display:block;overflow-x:auto}}}}
</style>
</head>
<body>
<h1>Business Change Impact Assessment</h1>
<p class="status">Status: {html.escape(str(snapshot["export_status"]))}</p>
<p>Run: <code>{html.escape(str(snapshot["run_id"]))}</code><br>
Analysis digest: <code>{html.escape(str(analysis["analysis_digest"]))}</code><br>
Review state: <code>{html.escape(str(snapshot["review_state"]))}</code></p>
<div class="banner">{html.escape(str(snapshot["authority_boundary"]))}</div>
<h2>Summary</h2><ul>{summary_html}</ul>
<h2>Impact register</h2>
<table><thead><tr><th>Entity</th><th>Classification</th><th>Domain</th><th>Attention</th><th>Origin changes</th></tr></thead>
<tbody>{"".join(rows_html)}</tbody></table>
<h2>Human review</h2>{review_html}
<h2>Limitations</h2><ul>{limitations}</ul>
</body>
</html>
"""


def write_exports(store: ReviewStore, run_id: str, output_dir: Path) -> Mapping[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir.is_symlink():
        raise ValidationError("export directory may not be a symlink")
    snapshot = build_export_snapshot(store, run_id)
    paths = {
        "json": output_dir / f"{run_id}-impact-assessment.json",
        "markdown": output_dir / f"{run_id}-impact-assessment.md",
        "html": output_dir / f"{run_id}-impact-assessment.html",
    }
    paths["json"].write_text(export_json(snapshot), encoding="utf-8")
    paths["markdown"].write_text(export_markdown(snapshot), encoding="utf-8")
    paths["html"].write_text(export_html(snapshot), encoding="utf-8")
    verify_export_equivalence(paths["json"], paths["markdown"], paths["html"])
    return paths


def verify_export_equivalence(json_path: Path, markdown_path: Path, html_path: Path) -> str:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("JSON export must be an object")
    digest = str(payload.get("snapshot_digest", ""))
    material = dict(payload)
    material.pop("snapshot_digest", None)
    if digest != sha256_bytes(canonical_json_bytes(material)):
        raise ValidationError("JSON export snapshot digest mismatch")
    first_line = markdown_path.read_text(encoding="utf-8").splitlines()[0]
    markdown_match = _MD_MARKER.fullmatch(first_line)
    html_text = html_path.read_text(encoding="utf-8")
    html_match = _HTML_MARKER.search(html_text)
    if markdown_match is None or html_match is None:
        raise ValidationError("export digest marker is missing")
    if markdown_match.group(1) != digest or html_match.group(1) != digest:
        raise ValidationError("JSON, Markdown and HTML exports are not equivalent")
    if (
        "<script src=" in html_text.lower()
        or "http://" in html_text.lower()
        or "https://" in html_text.lower()
    ):
        raise ValidationError("HTML export contains an external dependency")
    return digest
