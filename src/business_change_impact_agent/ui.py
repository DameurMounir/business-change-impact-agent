"""Professional local Streamlit Impact Room."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from .domain import ReviewAction
from .errors import ImpactAgentError
from .exporters import build_export_snapshot, export_html, export_json, export_markdown
from .paths import packaged_case_dir, packaged_design_dir
from .service import ImpactAnalysisService
from .store import ReviewStore


def _rows(analysis: Mapping[str, Any], classification: str | None = None) -> list[dict[str, Any]]:
    impacts = cast(list[Mapping[str, Any]], analysis["impacts"])
    selected = (
        impacts
        if classification is None
        else [row for row in impacts if row["classification"] == classification]
    )
    return [
        {
            "entity": row["entity_name"],
            "id": row["target_entity_id"],
            "classification": row["classification"],
            "domain": row["primary_domain"],
            "attention": row["attention_tier"],
            "origins": ", ".join(cast(list[str], row["origin_change_ids"])),
            "evidence": ", ".join(cast(list[str], row["evidence_refs"])),
        }
        for row in selected
    ]


def run() -> None:  # pragma: no cover - exercised through local Streamlit smoke checks
    import streamlit as st

    st.set_page_config(page_title="Business Change Impact Room", page_icon="🧭", layout="wide")
    st.title("Business Change Impact Room")
    st.caption("Evidence-linked direct and indirect impacts with human authority preserved.")
    st.info(
        "This local assessment does not approve implementation, budget, staffing, vendor selection, "
        "risk acceptance or go-live."
    )
    try:
        result = ImpactAnalysisService(packaged_design_dir()).analyse(packaged_case_dir())
        analysis = result.as_dict()
    except ImpactAgentError as exc:
        st.error(f"Validation blocked: {exc}")
        st.stop()

    summary = result.summary
    columns = st.columns(6)
    for column, (label, key) in zip(
        columns,
        [
            ("Direct", "direct"),
            ("Indirect", "indirect"),
            ("Conditional", "conditional"),
            ("Unaffected", "explicitly_unaffected"),
            ("Collisions", "collisions"),
            ("Blocked claims", "blocked_candidates"),
        ],
        strict=True,
    ):
        column.metric(label, int(summary.get(key, 0)))

    overview, direct, indirect, conditional, collisions, trace, review = st.tabs(
        ["Overview", "Direct", "Indirect", "Conditional", "Collisions", "Trace", "Human review"]
    )
    with overview:
        st.subheader("Decision question")
        st.write(result.decision_question)
        st.dataframe(_rows(analysis), use_container_width=True, hide_index=True)
    with direct:
        st.dataframe(_rows(analysis, "DIRECT"), use_container_width=True, hide_index=True)
    with indirect:
        st.dataframe(_rows(analysis, "INDIRECT"), use_container_width=True, hide_index=True)
    with conditional:
        st.warning("Conditional impacts retain unresolved assumptions or evidence gaps.")
        st.dataframe(_rows(analysis, "CONDITIONAL"), use_container_width=True, hide_index=True)
    with collisions:
        st.dataframe(
            [dict(item) for item in analysis["collisions"]],
            use_container_width=True,
            hide_index=True,
        )
    with trace:
        target_ids = [
            str(row["target_entity_id"])
            for row in cast(list[Mapping[str, Any]], analysis["impacts"])
        ]
        target = st.selectbox("Impacted entity", target_ids)
        selected = next(
            row
            for row in cast(list[Mapping[str, Any]], analysis["impacts"])
            if row["target_entity_id"] == target
        )
        st.json(selected)
    with review:
        workspace_text = st.text_input("Local workspace", value=".impact-room")
        reviewer = st.text_input("Reviewer", value="Mounir Dameur")
        action = st.selectbox("Action", [item.value for item in ReviewAction])
        comment = st.text_area("Comment", value="Synthetic case review only; no go-live decision.")
        workspace = Path(workspace_text)
        db_path = workspace / "impact-room.sqlite3"
        run_id = "atlasbridge-streamlit"
        if st.button("Issue local review challenge"):
            try:
                store = ReviewStore(db_path)
                store.create_run(run_id, result)
                challenge = store.issue_challenge(run_id, result.analysis_digest)
                st.session_state["review_nonce"] = challenge.nonce
                st.success("Challenge issued. The nonce is retained only in this browser session.")
            except (ImpactAgentError, OSError, ValueError) as exc:
                st.error(str(exc))
        nonce = st.session_state.get("review_nonce")
        if nonce and st.button("Record human review"):
            try:
                store = ReviewStore(db_path)
                record = store.record_review(
                    run_id=run_id,
                    analysis_digest=result.analysis_digest,
                    nonce=str(nonce),
                    reviewer=reviewer,
                    action=ReviewAction(action),
                    comment=comment,
                )
                st.session_state.pop("review_nonce", None)
                st.success(f"Recorded {record.state.value} as {record.review_id}")
            except (ImpactAgentError, OSError, ValueError) as exc:
                st.error(str(exc))
        if db_path.exists():
            try:
                snapshot = build_export_snapshot(ReviewStore(db_path), run_id)
                st.download_button(
                    "Download JSON",
                    export_json(snapshot),
                    file_name="impact-assessment.json",
                    mime="application/json",
                )
                st.download_button(
                    "Download Markdown",
                    export_markdown(snapshot),
                    file_name="impact-assessment.md",
                    mime="text/markdown",
                )
                st.download_button(
                    "Download HTML",
                    export_html(snapshot),
                    file_name="impact-assessment.html",
                    mime="text/html",
                )
            except (ImpactAgentError, OSError, ValueError):
                pass
