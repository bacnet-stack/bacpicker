# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from typing import Sequence, TextIO

from ..registry import TestCase
from ..result import RunReport, Status, TestResult
from . import Reporter

_COLORS = {
    Status.PASS: "\033[32m",
    Status.FAIL: "\033[31m",
    Status.ERROR: "\033[35m",
    Status.SKIP: "\033[33m",
}
_RESET = "\033[0m"


class ConsoleReporter(Reporter):
    def __init__(self, stream: TextIO = sys.stdout, verbose: bool = False) -> None:
        self.stream = stream
        self.verbose = verbose
        self.color = hasattr(stream, "isatty") and stream.isatty()

    def _status(self, status: Status) -> str:
        text = f"{status.value:<5}"
        return f"{_COLORS[status]}{text}{_RESET}" if self.color else text

    def _print(self, text: str = "") -> None:
        print(text, file=self.stream, flush=True)

    def start(self, report: RunReport, tests: Sequence[TestCase]) -> None:
        iut = report.iut
        self._print(f"BACnet conformance test run ({report.edition})")
        self._print(
            f"IUT: {iut.get('device_id')} '{iut.get('object_name')}' at {iut.get('address')}"
            f" vendor={iut.get('vendor_name')} ({iut.get('vendor_id')})"
            f" model={iut.get('model_name')} rev={iut.get('protocol_revision')}"
        )
        for warning in iut.get("warnings", []):
            self._print(f"  warning: {warning}")
        self._print(f"{len(tests)} test(s) selected")
        self._print()

    def test_finished(self, result: TestResult) -> None:
        self._print(
            f"{self._status(result.status)} {result.clause:<12} {result.title}"
            + (f"  ({result.duration:.2f}s)" if result.duration else "")
        )
        if self.verbose:
            for step in result.steps:
                self._print(f"        {step}")
        if result.reason and result.status is not Status.PASS:
            first, *rest = result.reason.splitlines()
            self._print(f"        {first}")
            if self.verbose:
                for line in rest:
                    self._print(f"        {line}")
        for defect in result.defects:
            self._print(f"        DEFECT [{defect.clause}] {defect.message}")
            self._print(f"          step:     {defect.step}")
            for label in ("expected", "actual", "request", "response"):
                value = getattr(defect, label)
                if value is not None:
                    self._print(f"          {label + ':':<9} {value}")

    def finish(self, report: RunReport) -> None:
        summary = report.summary()
        self._print()
        self._print(
            "Summary: "
            + ", ".join(f"{k}={summary[k]}" for k in ("PASS", "FAIL", "ERROR", "SKIP", "TOTAL"))
        )
