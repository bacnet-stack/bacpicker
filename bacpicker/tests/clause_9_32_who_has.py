# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.32 Who-Has Service Execution Tests."""

from __future__ import annotations

import uuid
from typing import Optional, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack, IHaveRequest, WhoHasLimits, WhoHasObject, WhoHasRequest
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier

from ..assertions import format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import MAX_INSTANCE, iut_instance_ranges, rp_request

SERVICES = ["who-has"]
REMOTE = (
    "requires the TD to originate the request from a simulated remote network "
    "(SNET/SADR) and to act as the router for the response"
)


def _who_has(
    destination: Address,
    *,
    object_id: Optional[ObjectIdentifier] = None,
    object_name: Optional[str] = None,
    limits: Optional[Tuple[int, int]] = None,
) -> WhoHasRequest:
    request = WhoHasRequest(destination=destination)
    if limits is not None:
        request.limits = WhoHasLimits(
            deviceInstanceRangeLowLimit=limits[0], deviceInstanceRangeHighLimit=limits[1]
        )
    if object_id is not None:
        request.object = WhoHasObject(objectIdentifier=object_id)
    else:
        request.object = WhoHasObject(objectName=CharacterString(object_name))
    return request


def _from_iut(ctx: TestContext):
    return lambda apdu: isinstance(apdu, IHaveRequest) and apdu.deviceIdentifier == ctx.iut.device_id


async def _object1(ctx: TestContext) -> Tuple[ObjectIdentifier, str]:
    """Configuration Requirements: choose any object (Object1); step 1 READ V1 = Object_Name."""
    candidates = [o for o in ctx.iut.object_list if o != ctx.iut.device_id]
    object1 = candidates[0] if candidates else ctx.iut.device_id
    ctx.step(f"1. READ V1 = ({object1}), Object_Name")
    return object1, str(await ctx.read(object1, "object-name"))


async def _receive_i_have(
    ctx: TestContext, request: WhoHasRequest, step: str, object1: ObjectIdentifier, v1: str
) -> None:
    """BEFORE Unconfirmed Response Fail Time RECEIVE I-Have (IUT, Object1, V1)."""
    ctx.step(f"{step}. BEFORE Unconfirmed Response Fail Time RECEIVE I-Have-Request "
             f"(IUT device, {object1}, '{v1}')")
    i_haves = await ctx.collect(
        request, _from_iut(ctx), ctx.config.unconfirmed_response_fail_time, first_only=True
    )
    if not ctx.check(
        bool(i_haves),
        "No I-Have received from the IUT before the Unconfirmed Response Fail Time",
        expected=f"I-Have {ctx.iut.device_id}, {object1}, '{v1}'",
        actual="no I-Have",
        request=request,
    ):
        return
    i_have = i_haves[0]
    ctx.check(
        i_have.objectIdentifier == object1,
        "I-Have 'Object Identifier' is incorrect",
        expected=object1,
        actual=i_have.objectIdentifier,
        response=i_have,
    )
    ctx.check(
        str(i_have.objectName) == v1,
        "I-Have 'Object Name' is incorrect",
        expected=v1,
        actual=i_have.objectName,
        response=i_have,
    )


async def _no_response(
    ctx: TestContext, request: WhoHasRequest, step: str, wait: float, wait_name: str, match=None
) -> None:
    """WAIT <fail time>; CHECK (verify that the IUT does not respond)."""
    ctx.step(f"{step}. WAIT {wait_name}; CHECK (the IUT does not respond)")
    i_haves = await ctx.collect(request, match or _from_iut(ctx), wait)
    ctx.check(
        not i_haves,
        "IUT responded with I-Have when it shall not",
        expected="no I-Have",
        actual=f"{len(i_haves)} I-Have",
        request=request,
        response=i_haves[0] if i_haves else None,
    )


def _range(ctx: TestContext, key: str) -> Tuple[int, int]:
    limits = iut_instance_ranges(ctx)[key]
    if limits is None:
        ctx.skip(f"no valid device range of this form exists for instance {ctx.iut.device_instance}")
    return limits


def _outside_range(ctx: TestContext) -> Tuple[int, int]:
    """Low Limit > 0, High Limit > Low Limit, IUT instance not in the range."""
    x = ctx.iut.device_instance
    if x + 1 < MAX_INSTANCE:
        return x + 1, MAX_INSTANCE
    if x > 2:
        return 1, x - 1
    ctx.skip("no device range excluding the IUT satisfies Low Limit > 0")


# ---- 9.32.1 Who-Has requests originating from the local network ------------


@conformance_test("9.32.1.1", "Object ID Version with No Device Range", services=SERVICES)
async def object_id_no_range(ctx: TestContext) -> None:
    object1, v1 = await _object1(ctx)
    ctx.step(f"2. TRANSMIT DA = LOCAL BROADCAST, Who-Has-Request 'Object Identifier' = {object1}")
    request = _who_has(ctx.destination("local"), object_id=object1)
    await _receive_i_have(ctx, request, "3", object1, v1)


@conformance_test("9.32.1.2", "Object Name Version with no Device Range", services=SERVICES)
async def object_name_no_range(ctx: TestContext) -> None:
    object1, v1 = await _object1(ctx)
    ctx.step(f"2. TRANSMIT DA = LOCAL BROADCAST, Who-Has-Request 'Object Name' = '{v1}'")
    request = _who_has(ctx.destination("local"), object_name=v1)
    await _receive_i_have(ctx, request, "3", object1, v1)


async def _in_range(ctx: TestContext, key: str, by_name: bool) -> None:
    limits = _range(ctx, key)
    object1, v1 = await _object1(ctx)
    what = f"'Object Name' = '{v1}'" if by_name else f"'Object Identifier' = {object1}"
    ctx.step(f"2. TRANSMIT DA = LOCAL BROADCAST, Who-Has-Request Low = {limits[0]}, "
             f"High = {limits[1]}, {what}")
    request = _who_has(
        ctx.destination("local"),
        object_name=v1 if by_name else None,
        object_id=None if by_name else object1,
        limits=limits,
    )
    await _receive_i_have(ctx, request, "3", object1, v1)


@conformance_test("9.32.1.3", "Object ID Version with IUT Inside of the Device Range", services=SERVICES)
async def object_id_inside_range(ctx: TestContext) -> None:
    await _in_range(ctx, "inside", by_name=False)


@conformance_test("9.32.1.4", "Object ID Version with IUT Outside of the Device Range", services=SERVICES)
async def object_id_outside_range(ctx: TestContext) -> None:
    limits = _outside_range(ctx)
    candidates = [o for o in ctx.iut.object_list if o != ctx.iut.device_id]
    object1 = candidates[0] if candidates else ctx.iut.device_id
    ctx.step(f"1. TRANSMIT DA = LOCAL BROADCAST, Who-Has-Request Low = {limits[0]}, "
             f"High = {limits[1]}, 'Object Identifier' = {object1}")
    request = _who_has(ctx.destination("local"), object_id=object1, limits=limits)
    await _no_response(
        ctx, request, "2-3", ctx.config.unconfirmed_response_fail_time,
        "Unconfirmed Response Fail Time",
    )


@conformance_test("9.32.1.5", "Object Name Version with IUT Inside of the Device Range", services=SERVICES)
async def object_name_inside_range(ctx: TestContext) -> None:
    await _in_range(ctx, "inside", by_name=True)


@conformance_test("9.32.1.6", "Object Name Version with IUT Outside of the Device Range", services=SERVICES)
async def object_name_outside_range(ctx: TestContext) -> None:
    limits = _outside_range(ctx)
    name = ctx.iut.object_name or str(await ctx.read(ctx.iut.device_id, "object-name"))
    ctx.step(f"1. TRANSMIT DA = LOCAL BROADCAST, Who-Has-Request Low = {limits[0]}, "
             f"High = {limits[1]}, 'Object Name' = '{name}'")
    request = _who_has(ctx.destination("local"), object_name=name, limits=limits)
    await _no_response(
        ctx, request, "2-3", ctx.config.internal_processing_fail_time,
        "Internal Processing Fail Time",
    )


@conformance_test(
    "9.32.1.7",
    "Object ID Version with IUT Device Instance Equal to the High Limit of the Device Range",
    services=SERVICES,
)
async def object_id_high_limit(ctx: TestContext) -> None:
    await _in_range(ctx, "high_equal", by_name=False)


@conformance_test(
    "9.32.1.8",
    "Object ID Version with IUT Device Instance Equal to the Low Limit of the Device Range",
    services=SERVICES,
)
async def object_id_low_limit(ctx: TestContext) -> None:
    await _in_range(ctx, "low_equal", by_name=False)


@conformance_test(
    "9.32.1.9",
    "Object Name Version with IUT Device Instance Equal to the High Limit of the Device Range",
    services=SERVICES,
)
async def object_name_high_limit(ctx: TestContext) -> None:
    await _in_range(ctx, "high_equal", by_name=True)


@conformance_test(
    "9.32.1.10",
    "Object Name Version with IUT Device Instance Equal to the Low Limit of the Device Range",
    services=SERVICES,
)
async def object_name_low_limit(ctx: TestContext) -> None:
    await _in_range(ctx, "low_equal", by_name=True)


@conformance_test(
    "9.32.1.11", "Object Name Version, Directed to a Specific MAC Address", services=SERVICES
)
async def object_name_directed(ctx: TestContext) -> None:
    object1, v1 = await _object1(ctx)
    ctx.step(f"2. TRANSMIT (directed to the IUT) Who-Has-Request 'Object Name' = '{v1}'")
    request = _who_has(ctx.destination("iut"), object_name=v1)
    await _receive_i_have(ctx, request, "3", object1, v1)


async def _write(ctx: TestContext, objid: ObjectIdentifier, prop: str, value) -> Optional[str]:
    """WriteProperty; returns the error text if the IUT refuses."""
    try:
        await ctx.app.write_property(ctx.iut.address, objid, prop, value)
    except ErrorRejectAbortNack as err:
        return format_pdu(err)
    return None


@conformance_test(
    "9.32.1.12",
    "Who-Has After Object_Name Changed",
    services=SERVICES + ["write-property"],
    writes=True,
)
async def who_has_after_name_changed(ctx: TestContext) -> None:
    candidates = [o for o in ctx.iut.object_list if o != ctx.iut.device_id] or [ctx.iut.device_id]
    o1 = candidates[0]
    ctx.step(f"1. READ V1 = ({o1}), Object_Name")
    v1 = str(await ctx.read(o1, "object-name"))
    v2 = f"{v1}-{uuid.uuid4().hex[:6]}"
    ctx.step(f"2. WRITE ({o1}), Object_Name = '{v2}'")
    error = await _write(ctx, o1, "object-name", v2)
    if error:
        ctx.skip(f"Object_Name of {o1} is not writable ({error}); MAKE requires manual action")
    try:
        ctx.step(f"3. TRANSMIT DESTINATION = GLOBAL BROADCAST, Who-Has-Request 'Object Name' = '{v1}'")
        request = _who_has(ctx.destination("global"), object_name=v1)
        await _no_response(
            ctx, request, "4-5", ctx.config.unconfirmed_response_fail_time,
            "Unconfirmed Response Fail Time",
        )
        ctx.step(f"6. TRANSMIT DESTINATION = GLOBAL BROADCAST, Who-Has-Request 'Object Name' = '{v2}'")
        request = _who_has(ctx.destination("global"), object_name=v2)
        await _receive_i_have(ctx, request, "7", o1, v2)
    finally:
        ctx.note(f"cleanup (not part of 135.1): restore ({o1}), Object_Name = '{v1}'")
        await _write(ctx, o1, "object-name", v1)


@conformance_test(
    "9.32.1.13",
    "Who-Has After Object_Identifier Changed",
    services=SERVICES + ["write-property"],
    writes=True,
)
async def who_has_after_identifier_changed(ctx: TestContext) -> None:
    candidates = [o for o in ctx.iut.object_list if o != ctx.iut.device_id]
    if not candidates:
        ctx.skip("IUT has no object other than the Device object")
    o1 = candidates[0]
    o2 = ctx.unknown_object_id(str(o1[0]))
    ctx.step(f"1. VERIFY ({o1}), Object_Identifier = {o1}")
    ctx.check_equal(await ctx.read(o1, "object-identifier"), o1, "Object_Identifier is incorrect")
    v1 = str(await ctx.read(o1, "object-name"))
    ctx.step(f"2. WRITE ({o1}), Object_Identifier = {o2}")
    error = await _write(ctx, o1, "object-identifier", o2)
    if error:
        ctx.skip(f"Object_Identifier of {o1} is not writable ({error}); MAKE requires manual action")
    try:
        ctx.step(f"3. TRANSMIT DESTINATION = GLOBAL BROADCAST, Who-Has-Request 'Object Identifier' = {o1}")
        request = _who_has(ctx.destination("global"), object_id=o1)
        await _no_response(
            ctx, request, "4-5", ctx.config.unconfirmed_response_fail_time,
            "Unconfirmed Response Fail Time",
        )
        ctx.step(f"6. TRANSMIT DESTINATION = GLOBAL BROADCAST, Who-Has-Request 'Object Identifier' = {o2}")
        request = _who_has(ctx.destination("global"), object_id=o2)
        await _receive_i_have(ctx, request, "7", o2, v1)
    finally:
        ctx.note(f"cleanup (not part of 135.1): restore Object_Identifier {o2} -> {o1}")
        await _write(ctx, o2, "object-identifier", o1)


# ---- 9.32.2 Who-Has requests originating from a remote network -------------


@conformance_test(
    "9.32.2.1", "Object ID Version, Global Broadcast from a Remote Network",
    services=SERVICES, manual=REMOTE,
)
async def object_id_global_from_remote(ctx: TestContext) -> None:
    pass


@conformance_test("9.32.2.2", "Object ID Version, Remote Broadcast", services=SERVICES, manual=REMOTE)
async def object_id_remote_broadcast(ctx: TestContext) -> None:
    pass


@conformance_test("9.32.2.3", "Who-Has for Non-existent Object_Name", services=SERVICES)
async def nonexistent_object_name(ctx: TestContext) -> None:
    v1 = f"no-such-object-{uuid.uuid4().hex[:12]}"
    ctx.note(f"V1 = '{v1}' (not the Object_Name of any object in the IUT)")
    ctx.step(f"1. TRANSMIT Who-Has-Request 'Object Name' = '{v1}'")
    request = _who_has(ctx.destination("local"), object_name=v1)
    await _no_response(
        ctx, request, "2-3", ctx.config.unconfirmed_response_fail_time,
        "Unconfirmed Response Fail Time",
        match=lambda apdu: isinstance(apdu, IHaveRequest)
        and apdu.deviceIdentifier == ctx.iut.device_id
        and str(apdu.objectName) == v1,
    )


@conformance_test("9.32.2.4", "Who-Has for Non-existent Object_Identifier", services=SERVICES)
async def nonexistent_object_identifier(ctx: TestContext) -> None:
    object1 = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT ReadProperty-Request ({object1}), Object_Identifier")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(rp_request(ctx, object1, "object-identifier"), ("object", "unknown-object"))
    ctx.step(f"3. TRANSMIT Who-Has-Request 'Object Identifier' = {object1}")
    request = _who_has(ctx.destination("local"), object_id=object1)
    await _no_response(
        ctx, request, "4-5", ctx.config.unconfirmed_response_fail_time,
        "Unconfirmed Response Fail Time",
        match=lambda apdu: isinstance(apdu, IHaveRequest)
        and apdu.deviceIdentifier == ctx.iut.device_id
        and apdu.objectIdentifier == object1,
    )
