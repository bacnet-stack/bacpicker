# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Result reporters. Each receives start / test_started / test_finished / finish events."""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

from ..registry import TestCase
from ..result import RunReport, TestResult


class Reporter:
    def start(self, report: RunReport, tests: Sequence[TestCase]) -> None:
        pass

    def test_started(self, test: TestCase) -> None:
        pass

    def test_finished(self, result: TestResult) -> None:
        pass

    def finish(self, report: RunReport) -> None:
        pass


FORMATS = ("console", "json", "junit", "markdown", "html")


def make_reporters(formats: Sequence[str], output_dir: Path, verbose: bool = False) -> List[Reporter]:
    from .console import ConsoleReporter
    from .json_report import JsonReporter
    from .junit import JUnitReporter
    from .markdown_html import HtmlReporter, MarkdownReporter

    factories = {
        "console": lambda: ConsoleReporter(verbose=verbose),
        "json": lambda: JsonReporter(output_dir / "report.json"),
        "junit": lambda: JUnitReporter(output_dir / "report.junit.xml"),
        "markdown": lambda: MarkdownReporter(output_dir / "report.md"),
        "html": lambda: HtmlReporter(output_dir / "report.html"),
    }
    unknown = [f for f in formats if f not in factories]
    if unknown:
        raise ValueError(f"unknown report format(s): {', '.join(unknown)}")
    return [factories[f]() for f in dict.fromkeys(formats)]
