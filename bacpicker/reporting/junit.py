# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..result import RunReport, Status
from . import Reporter


def defect_text(result) -> str:
    lines = []
    for d in result.defects:
        lines.append(f"[{d.clause}] {d.message}")
        lines.append(f"  step: {d.step}")
        for label in ("expected", "actual", "request", "response"):
            value = getattr(d, label)
            if value is not None:
                lines.append(f"  {label}: {value}")
    if result.reason:
        lines.append(result.reason)
    return "\n".join(lines)


class JUnitReporter(Reporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def finish(self, report: RunReport) -> None:
        summary = report.summary()
        suite = ET.Element(
            "testsuite",
            name=f"BACnet {report.edition} - {report.iut.get('device_id')}",
            tests=str(summary["TOTAL"]),
            failures=str(summary["FAIL"]),
            errors=str(summary["ERROR"]),
            skipped=str(summary["SKIP"]),
            time=f"{sum(r.duration for r in report.results):.3f}",
            timestamp=report.started,
        )
        props = ET.SubElement(suite, "properties")
        for key, value in report.iut.items():
            ET.SubElement(props, "property", name=f"iut.{key}", value=str(value))

        for result in report.results:
            case = ET.SubElement(
                suite,
                "testcase",
                classname=result.module,
                name=f"{result.clause} {result.title}",
                time=f"{result.duration:.3f}",
            )
            if result.status is Status.FAIL:
                first = result.defects[0].message if result.defects else (result.reason or "")
                ET.SubElement(case, "failure", message=first).text = defect_text(result)
            elif result.status is Status.ERROR:
                ET.SubElement(case, "error", message=(result.reason or "").splitlines()[0]).text = (
                    result.reason
                )
            elif result.status is Status.SKIP:
                ET.SubElement(case, "skipped", message=result.reason or "")
            if result.steps:
                ET.SubElement(case, "system-out").text = "\n".join(result.steps)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        root = ET.Element("testsuites")
        root.append(suite)
        tree = ET.ElementTree(root)
        ET.indent(tree)
        tree.write(self.path, encoding="utf-8", xml_declaration=True)
