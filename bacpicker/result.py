# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Test result data model shared by the runner and reporters."""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


class Status(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class Defect:
    """A single conformance failure, traceable to a 135.1 clause."""

    clause: str
    step: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None
    request: Optional[str] = None
    response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestResult:
    clause: str
    title: str
    module: str
    status: Status = Status.PASS
    started: Optional[str] = None
    duration: float = 0.0
    steps: List[str] = field(default_factory=list)
    defects: List[Defect] = field(default_factory=list)
    reason: Optional[str] = None

    __test__ = False  # keep pytest from collecting this class

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class RunReport:
    tool_version: str
    edition: str
    started: str
    finished: Optional[str] = None
    iut: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    results: List[TestResult] = field(default_factory=list)

    def summary(self) -> Dict[str, int]:
        counts = {status.value: 0 for status in Status}
        for result in self.results:
            counts[result.status.value] += 1
        counts["TOTAL"] = len(self.results)
        return counts

    @property
    def passed(self) -> bool:
        return all(r.status in (Status.PASS, Status.SKIP) for r in self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "edition": self.edition,
            "started": self.started,
            "finished": self.finished,
            "iut": self.iut,
            "config": self.config,
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }
