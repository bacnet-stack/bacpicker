# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import html
from pathlib import Path
from typing import List

from ..result import RunReport, TestResult
from . import Reporter

_IUT_FIELDS = (
    ("Device", "device_id"),
    ("Name", "object_name"),
    ("Address", "address"),
    ("Vendor", "vendor_name"),
    ("Vendor ID", "vendor_id"),
    ("Model", "model_name"),
    ("Firmware", "firmware_revision"),
    ("Application software", "application_software_version"),
    ("Protocol revision", "protocol_revision"),
    ("Max APDU", "max_apdu_length_accepted"),
    ("Segmentation", "segmentation_supported"),
)


def _md(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_markdown(report: RunReport) -> str:
    summary = report.summary()
    out: List[str] = [
        "# BACnet Conformance Test Report",
        "",
        f"- Standard: {report.edition}",
        f"- Tool version: {report.tool_version}",
        f"- Started: {report.started}",
        f"- Finished: {report.finished}",
        "",
        "## Implementation Under Test",
        "",
        "| Item | Value |",
        "|---|---|",
    ]
    out += [f"| {label} | {_md(report.iut.get(key))} |" for label, key in _IUT_FIELDS]
    for warning in report.iut.get("warnings", []):
        out.append(f"\n> Warning: {warning}")
    out += [
        "",
        "## Summary",
        "",
        "| PASS | FAIL | ERROR | SKIP | TOTAL |",
        "|---|---|---|---|---|",
        "| " + " | ".join(str(summary[k]) for k in ("PASS", "FAIL", "ERROR", "SKIP", "TOTAL")) + " |",
        "",
        "## Results",
        "",
        "| Clause | Title | Status | Details |",
        "|---|---|---|---|",
    ]
    for r in report.results:
        detail = (
            f"{len(r.defects)} defect(s)"
            if r.defects
            else (r.reason or "").splitlines()[0] if r.reason else ""
        )
        out.append(f"| {r.clause} | {_md(r.title)} | {r.status.value} | {_md(detail)} |")

    failed = [r for r in report.results if r.defects or r.status.value == "ERROR"]
    if failed:
        out += ["", "## Defects", ""]
        for r in failed:
            out += [f"### {r.clause} {r.title}", ""]
            for d in r.defects:
                out.append(f"- **{_md(d.message)}** (step: {_md(d.step)})")
                for label in ("expected", "actual", "request", "response"):
                    value = getattr(d, label)
                    if value is not None:
                        out.append(f"  - {label}: `{value}`")
            if r.status.value == "ERROR" and r.reason:
                out += ["", "```", r.reason, "```"]
            out.append("")
    return "\n".join(out) + "\n"


def _html_result(r: TestResult) -> str:
    rows = []
    for d in r.defects:
        items = "".join(
            f"<li>{label}: <code>{html.escape(getattr(d, label))}</code></li>"
            for label in ("expected", "actual", "request", "response")
            if getattr(d, label) is not None
        )
        rows.append(
            f"<div class='defect'><b>{html.escape(d.message)}</b>"
            f" <i>(step: {html.escape(d.step)})</i><ul>{items}</ul></div>"
        )
    if r.reason and r.status.value != "PASS":
        rows.append(f"<pre>{html.escape(r.reason)}</pre>")
    steps = "".join(f"<li>{html.escape(s)}</li>" for s in r.steps)
    if steps:
        rows.append(f"<details><summary>steps</summary><ul class='steps'>{steps}</ul></details>")
    return (
        f"<tr class='{r.status.value}'><td>{html.escape(r.clause)}</td>"
        f"<td>{html.escape(r.title)}</td><td>{r.status.value}</td>"
        f"<td>{''.join(rows)}</td></tr>"
    )


def render_html(report: RunReport) -> str:
    summary = report.summary()
    iut_rows = "".join(
        f"<tr><th>{label}</th><td>{html.escape(str(report.iut.get(key)))}</td></tr>"
        for label, key in _IUT_FIELDS
    )
    warnings = "".join(
        f"<p class='warn'>Warning: {html.escape(w)}</p>" for w in report.iut.get("warnings", [])
    )
    results = "".join(_html_result(r) for r in report.results)
    totals = ", ".join(f"{k}={summary[k]}" for k in ("PASS", "FAIL", "ERROR", "SKIP", "TOTAL"))
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>BACnet Conformance Test Report</title>
<style>
body {{ font-family: sans-serif; margin: 2em; }}
table {{ border-collapse: collapse; margin-bottom: 1.5em; }}
td, th {{ border: 1px solid #ccc; padding: 4px 8px; text-align: left; vertical-align: top; }}
tr.PASS td:nth-child(3) {{ color: #080; }} tr.FAIL td:nth-child(3) {{ color: #c00; font-weight: bold; }}
tr.ERROR td:nth-child(3) {{ color: #909; font-weight: bold; }} tr.SKIP td:nth-child(3) {{ color: #a60; }}
.defect {{ margin-bottom: .5em; }} .warn {{ color: #a60; }} code {{ white-space: pre-wrap; }}
ul.steps {{ list-style: none; padding-left: 1em; }} ul.steps li {{ white-space: pre-wrap; }}
</style></head><body>
<h1>BACnet Conformance Test Report</h1>
<p>Standard: {html.escape(report.edition)} &middot; tool {html.escape(report.tool_version)}
&middot; {html.escape(report.started)} &ndash; {html.escape(str(report.finished))}</p>
<h2>Implementation Under Test</h2><table>{iut_rows}</table>{warnings}
<h2>Summary</h2><p>{totals}</p>
<h2>Results</h2>
<table><tr><th>Clause</th><th>Title</th><th>Status</th><th>Details</th></tr>{results}</table>
</body></html>
"""


class MarkdownReporter(Reporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def finish(self, report: RunReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(render_markdown(report), encoding="utf-8")


class HtmlReporter(Reporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def finish(self, report: RunReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(render_html(report), encoding="utf-8")
