# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
from types import SimpleNamespace

from bacpypes3.pdu import Address
from bacpypes3.primitivedata import ObjectIdentifier

from bacpicker.config import RunConfig
from bacpicker.context import DeviceProfile
from bacpicker.iut import broadcast_listen_address
from bacpicker.registry import TestCase, clause_sort_key
from bacpicker.reporting.console import ConsoleReporter
from bacpicker.reporting.markdown_html import render_html, render_markdown
from bacpicker.result import Status
from bacpicker.runner import Runner, filter_tests, order_tests


def make_case(clause, func=None, **kwargs):
    async def noop(ctx):
        pass

    return TestCase(clause=clause, title=f"test {clause}", func=func or noop, module="m", **kwargs)


def make_profile(**kwargs):
    return DeviceProfile(
        address=Address("192.0.2.1"),
        device_id=ObjectIdentifier("device,7"),
        vendor_id=999,
        max_apdu_length_accepted=1476,
        segmentation_supported="no-segmentation",
        **kwargs,
    )


def test_clause_sort_is_numeric():
    clauses = ["9.20.1.1", "9.3.1", "9.18.2.10", "9.18.2.2"]
    assert sorted(clauses, key=clause_sort_key) == ["9.3.1", "9.18.2.2", "9.18.2.10", "9.20.1.1"]


def test_include_exclude_patterns():
    tests = [make_case(c) for c in ("9.18.1.1", "9.18.2.1", "9.20.1.1")]
    config = RunConfig(include=["9.18.*"], exclude=["9.18.2.1"])
    assert [t.clause for t in filter_tests(tests, config)] == ["9.18.1.1"]


def test_dependencies_run_first():
    tests = [make_case("9.1", depends_on=["9.2"]), make_case("9.2")]
    assert [t.clause for t in order_tests(tests)] == ["9.2", "9.1"]


async def test_skip_reasons():
    profile = make_profile(services_supported={"read-property"})
    runner = Runner(None, profile, RunConfig())
    results = {}
    cases = [
        make_case("1", services=["read-property-multiple"]),
        make_case("2", object_types=["analog-input"]),
        make_case("3", writes=True),
        make_case("4", services=["read-property"]),
    ]
    out = [await runner.run_one(c, results) for c in cases]
    assert [r.status for r in out] == [Status.SKIP, Status.SKIP, Status.SKIP, Status.PASS]
    assert "read-property-multiple" in (out[0].reason or "")
    assert "--allow-writes" in (out[2].reason or "")


async def test_defects_fail_and_exceptions_error():
    async def failing(ctx):
        ctx.step("compare")
        ctx.check_equal(1, 2, "values differ")

    async def crashing(ctx):
        raise RuntimeError("boom")

    runner = Runner(None, make_profile(), RunConfig())
    fail = await runner.run_one(make_case("9.1", failing), {})
    assert fail.status is Status.FAIL
    (defect,) = fail.defects
    assert (defect.clause, defect.step, defect.expected, defect.actual) == ("9.1", "compare", "2", "1")

    error = await runner.run_one(make_case("9.2", crashing), {})
    assert error.status is Status.ERROR and "boom" in (error.reason or "")

    blocked = await runner.run_one(make_case("9.3", depends_on=["9.1"]), {"9.1": fail})
    assert blocked.status is Status.SKIP and "9.1" in (blocked.reason or "")


async def test_reporters_render_defects():
    async def failing(ctx):
        ctx.step("compare")
        ctx.check_equal("<a>", "b", "values differ")

    stream = io.StringIO()
    runner = Runner(None, make_profile(), RunConfig(), [ConsoleReporter(stream)])
    report = await runner.run([make_case("9.1", failing)])
    console = stream.getvalue()
    assert "FAIL  9.1" in console and "DEFECT [9.1] values differ" in console
    assert "values differ" in render_markdown(report)
    html = render_html(report)
    assert "&lt;a&gt;" in html and "<a>" not in html


def test_broadcast_listen_address_per_platform():
    server = SimpleNamespace(local_address=("192.0.2.10", 47823), broadcast_address=("192.0.2.255", 47808))
    assert broadcast_listen_address(server, windows=False) == (("192.0.2.255", 47808), True)
    # Windows has no SO_REUSEPORT and receives broadcasts on the unicast address
    assert broadcast_listen_address(server, windows=True) == (("192.0.2.10", 47808), False)
