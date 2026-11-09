# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.10 SubscribeCOV Service Execution Tests."""

from __future__ import annotations

import asyncio
from typing import Optional

from bacpypes3.apdu import (
    ConfirmedCOVNotificationRequest,
    ErrorPDU,
    ErrorRejectAbortNack,
    SubscribeCOVRequest,
    UnconfirmedCOVNotificationRequest,
)
from bacpypes3.primitivedata import ObjectIdentifier, Unsigned

from ..assertions import error_class_code, format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import expect_simple_ack, register_manual

SERVICE = ["subscribe-cov"]
_PID = 1001
_PROBE_PID = _PID + 9
_COV_OBJECT = "9.10 cov object"
# object types that commonly report COV; they are probed first
_COV_TYPES = (
    "analog-input", "analog-output", "analog-value", "binary-input", "binary-output", "binary-value",
    "multi-state-input", "multi-state-output", "multi-state-value",
)


def _request(
    ctx: TestContext,
    objid: ObjectIdentifier,
    confirmed: Optional[bool],
    lifetime: Optional[int],
    pid: int = _PID,
) -> SubscribeCOVRequest:
    request = SubscribeCOVRequest(
        subscriberProcessIdentifier=pid,
        monitoredObjectIdentifier=objid,
        destination=ctx.iut.address,
    )
    if confirmed is not None:
        request.issueConfirmedNotifications = confirmed
    if lifetime is not None:
        request.lifetime = lifetime
    return request


async def _notification(ctx: TestContext, objid: ObjectIdentifier, confirmed: bool, request) -> bool:
    """Subscribe, then wait Notification Fail Time for the initial notification."""
    found = []
    got = asyncio.Event()

    def listener(apdu) -> None:
        if confirmed and not isinstance(apdu, ConfirmedCOVNotificationRequest):
            return
        if not confirmed and not isinstance(apdu, UnconfirmedCOVNotificationRequest):
            return
        if apdu.monitoredObjectIdentifier == objid and int(apdu.subscriberProcessIdentifier) == int(
            request.subscriberProcessIdentifier
        ):
            found.append(apdu)
            got.set()

    ctx.app.add_listener(listener)
    try:
        ctx.step("1. TRANSMIT SubscribeCOV-Request")
        ctx.step("2. RECEIVE BACnet-SimpleACK-PDU")
        if not await expect_simple_ack(ctx, request):
            return False
        ctx.step("3. BEFORE Notification Fail Time RECEIVE COV notification")
        try:
            await asyncio.wait_for(got.wait(), ctx.config.internal_processing_fail_time)
        except asyncio.TimeoutError:
            ctx.defect(
                "No COV notification before Notification Fail Time",
                expected=f"COV notification for {objid}",
                actual="no notification",
                request=request,
            )
            return False
    finally:
        ctx.app.remove_listener(listener)
    note = found[0]
    ctx.check_equal(note.initiatingDeviceIdentifier, ctx.iut.device_id,
        "Initiating Device Identifier is not the IUT")
    return True


async def _cancel(ctx: TestContext, objid: ObjectIdentifier, pid: int) -> None:
    """Cancel a subscription the tester made. A failed cancel is recorded; it is not part of the
    135.1 procedure."""
    request = _request(ctx, objid, None, None, pid=pid)
    try:
        await ctx.send(request)
    except ErrorRejectAbortNack as err:
        ctx.defect(f"Could not cancel COV subscription {pid} for {objid}", expected="BACnet-SimpleACK-PDU",
            actual=format_pdu(err), request=request, response=err)


async def _cov_object(ctx: TestContext) -> ObjectIdentifier:
    """An object that accepts a COV subscription, found by subscribing and then cancelling.

    SubscribeCOV support is device-wide; it does not mean every object supports COV, so the
    object type alone does not establish the 135.1 "object supporting COV notifications".
    """
    if _COV_OBJECT in ctx.shared:
        found = ctx.shared[_COV_OBJECT]
        if found is None:
            ctx.skip("no object accepted a SubscribeCOV probe, so no COV-capable object is known")
        return found
    candidates = sorted(
        (o for o in ctx.test_objects() if o != ctx.iut.device_id),
        key=lambda o: str(o[0]) not in _COV_TYPES,
    )
    for objid in candidates:
        try:
            await ctx.send(_request(ctx, objid, False, 60, pid=_PROBE_PID))
        except ErrorRejectAbortNack:
            continue
        await _cancel(ctx, objid, _PROBE_PID)
        ctx.note(f"{objid} accepted a SubscribeCOV probe; using it as the monitored object")
        ctx.shared[_COV_OBJECT] = objid
        return objid
    ctx.shared[_COV_OBJECT] = None
    ctx.skip("no object accepted a SubscribeCOV probe, so no COV-capable object is known")


@conformance_test("9.10.1.1", "Confirmed COV Notifications", services=SERVICE)
async def confirmed_notifications(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    ctx.shared["9.10.1.1"] = (_PID, objid)
    ok = await _notification(ctx, objid, True, _request(ctx, objid, True, 60))
    if not ok:
        ctx.shared.pop("9.10.1.1", None)


@conformance_test("9.10.1.2", "Unconfirmed COV Notifications", services=SERVICE)
async def unconfirmed_notifications(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    await _notification(ctx, objid, False, _request(ctx, objid, False, 60, pid=_PID + 1))


@conformance_test("9.10.1.3", "Explicit Indefinite Lifetime COV Subscriptions", services=SERVICE)
async def explicit_indefinite(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    pid = _PID + 2
    try:
        await _notification(ctx, objid, False, _request(ctx, objid, False, 0, pid=pid))
    finally:
        ctx.note("cleanup: cancel the indefinite subscription")
        await _cancel(ctx, objid, pid)


@conformance_test(
    "9.10.1.4", "Canceling COV Subscriptions", services=SERVICE, depends_on=["9.10.1.1"]
)
async def canceling(ctx: TestContext) -> None:
    saved = ctx.shared.get("9.10.1.1")
    if not saved:
        ctx.skip("9.10.1.1 did not record a subscription")
    pid, objid = saved
    ctx.step("1. TRANSMIT SubscribeCOV-Request with no lifetime (cancel)")
    ctx.step("2. RECEIVE BACnet-SimpleACK-PDU")
    await expect_simple_ack(ctx, _request(ctx, objid, None, None, pid=pid))


@conformance_test("9.10.1.5", "Canceling Expired or Non-Existing Subscriptions", services=SERVICE)
async def cancel_missing(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    ctx.step("1. TRANSMIT SubscribeCOV-Request cancelling a process identifier that was never subscribed")
    ctx.step("2. RECEIVE BACnet-SimpleACK-PDU")
    await expect_simple_ack(ctx, _request(ctx, objid, None, None, pid=4000000))


@conformance_test("9.10.1.6", "Implied Indefinite Lifetime COV Subscriptions", services=SERVICE)
async def implied_indefinite(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    pid = _PID + 3
    try:
        await _notification(ctx, objid, True, _request(ctx, objid, True, None, pid=pid))
    finally:
        ctx.note("cleanup: cancel the indefinite subscription")
        await _cancel(ctx, objid, pid)


register_manual(
    "9.10.1.7",
    "Finite Lifetime Subscriptions",
    "requires changing the monitored object (MAKE) to check that Time Remaining decreases over a"
        " 60 to 300 second lifetime",
    services=SERVICE,
    writes=True,
)


register_manual(
    "9.10.1.8",
    "Updating Existing Subscriptions",
    "requires observing that an updated subscription replaces the lifetime and confirmation mode of"
        "an existing one",
    services=SERVICE,
)
register_manual(
    "9.10.1.9",
    "Ensuring Subscription Lifetimes Are Not Affected By Time Changes",
    "requires changing the IUT clock while a subscription is active",
    services=SERVICE,
)
register_manual(
    "9.10.1.10",
    "Accepts 8 Hour Lifetimes",
    "requires waiting out an 8 hour subscription lifetime",
    services=SERVICE,
)
register_manual(
    "9.10.1.11",
    "Ensuring 5 Concurrent COV Subscribers",
    "requires five concurrent subscribers and a value change that notifies all of them",
    services=SERVICE,
    writes=True,
)


@conformance_test("9.10.2.1", "The Monitored Object Does Not Support COV Notification", services=SERVICE)
async def object_without_cov(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT SubscribeCOV-Request for the Device object")
    request = _request(ctx, device, True, 60, pid=_PID + 5)
    try:
        await ctx.send(request)
    except ErrorPDU as err:
        ctx.step("2. RECEIVE an error: the object does not support COV")
        allowed = {
            ("object", "optional-functionality-not-supported"),
            ("services", "service-request-denied"),
            ("services", "other"),
            ("property", "not-cov-property"),
        }
        pair = tuple(str(part) for part in error_class_code(err))
        revision = ctx.iut.protocol_revision
        if revision is not None and revision >= 10:
            allowed = {("object", "optional-functionality-not-supported")}
        ctx.check(pair in allowed, "Wrong error for an object that does not support COV",
            expected=allowed, actual=pair, response=err)
        return
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected an Error PDU", actual=format_pdu(err), request=request, response=err)
        return
    ctx.skip("the Device object accepted a COV subscription; no object that refuses COV was selected")


@conformance_test("9.10.2.2", "The Monitored Object Does Not Exist", services=SERVICE)
async def object_does_not_exist(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT SubscribeCOV-Request for {objid}")
    request = _request(ctx, objid, True, 60, pid=_PID + 6)
    revision = ctx.iut.protocol_revision
    if revision is not None and revision >= 10:
        ctx.step("2. RECEIVE OBJECT / UNKNOWN_OBJECT")
        await ctx.expect_error(request, ("object", "unknown-object"))
    else:
        ctx.step("2. RECEIVE UNKNOWN_OBJECT or SERVICE_REQUEST_DENIED or OTHER")
        await ctx.expect_error(
            request,
            ("object", "unknown-object"),
            ("services", "service-request-denied"),
            ("services", "other"),
        )


register_manual(
    "9.10.2.3",
    "There Is No Space For A Subscription",
    "requires filling the IUT subscription table; the limit is not known and may be up to 10000",
    services=SERVICE,
    min_protocol_revision=10,
)


@conformance_test("9.10.2.4", "The Lifetime Parameter is Out of Range", services=SERVICE)
async def lifetime_out_of_range(ctx: TestContext) -> None:
    objid = await _cov_object(ctx)
    ctx.step("1. TRANSMIT SubscribeCOV-Request, Lifetime = 4294967294")
    request = _request(ctx, objid, True, 4294967294, pid=_PID + 7)
    revision = ctx.iut.protocol_revision
    if revision is not None and revision >= 10:
        ctx.step("2. RECEIVE SERVICES / VALUE_OUT_OF_RANGE")
        await ctx.expect_error(request, ("services", "value-out-of-range"))
    else:
        ctx.step("2. RECEIVE VALUE_OUT_OF_RANGE, SERVICE_REQUEST_DENIED, OTHER, or Reject"
            "PARAMETER_OUT_OF_RANGE")
        from bacpypes3.apdu import RejectPDU

        try:
            await ctx.send(request)
        except RejectPDU as err:
            ctx.check(str(err.apduAbortRejectReason) == "parameter-out-of-range", "Wrong reject reason",
                response=err)
            return
        except ErrorPDU as err:
            pair = tuple(str(part) for part in error_class_code(err))
            ctx.check(
                pair in {("services", "value-out-of-range"), ("services", "service-request-denied"),
                    ("services", "other")},
                "Wrong error",
                actual=pair,
                response=err,
            )
            return
        ctx.defect("Out-of-range lifetime was accepted", request=request)


@conformance_test("9.10.3.1", "Unsubscribed COVNotification Execution Test",
    services=["unconfirmed-cov-notification"])
async def unsubscribed_cov(ctx: TestContext) -> None:
    from bacpypes3.apdu import UnconfirmedCOVNotificationRequest
    from bacpypes3.basetypes import PropertyValue

    ctx.step("1. TRANSMIT UnconfirmedCOVNotification-Request, Process Identifier = 0")
    request = UnconfirmedCOVNotificationRequest(
        subscriberProcessIdentifier=0,
        initiatingDeviceIdentifier=ctx.app.device_object.objectIdentifier,
        monitoredObjectIdentifier=ctx.app.device_object.objectIdentifier,
        timeRemaining=0,
        listOfValues=[PropertyValue(propertyIdentifier="system-status", value=Unsigned(0))],
        destination=ctx.iut.address,
    )
    await ctx.app.request(request)
    ctx.step("2. CHECK vendor-defined observable actions")
    ctx.note("no vendor-defined action is declared for an unsubscribed COV notification")
