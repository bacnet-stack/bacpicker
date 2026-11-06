# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Selects applicable tests, runs them in order and collects results."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack

from . import STANDARD_EDITION, __version__
from .assertions import SkipTest, TestAborted, format_pdu
from .config import RunConfig
from .context import DeviceProfile, TestContext
from .registry import TestCase
from .result import RunReport, Status, TestResult

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _matches(clause: str, patterns: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(clause, p) or clause == p for p in patterns)


def filter_tests(tests: Sequence[TestCase], config: RunConfig) -> List[TestCase]:
    """Apply --include / --exclude clause patterns (shell-style, e.g. '9.18.*')."""
    selected = [t for t in tests if not config.include or _matches(t.clause, config.include)]
    return [t for t in selected if not _matches(t.clause, config.exclude)]


def order_tests(tests: Sequence[TestCase]) -> List[TestCase]:
    """Clause order, with dependencies moved ahead of the tests that need them."""
    by_clause = {t.clause: t for t in tests}
    ordered: List[TestCase] = []
    visiting: set = set()

    def visit(test: TestCase) -> None:
        if test in ordered:
            return
        if test.clause in visiting:
            raise ValueError(f"circular test dependency at {test.clause}")
        visiting.add(test.clause)
        for dep in test.depends_on:
            if dep in by_clause:
                visit(by_clause[dep])
        visiting.discard(test.clause)
        ordered.append(test)

    for test in sorted(tests, key=lambda t: t.sort_key):
        visit(test)
    return ordered


def applicability(
    test: TestCase, profile: DeviceProfile, config: RunConfig, results: Dict[str, TestResult]
) -> Optional[str]:
    """Return a skip reason, or None if the test should run."""
    if test.manual:
        return f"not automated: {test.manual}"
    if test.writes and not config.allow_writes:
        return "test modifies the IUT; run with --allow-writes to enable"
    if test.min_protocol_revision is not None and (
        profile.protocol_revision is None or profile.protocol_revision < test.min_protocol_revision
    ):
        return (
            f"applies only when Protocol_Revision is present and >= {test.min_protocol_revision}"
            f" (IUT: {profile.protocol_revision})"
        )
    missing = [s for s in test.services if not profile.supports_service(s)]
    if missing:
        return "IUT does not support service(s): " + ", ".join(missing)
    missing = [o for o in test.object_types if not profile.supports_object_type(o)]
    if missing:
        return "IUT does not support object type(s): " + ", ".join(missing)
    for dep in test.depends_on:
        dep_result = results.get(dep)
        if dep_result is not None and dep_result.status is not Status.PASS:
            return f"prerequisite test {dep} did not pass ({dep_result.status.value})"
    return None


class Runner:
    def __init__(
        self,
        app: Any,
        profile: DeviceProfile,
        config: RunConfig,
        reporters: Sequence[Any] = (),
        shared: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.app = app
        self.profile = profile
        self.config = config
        self.reporters = list(reporters)
        self.shared: Dict[str, Any] = shared if shared is not None else {}

    def _emit(self, event: str, *args: Any) -> None:
        for reporter in self.reporters:
            getattr(reporter, event)(*args)

    async def run(self, tests: Sequence[TestCase]) -> RunReport:
        tests = order_tests(filter_tests(tests, self.config))
        report = RunReport(
            tool_version=__version__,
            edition=STANDARD_EDITION,
            started=_now(),
            iut=self.profile.to_dict(),
            config=self.config.to_dict(),
        )
        self._emit("start", report, tests)
        results: Dict[str, TestResult] = {}
        for test in tests:
            self._emit("test_started", test)
            result = await self.run_one(test, results)
            results[test.clause] = result
            report.results.append(result)
            self._emit("test_finished", result)
        report.finished = _now()
        self._emit("finish", report)
        return report

    async def run_one(self, test: TestCase, results: Dict[str, TestResult]) -> TestResult:
        result = TestResult(
            clause=test.clause, title=test.title, module=test.module, started=_now()
        )
        reason = applicability(test, self.profile, self.config, results)
        if reason:
            result.status, result.reason = Status.SKIP, reason
            return result

        ctx = TestContext(self.app, self.profile, self.config, test, result, self.shared)
        start = time.monotonic()
        status, reason = await self._execute(test, ctx)
        result.duration = round(time.monotonic() - start, 3)
        if status is Status.PASS and result.defects:
            status = Status.FAIL
        result.status, result.reason = status, reason
        return result

    async def _execute(self, test: TestCase, ctx: TestContext) -> Tuple[Status, Optional[str]]:
        try:
            await asyncio.wait_for(test.func(ctx), timeout=self.config.test_timeout)
        except SkipTest as err:
            return Status.SKIP, str(err)
        except TestAborted as err:
            return Status.FAIL, f"aborted: {err}"
        except asyncio.TimeoutError:
            return Status.ERROR, f"test exceeded {self.config.test_timeout}s timeout"
        except ErrorRejectAbortNack as err:
            # a test sent a request without handling an Error/Reject/Abort response
            ctx.defect("Unexpected Error/Reject/Abort from IUT", actual=format_pdu(err))
            return Status.FAIL, None
        except Exception as err:
            log.debug("test %s raised", test.clause, exc_info=True)
            return Status.ERROR, f"{type(err).__name__}: {err}\n{traceback.format_exc()}"
        return Status.PASS, None
