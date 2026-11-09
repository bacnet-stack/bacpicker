# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.6 GetAlarmSummary Service Execution Tests."""

from __future__ import annotations

from typing import List

from bacpypes3.apdu import ErrorRejectAbortNack, GetAlarmSummaryACK, GetAlarmSummaryRequest
from bacpypes3.primitivedata import ObjectIdentifier

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["get-alarm-summary"]


async def _active(ctx: TestContext) -> List[ObjectIdentifier]:
    """Objects whose Event_State is present and not NORMAL."""
    active = []
    for objid in ctx.test_objects():
        if "event-state" not in ctx.model_properties(objid):
            continue
        try:
            state = str(await ctx.read(objid, "event-state"))
        except ErrorRejectAbortNack:
            continue
        if state != "normal":
            active.append(objid)
    return active


async def _summary(ctx: TestContext):
    ctx.step("1. TRANSMIT GetAlarmSummary-Request")
    ack = await ctx.expect_ack(GetAlarmSummaryRequest(destination=ctx.iut.address), GetAlarmSummaryACK)
    if ack is None:
        return None
    ctx.step("2. RECEIVE GetAlarmSummary-ACK")
    return list(ack.listOfAlarmSummaries)


@conformance_test("9.6.1", "Alarm Summaries with no Active Alarms", services=SERVICE)
async def no_active_alarms(ctx: TestContext) -> None:
    active = await _active(ctx)
    if active:
        ctx.skip(f"IUT has {len(active)} object(s) whose Event_State is not NORMAL")
    summaries = await _summary(ctx)
    if summaries is None:
        return
    ctx.check(not summaries, "List of Alarm Summaries is not empty", expected="[]", actual=len(summaries))


@conformance_test("9.6.2", "Alarm Summaries with One Active Alarm", services=SERVICE)
async def one_active_alarm(ctx: TestContext) -> None:
    active = await _active(ctx)
    if len(active) != 1:
        ctx.skip(f"IUT has {len(active)} active Event_State values; this test needs exactly one")
    summaries = await _summary(ctx)
    if summaries is None:
        return
    ctx.check(len(summaries) == 1, "expected one alarm summary", expected=1, actual=len(summaries))
    if summaries:
        ctx.check_equal(summaries[0].objectIdentifier, active[0], "summary is not the active object")


@conformance_test("9.6.3", "Alarm Summaries with Multiple Active Alarms", services=SERVICE)
async def multiple_active_alarms(ctx: TestContext) -> None:
    alarming = [o for o in ctx.test_objects() if "event-state" in ctx.model_properties(o)]
    if len(alarming) < 2:
        ctx.skip("the IUT does not contain more than one object that can detect alarms")
    active = await _active(ctx)
    if len(active) < 2:
        ctx.skip(f"IUT has {len(active)} active Event_State values; this test needs more than one")
    summaries = await _summary(ctx)
    if summaries is None:
        return
    got = {item.objectIdentifier for item in summaries}
    ctx.check(got == set(active), "alarm summaries do not match the active objects", expected=active,
        actual=got)
