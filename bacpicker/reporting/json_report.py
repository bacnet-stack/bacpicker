# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path

from ..result import RunReport
from . import Reporter


class JsonReporter(Reporter):
    def __init__(self, path: Path) -> None:
        self.path = path

    def finish(self, report: RunReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
