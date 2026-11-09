# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.8 GetEventInformation Service Execution Tests."""

from __future__ import annotations

from typing import List, Optional, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack, GetEventInformationACK, GetEventInformationRequest
from bacpypes3.primitivedata import ObjectIdentifier

from ..context import TestContext
from ..registry import conformance_test
from ._common import all_objects, register_manual

SERVICE = ["get-event-information"]


async def _events(ctx: TestContext) -> List[Tuple[ObjectIdentifier, str, Optional[List[int]]]]:
    """Objects with a non-NORMAL Event_State or an unacknowledged transition."""
    found = []
    for objid in all_objects(ctx):
        if "event-state" not in ctx.model_properties(objid):
            continue
        try:
            state = str(await ctx.read(objid, "event-state"))
        except ErrorRejectAbortNack:
            continue
        acked = None
        if "acked-transitions" in ctx.model_properties(objid):
            try:
                acked = [int(bit) for bit in await ctx.read(objid, "acked-transitions")]
            except ErrorRejectAbortNack:
                acked = None
        offnormal = state != "normal"
        unacked = acked is not None and 0 in acked
        if offnormal or unacked:
            found.append((objid, state, acked))
    return found


async def _ask(ctx: TestContext, last: Optional[ObjectIdentifier] = None):
    request = GetEventInformationRequest(destination=ctx.iut.address)
    if last is not None:
        request.lastReceivedObjectIdentifier = last
    ack = await ctx.expect_ack(request, GetEventInformationACK)
    return ack


@conformance_test("9.8.1", "Event Information with no Active Events", services=SERVICE)
async def no_active_events(ctx: TestContext) -> None:
    active = await _events(ctx)
    if active:
        ctx.skip(f"IUT has {len(active)} active event state(s)")
    ctx.step("1. TRANSMIT GetEventInformation-Request")
    ack = await _ask(ctx)
    if ack is None:
        return
    ctx.step("2. RECEIVE GetEventInformation-ACK, empty list, More Events = FALSE")
    ctx.check(not list(ack.listOfEventSummaries), "list of event summaries is not empty",
        actual=len(ack.listOfEventSummaries))
    ctx.check(not bool(ack.moreEvents), "More Events is not FALSE", actual=ack.moreEvents)


@conformance_test("9.8.2", "Event Information with one Active Event", services=SERVICE)
async def one_active_event(ctx: TestContext) -> None:
    active = await _events(ctx)
    if len(active) != 1:
        ctx.skip(f"IUT has {len(active)} active event state(s); this test needs exactly one")
    ctx.step("1. TRANSMIT GetEventInformation-Request")
    ack = await _ask(ctx)
    if ack is None:
        return
    ctx.step("2. RECEIVE one summary, More Events = FALSE")
    summaries = list(ack.listOfEventSummaries)
    ctx.check(len(summaries) == 1, "expected one event summary", expected=1, actual=len(summaries))
    ctx.check(not bool(ack.moreEvents), "More Events is not FALSE", actual=ack.moreEvents)
    if summaries:
        ctx.check_equal(summaries[0].objectIdentifier, active[0][0], "summary is not the active object")


@conformance_test("9.8.3", "Event Information with Multiple Active Events", services=SERVICE)
async def multiple_active_events(ctx: TestContext) -> None:
    capable = [o for o in all_objects(ctx) if "event-state" in ctx.model_properties(o)]
    if len(capable) < 2:
        ctx.skip("the IUT does not contain more than one object that can detect alarms")
    active = await _events(ctx)
    if len(active) < 2:
        ctx.skip("the IUT is not configured with more than one active event state")
    ctx.step("1. TRANSMIT GetEventInformation-Request")
    ack = await _ask(ctx)
    if ack is None:
        return
    ctx.step("2. RECEIVE one summary per active event, More Events = FALSE")
    if bool(ack.moreEvents):
        ctx.skip("the response set More Events; 9.8.3 requires a single APDU")
    got = {item.objectIdentifier for item in ack.listOfEventSummaries}
    ctx.check(got == {item[0] for item in active}, "summaries do not match the active events",
        expected=len(active), actual=len(got))


@conformance_test("9.8.4", "Event Information Based on Event_State", services=SERVICE)
async def based_on_event_state(ctx: TestContext) -> None:
    active = await _events(ctx)
    matched = [item for item in active if item[1] != "normal" and item[2] is not None and 0 not in item[2]]
    if len(active) != 1 or not matched:
        ctx.skip("the IUT is not configured with one offnormal event whose transitions are all acknowledged")
    ctx.step("1. TRANSMIT GetEventInformation-Request")
    ack = await _ask(ctx)
    if ack is None:
        return
    summaries = list(ack.listOfEventSummaries)
    ctx.check(len(summaries) == 1 and not bool(ack.moreEvents),
        "expected one summary and More Events = FALSE")
    if summaries:
        ctx.check_equal(summaries[0].objectIdentifier, matched[0][0], "summary is not the offnormal object")


@conformance_test("9.8.5", "Event Information Based on Acknowledged_Transitions", services=SERVICE)
async def based_on_acknowledged_transitions(ctx: TestContext) -> None:
    active = await _events(ctx)
    matched = [item for item in active if item[1] == "normal" and item[2] is not None and 0 in item[2]]
    if len(active) != 1 or not matched:
        ctx.skip("the IUT is not configured with one NORMAL object that has an unacknowledged transition")
    ctx.step("1. TRANSMIT GetEventInformation-Request")
    ack = await _ask(ctx)
    if ack is None:
        return
    summaries = list(ack.listOfEventSummaries)
    ctx.check(len(summaries) == 1 and not bool(ack.moreEvents),
        "expected one summary and More Events = FALSE")
    if summaries:
        ctx.check_equal(summaries[0].objectIdentifier, matched[0][0],
            "summary is not the unacknowledged object")


register_manual(
    "9.8.6",
    "Chaining Test",
    "requires more active events than fit in one 50-octet APDU, then clearing the last event of the"
        "first response",
    services=SERVICE,
)
