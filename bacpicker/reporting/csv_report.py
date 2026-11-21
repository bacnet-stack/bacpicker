# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""One row per test, for spreadsheets and other tabular tools."""

from __future__ import annotations

import csv
from pathlib import Path

from ..result import RunReport
from . import Reporter
from .junit import defect_text

COLUMNS = ("clause", "title", "status", "module", "started", "duration", "defects", "details")


class CsvReporter(Reporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def finish(self, report: RunReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig so Excel detects the encoding; newline="" as the csv module requires
        with self.path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            for r in report.results:
                writer.writerow(
                    (
                        r.clause,
                        r.title,
                        r.status.value,
                        r.module,
                        r.started or "",
                        f"{r.duration:.3f}",
                        len(r.defects),
                        defect_text(r),
                    )
                )
