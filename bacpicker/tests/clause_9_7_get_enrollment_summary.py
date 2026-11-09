# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.7 GetEnrollmentSummary Service Execution Tests."""

from __future__ import annotations

from typing import List, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack, GetEnrollmentSummaryACK, GetEnrollmentSummaryRequest
from bacpypes3.primitivedata import ObjectIdentifier

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["get-enrollment-summary"]


async def _acked(ctx: TestContext) -> List[Tuple[ObjectIdentifier, bool]]:
    """(object, every transition acknowledged) for objects that expose Acked_Transitions."""
    found = []
    for objid in ctx.test_objects():
        if "acked-transitions" not in ctx.model_properties(objid):
            continue
        try:
            bits = [int(bit) for bit in await ctx.read(objid, "acked-transitions")]
        except ErrorRejectAbortNack:
            continue
        found.append((objid, 0 not in bits))
    return found


async def _ask(ctx: TestContext, filt: str):
    ctx.step(f"1. TRANSMIT GetEnrollmentSummary-Request, Acknowledgment Filter = {filt}")
    request = GetEnrollmentSummaryRequest(acknowledgmentFilter=filt, destination=ctx.iut.address)
    ack = await ctx.expect_ack(request, GetEnrollmentSummaryACK)
    if ack is None:
        return None
    ctx.step("2. RECEIVE GetEnrollmentSummary-ACK")
    return list(ack.listOfEnrollmentSummaries)


@conformance_test("9.7.1.1", "Enrollment Summary with Zero Summaries", services=SERVICE)
async def zero_summaries(ctx: TestContext) -> None:
    rows = await _acked(ctx)
    if any(not done for _obj, done in rows):
        ctx.skip("the IUT has an unacknowledged enrollment; it cannot be filtered to an empty"
            "NOT_ACKED summary")
    summaries = await _ask(ctx, "not-acked")
    if summaries is None:
        return
    ctx.check(not summaries, "NOT_ACKED summary is not empty", actual=len(summaries))


@conformance_test("9.7.1.2", "ACKED", services=SERVICE)
async def acked_filter(ctx: TestContext) -> None:
    rows = await _acked(ctx)
    acked = {obj for obj, done in rows if done}
    pending = {obj for obj, done in rows if not done}
    if not acked or not pending:
        ctx.skip("the IUT does not have both an acknowledged and an unacknowledged enrollment")
    summaries = await _ask(ctx, "acked")
    if summaries is None:
        return
    got = {item.objectIdentifier for item in summaries}
    ctx.check(acked <= got and not (got & pending),
        "ACKED filter did not return only acknowledged enrollments", expected=acked, actual=got)


@conformance_test("9.7.1.3", "NOT-ACKED", services=SERVICE)
async def not_acked_filter(ctx: TestContext) -> None:
    rows = await _acked(ctx)
    acked = {obj for obj, done in rows if done}
    pending = {obj for obj, done in rows if not done}
    if not acked or not pending:
        ctx.skip("the IUT does not have both an acknowledged and an unacknowledged enrollment")
    summaries = await _ask(ctx, "not-acked")
    if summaries is None:
        return
    got = {item.objectIdentifier for item in summaries}
    ctx.check(pending <= got and not (got & acked),
        "NOT_ACKED filter did not return only unacknowledged enrollments", expected=pending, actual=got)


@conformance_test("9.7.1.4", "All", services=SERVICE)
async def all_filter(ctx: TestContext) -> None:
    rows = await _acked(ctx)
    if len(rows) < 2:
        ctx.skip("the IUT does not have two enrollments with Acked_Transitions")
    summaries = await _ask(ctx, "all")
    if summaries is None:
        return
    got = {item.objectIdentifier for item in summaries}
    ctx.check({obj for obj, _done in rows} <= got, "ALL filter omitted an enrollment", expected=len(rows),
        actual=len(got))


@conformance_test("9.7.2.1", "Enrollment Filter", services=SERVICE)
async def enrollment_filter(ctx: TestContext) -> None:
    ctx.skip("the tester has no recipient process identifier configured for an enrollment filter")


@conformance_test("9.7.2.2", "Event State Filter", services=SERVICE)
async def event_state_filter(ctx: TestContext) -> None:
    ctx.skip("the IUT is not configured with enrollments in each event state this filter selects")


@conformance_test("9.7.2.3", "Event Type Filter", services=SERVICE)
async def event_type_filter(ctx: TestContext) -> None:
    ctx.skip("the IUT is not configured with enrollments of a known event type for this filter")


@conformance_test("9.7.2.4", "Priority Filter", services=SERVICE)
async def priority_filter(ctx: TestContext) -> None:
    ctx.skip("the IUT is not configured with enrollments inside and outside a known priority range")


@conformance_test("9.7.2.5", "Notification Class Filter", services=SERVICE)
async def notification_class_filter(ctx: TestContext) -> None:
    ctx.skip("the IUT is not configured with enrollments of a known notification class")


@conformance_test("9.7.2.6", "A Combination of Filters", services=SERVICE)
async def combination(ctx: TestContext) -> None:
    ctx.skip("the IUT is not configured with enrollments that match a known combination of filters")

