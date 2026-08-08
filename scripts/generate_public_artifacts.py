#!/usr/bin/env python3
"""Generate deterministic SVG diagrams and public previews."""

from __future__ import annotations

import argparse
import html
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from business_change_impact_agent.service import ImpactAnalysisService  # noqa: E402


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def _svg(width: int, height: int, body: str, title: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{html.escape(title)}</title>
<desc id="desc">{html.escape(title)} generated from the committed synthetic impact assessment.</desc>
<rect width="100%" height="100%" fill="#f7f9fc"/>
<style>
.title{{font:700 34px system-ui,sans-serif;fill:#10233f}}.h2{{font:700 22px system-ui,sans-serif;fill:#10233f}}.body{{font:16px system-ui,sans-serif;fill:#33445d}}.small{{font:14px system-ui,sans-serif;fill:#53647a}}.metric{{font:700 30px system-ui,sans-serif;fill:#10233f}}.label{{font:700 14px system-ui,sans-serif;fill:#53647a;letter-spacing:.6px}}.box{{fill:#fff;stroke:#c7d2e3;stroke-width:2}}.direct{{fill:#e8f0ff;stroke:#2f6fed;stroke-width:2}}.indirect{{fill:#e9f8f3;stroke:#138a68;stroke-width:2}}.conditional{{fill:#fff5da;stroke:#c68400;stroke-width:2}}.blocked{{fill:#feecec;stroke:#c33f49;stroke-width:2}}.dark{{fill:#10233f}}.white{{fill:#fff}}.arrow{{stroke:#62748a;stroke-width:3;fill:none;marker-end:url(#arrow)}}
</style>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#62748a"/></marker></defs>
{body}
</svg>'''


def generate(root: Path) -> None:
    assets = root / "assets"
    analysis = ImpactAnalysisService(ROOT / "design").analyse(ROOT / "cases" / "atlasbridge")
    summary = analysis.summary

    social = f"""
<rect x="0" y="0" width="1280" height="640" fill="#10233f"/>
<rect x="56" y="54" width="1168" height="532" rx="28" fill="#ffffff"/>
<text x="100" y="135" class="label">PUBLIC BUSINESS ANALYSIS CASE STUDY</text>
<text x="100" y="205" class="title">Business Change Impact Agent</text>
<text x="100" y="250" class="h2">What changes directly and indirectly?</text>
<text x="100" y="305" class="body">Evidence-linked graph traversal • explicit uncertainty • human confirmation</text>
<g transform="translate(100,360)">
  <rect width="190" height="125" rx="16" class="direct"/><text x="24" y="43" class="label">DIRECT</text><text x="24" y="91" class="metric">{summary["direct"]}</text>
  <rect x="215" width="190" height="125" rx="16" class="indirect"/><text x="239" y="43" class="label">INDIRECT</text><text x="239" y="91" class="metric">{summary["indirect"]}</text>
  <rect x="430" width="190" height="125" rx="16" class="conditional"/><text x="454" y="43" class="label">CONDITIONAL</text><text x="454" y="91" class="metric">{summary["conditional"]}</text>
  <rect x="645" width="190" height="125" rx="16" class="box"/><text x="669" y="43" class="label">COLLISIONS</text><text x="669" y="91" class="metric">{summary["collisions"]}</text>
  <rect x="860" width="190" height="125" rx="16" class="blocked"/><text x="884" y="43" class="label">BLOCKED CLAIMS</text><text x="884" y="91" class="metric">{summary["blocked_candidates"]}</text>
</g>
<text x="100" y="545" class="small">Frozen synthetic AtlasBridge case • provider-free baseline • no go-live decision</text>
"""
    _write(
        assets / "social-preview.svg",
        _svg(1280, 640, social, "Business Change Impact Agent social preview"),
    )

    interface = f"""
<rect x="0" y="0" width="1400" height="900" fill="#eef3f9"/>
<rect x="35" y="30" width="1330" height="840" rx="22" fill="#ffffff" stroke="#c7d2e3" stroke-width="2"/>
<text x="78" y="95" class="title">Business Change Impact Room</text>
<text x="78" y="132" class="body">Evidence-linked direct and indirect impacts with human authority preserved.</text>
<rect x="78" y="160" width="1245" height="58" rx="10" fill="#eef4ff" stroke="#2f6fed"/>
<text x="100" y="195" class="small">Assessment only — no implementation, budget, staffing, vendor, risk-acceptance or go-live authority.</text>
<g transform="translate(78,250)">
  <rect width="180" height="105" rx="14" class="direct"/><text x="20" y="34" class="label">DIRECT</text><text x="20" y="78" class="metric">{summary["direct"]}</text>
  <rect x="205" width="180" height="105" rx="14" class="indirect"/><text x="225" y="34" class="label">INDIRECT</text><text x="225" y="78" class="metric">{summary["indirect"]}</text>
  <rect x="410" width="180" height="105" rx="14" class="conditional"/><text x="430" y="34" class="label">CONDITIONAL</text><text x="430" y="78" class="metric">{summary["conditional"]}</text>
  <rect x="615" width="180" height="105" rx="14" class="box"/><text x="635" y="34" class="label">UNAFFECTED</text><text x="635" y="78" class="metric">{summary["explicitly_unaffected"]}</text>
  <rect x="820" width="180" height="105" rx="14" class="box"/><text x="840" y="34" class="label">COLLISIONS</text><text x="840" y="78" class="metric">{summary["collisions"]}</text>
  <rect x="1025" width="180" height="105" rx="14" class="blocked"/><text x="1045" y="34" class="label">BLOCKED</text><text x="1045" y="78" class="metric">{summary["blocked_candidates"]}</text>
</g>
<g transform="translate(78,395)">
  <rect width="1245" height="390" rx="14" class="box"/>
  <rect width="1245" height="54" rx="14" class="dark"/>
  <text x="22" y="35" class="white" style="font:700 15px system-ui,sans-serif">ENTITY</text><text x="430" y="35" class="white" style="font:700 15px system-ui,sans-serif">CLASS</text><text x="620" y="35" class="white" style="font:700 15px system-ui,sans-serif">DOMAIN</text><text x="1040" y="35" class="white" style="font:700 15px system-ui,sans-serif">ATTENTION</text>
  <text x="22" y="95" class="body">Workflow orchestration system</text><text x="430" y="95" class="body">DIRECT</text><text x="620" y="95" class="body">SYSTEM_AND_APPLICATION</text><text x="1040" y="95" class="body">HIGH</text>
  <line x1="20" y1="118" x2="1225" y2="118" stroke="#d6deea"/>
  <text x="22" y="158" class="body">Screening interface</text><text x="430" y="158" class="body">INDIRECT</text><text x="620" y="158" class="body">INTEGRATION_AND_EXTERNAL_SERVICE</text><text x="1040" y="158" class="body">HIGH</text>
  <line x1="20" y1="181" x2="1225" y2="181" stroke="#d6deea"/>
  <text x="22" y="221" class="body">External screening service</text><text x="430" y="221" class="body">CONDITIONAL</text><text x="620" y="221" class="body">INTEGRATION_AND_EXTERNAL_SERVICE</text><text x="1040" y="221" class="body">CRITICAL</text>
  <line x1="20" y1="244" x2="1225" y2="244" stroke="#d6deea"/>
  <text x="22" y="284" class="body">Payroll processing</text><text x="430" y="284" class="body">EXPLICITLY_UNAFFECTED</text><text x="620" y="284" class="body">ROLE_AND_TEAM</text><text x="1040" y="284" class="body">LOW</text>
  <line x1="20" y1="307" x2="1225" y2="307" stroke="#d6deea"/>
  <text x="22" y="352" class="small">Trace view exposes relationship IDs, exact evidence references, conditions, gaps and digest.</text>
</g>
<text x="78" y="835" class="small">Deterministic interface preview — not a captured production screen.</text>
"""
    _write(
        assets / "interface-preview.svg",
        _svg(1400, 900, interface, "Deterministic Impact Room interface preview"),
    )

    architecture = """
<text x="55" y="70" class="title">Evidence-authoritative architecture</text>
<rect x="55" y="130" width="220" height="115" rx="16" class="box"/><text x="82" y="175" class="h2">Frozen case</text><text x="82" y="208" class="small">evidence • entities • graph</text>
<path d="M275 188 H350" class="arrow"/>
<rect x="350" y="130" width="220" height="115" rx="16" class="box"/><text x="380" y="175" class="h2">Rulebook</text><text x="380" y="208" class="small">direction • depth • conditions</text>
<path d="M570 188 H645" class="arrow"/>
<rect x="645" y="130" width="245" height="115" rx="16" class="direct"/><text x="675" y="175" class="h2">Rule adapter</text><text x="675" y="208" class="small">provider-free proposal</text>
<path d="M890 188 H965" class="arrow"/>
<rect x="965" y="130" width="260" height="115" rx="16" class="indirect"/><text x="992" y="175" class="h2">Verifier</text><text x="992" y="208" class="small">recomputes and fails closed</text>
<path d="M1095 245 V330" class="arrow"/>
<rect x="965" y="330" width="260" height="115" rx="16" class="box"/><text x="997" y="375" class="h2">Impact packet</text><text x="997" y="408" class="small">paths • gaps • obligations</text>
<path d="M965 388 H870" class="arrow"/>
<rect x="600" y="330" width="270" height="115" rx="16" class="conditional"/><text x="628" y="375" class="h2">Human review</text><text x="628" y="408" class="small">digest • nonce • terminal action</text>
<path d="M600 388 H505" class="arrow"/>
<rect x="220" y="330" width="285" height="115" rx="16" class="box"/><text x="250" y="375" class="h2">Equivalent exports</text><text x="250" y="408" class="small">JSON • Markdown • safe HTML</text>
<rect x="55" y="520" width="1170" height="82" rx="14" fill="#feecec" stroke="#c33f49" stroke-width="2"/>
<text x="82" y="555" class="h2">Authority boundary</text><text x="82" y="584" class="small">No implementation, external write, budget, staffing, vendor selection, risk acceptance or go-live decision.</text>
"""
    _write(
        assets / "architecture.svg",
        _svg(1280, 660, architecture, "Business change impact architecture"),
    )

    trace = """
<text x="55" y="70" class="title">Direct versus indirect trace</text>
<rect x="55" y="125" width="210" height="100" rx="15" class="direct"/><text x="82" y="165" class="label">CHANGE COMPONENT</text><text x="82" y="198" class="h2">CC-03</text>
<path d="M265 175 H335" class="arrow"/>
<rect x="335" y="125" width="250" height="100" rx="15" class="direct"/><text x="362" y="165" class="label">DIRECT • MODIFIES</text><text x="362" y="198" class="h2">Workflow system</text>
<path d="M585 175 H655" class="arrow"/>
<rect x="655" y="125" width="230" height="100" rx="15" class="indirect"/><text x="682" y="165" class="label">INDIRECT • CALLS</text><text x="682" y="198" class="h2">Interface</text>
<path d="M885 175 H955" class="arrow"/>
<rect x="955" y="125" width="240" height="100" rx="15" class="indirect"/><text x="982" y="165" class="label">INDIRECT • INTEGRATES</text><text x="982" y="198" class="h2">Integration</text>
<path d="M1075 225 V315" class="arrow"/>
<rect x="870" y="315" width="325" height="110" rx="15" class="conditional"/><text x="900" y="357" class="label">CONDITIONAL • DEPENDS ON</text><text x="900" y="392" class="h2">External screening service</text>
<rect x="55" y="315" width="730" height="110" rx="15" class="box"/><text x="82" y="355" class="h2">Why it is included</text><text x="82" y="388" class="body">Every edge is forward, explicitly allowed, within four edges and backed by exact evidence.</text>
<rect x="55" y="475" width="1140" height="85" rx="15" class="blocked"/><text x="82" y="510" class="h2">Vendor remains blocked</text><text x="82" y="540" class="body">The fifth edge exceeds the published depth boundary; no unsupported impact is added.</text>
"""
    _write(
        assets / "direct-indirect-trace.svg",
        _svg(1250, 620, trace, "Direct and indirect impact trace"),
    )

    workflow = """
<text x="55" y="70" class="title">Controlled workflow</text>
<g transform="translate(55,125)">
<rect width="170" height="82" rx="13" class="box"/><text x="28" y="49" class="h2">Validate</text><path d="M170 41 H225" class="arrow"/>
<rect x="225" width="170" height="82" rx="13" class="direct"/><text x="255" y="49" class="h2">Trace direct</text><path d="M395 41 H450" class="arrow"/>
<rect x="450" width="190" height="82" rx="13" class="indirect"/><text x="477" y="49" class="h2">Propagate</text><path d="M640 41 H695" class="arrow"/>
<rect x="695" width="190" height="82" rx="13" class="conditional"/><text x="727" y="49" class="h2">Separate gaps</text><path d="M885 41 H940" class="arrow"/>
<rect x="940" width="190" height="82" rx="13" class="box"/><text x="970" y="49" class="h2">Human review</text>
<path d="M1035 82 V155" class="arrow"/>
<rect x="805" y="155" width="325" height="82" rx="13" class="box"/><text x="840" y="204" class="h2">Digest-equivalent exports</text>
<path d="M805 196 H720" class="arrow"/>
<rect x="450" y="155" width="270" height="82" rx="13" class="blocked"/><text x="484" y="204" class="h2">Stop before execution</text>
</g>
<text x="55" y="440" class="body">Human authority is explicit: confirm, request revision, apply bounded review edits or reject.</text>
<text x="55" y="478" class="body">Every terminal review binds the exact analysis digest and a single-use expiring challenge.</text>
"""
    _write(
        assets / "workflow.svg",
        _svg(1250, 560, workflow, "Controlled business change impact workflow"),
    )

    ordered = sorted(
        analysis.domain_heatmap.items(),
        key=lambda item: (-sum(item[1].values()), item[0]),
    )[:10]
    bars = []
    y = 120
    maximum = max(sum(counts.values()) for _, counts in ordered)
    for domain, counts in ordered:
        total = sum(counts.values())
        width = int(650 * total / maximum)
        bars.append(
            f'<text x="55" y="{y + 22}" class="small">{html.escape(domain)}</text>'
            f'<rect x="470" y="{y}" width="{width}" height="30" rx="7" fill="#2f6fed"/>'
            f'<text x="{485 + width}" y="{y + 22}" class="body">{total}</text>'
        )
        y += 48
    heatmap_body = (
        '<text x="55" y="70" class="title">Impact concentration by business domain</text>'
        + "".join(bars)
    )
    _write(
        assets / "domain-heatmap.svg",
        _svg(1250, 660, heatmap_body, "Impact count by business domain"),
    )


def tree(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes() for item in sorted(path.rglob("*.svg"))
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory(prefix="bcia-public-") as temporary:
            generated = Path(temporary)
            generate(generated)
            if tree(generated / "assets") != tree(ROOT / "assets"):
                print("public SVG artifact drift detected")
                return 1
        print("PASS: public SVG artifacts are byte-stable")
        return 0
    generate(ROOT)
    print("PASS: generated deterministic public SVG artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
