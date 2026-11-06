# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.33 Who-Is Service Execution Tests."""

from __future__ import annotations

from typing import Optional, Tuple

from bacpypes3.apdu import IAmRequest, WhoIsRequest
from bacpypes3.pdu import Address

from ..context import TestContext
from ..registry import conformance_test
from ._common import MAX_INSTANCE, iut_instance_ranges

REMOTE = (
    "requires the TD to originate the request from a simulated remote network "
    "(SNET/SADR) and to act as the router for the response"
)


def _who_is(destination: Address, limits: Optional[Tuple[int, int]] = None) -> WhoIsRequest:
    request = WhoIsRequest(destination=destination)
    if limits is not None:
        request.deviceInstanceRangeLowLimit, request.deviceInstanceRangeHighLimit = limits
    return request


def _from_iut(ctx: TestContext):
    return lambda apdu: isinstance(apdu, IAmRequest) and apdu.iAmDeviceIdentifier == ctx.iut.device_id


async def _receive_i_am(ctx: TestContext, request: WhoIsRequest) -> None:
    """BEFORE Unconfirmed Response Fail Time RECEIVE I-Am-Request with the EPICS values."""
    ctx.step("2. BEFORE Unconfirmed Response Fail Time RECEIVE I-Am-Request")
    i_ams = await ctx.collect(
        request, _from_iut(ctx), ctx.config.unconfirmed_response_fail_time, first_only=True
    )
    if not ctx.check(
        bool(i_ams),
        "No I-Am received from the IUT before the Unconfirmed Response Fail Time",
        expected=f"I-Am {ctx.iut.device_id}",
        actual="no I-Am",
        request=request,
    ):
        return
    i_am = i_ams[0]
    device = ctx.iut.device_id
    # Device object values stand in for "the value specified in the EPICS"
    for param, value, prop in (
        ("Max APDU Length Accepted", i_am.maxAPDULengthAccepted, "max-apdu-length-accepted"),
        ("Segmentation Supported", i_am.segmentationSupported, "segmentation-supported"),
        ("Vendor Identifier", i_am.vendorID, "vendor-identifier"),
    ):
        expected = await ctx.read(device, prop)
        ctx.check(
            str(value) == str(expected),
            f"I-Am '{param}' does not match the Device object's {prop}",
            expected=expected,
            actual=value,
            response=i_am,
        )


def _range(ctx: TestContext, key: str) -> Tuple[int, int]:
    limits = iut_instance_ranges(ctx)[key]
    if limits is None:
        ctx.skip(f"no valid device range of this form exists for instance {ctx.iut.device_instance}")
    return limits


# ---- 9.33.1 Who-Is requests originating from the local network -------------


@conformance_test("9.33.1.1", "Local Broadcast, General Inquiry")
async def local_broadcast_general(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT DESTINATION = LOCAL BROADCAST, Who-Is-Request")
    await _receive_i_am(ctx, _who_is(ctx.destination("local")))


@conformance_test("9.33.1.2", "Global Broadcast, General Inquiry")
async def global_broadcast_general(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT DESTINATION = GLOBAL BROADCAST, Who-Is-Request")
    await _receive_i_am(ctx, _who_is(ctx.destination("global")))


@conformance_test(
    "9.33.1.3", "Local Broadcast, Specific Device Inquiry with IUT Outside of the Device Range"
)
async def local_broadcast_outside_range(ctx: TestContext) -> None:
    x = ctx.iut.device_instance
    limits = (x + 1, MAX_INSTANCE) if x < MAX_INSTANCE else (0, x - 1)
    ctx.step(f"1. TRANSMIT DESTINATION = LOCAL BROADCAST, Who-Is-Request "
             f"Low = {limits[0]}, High = {limits[1]}")
    request = _who_is(ctx.destination("local"), limits)
    ctx.step("2. WAIT Internal Processing Fail Time")
    i_ams = await ctx.collect(request, _from_iut(ctx), ctx.config.internal_processing_fail_time)
    ctx.step("3. CHECK (verify that the IUT does not respond)")
    ctx.check(
        not i_ams,
        "IUT responded to a Who-Is whose device range excludes it",
        expected="no I-Am",
        actual=f"{len(i_ams)} I-Am",
        request=request,
        response=i_ams[0] if i_ams else None,
    )


@conformance_test(
    "9.33.1.4",
    "Local Broadcast, Specific Device Inquiry with IUT Device Instance Equal to Low Limit of Device Range",
)
async def local_broadcast_low_limit(ctx: TestContext) -> None:
    limits = _range(ctx, "low_equal")
    ctx.step(f"1. TRANSMIT DESTINATION = LOCAL BROADCAST, Who-Is-Request "
             f"Low = {limits[0]}, High = {limits[1]}")
    await _receive_i_am(ctx, _who_is(ctx.destination("local"), limits))


@conformance_test(
    "9.33.1.5",
    "Local Broadcast, Specific Device Inquiry with IUT Device Instance Equal to High Limit of Device Range",
)
async def local_broadcast_high_limit(ctx: TestContext) -> None:
    limits = _range(ctx, "high_equal")
    ctx.step(f"1. TRANSMIT DESTINATION = LOCAL BROADCAST, Who-Is-Request "
             f"Low = {limits[0]}, High = {limits[1]}")
    await _receive_i_am(ctx, _who_is(ctx.destination("local"), limits))


@conformance_test(
    "9.33.1.6", "Local Broadcast, Specific Device Inquiry with IUT Inside of the Device Range"
)
async def local_broadcast_inside_range(ctx: TestContext) -> None:
    limits = _range(ctx, "inside")
    ctx.step(f"1. TRANSMIT DESTINATION = LOCAL BROADCAST, Who-Is-Request "
             f"Low = {limits[0]}, High = {limits[1]}")
    await _receive_i_am(ctx, _who_is(ctx.destination("local"), limits))


# ---- 9.33.2 Who-Is requests originating from a remote network --------------


@conformance_test("9.33.2.1", "General Inquiry, Global Broadcast from a Remote Network", manual=REMOTE)
async def general_global_from_remote(ctx: TestContext) -> None:
    pass


@conformance_test("9.33.2.2", "General Inquiry, Remote Broadcast", manual=REMOTE)
async def general_remote_broadcast(ctx: TestContext) -> None:
    pass


@conformance_test("9.33.2.3", "General Inquiry, Directed to a Remote Device", manual=REMOTE)
async def general_directed_to_remote(ctx: TestContext) -> None:
    pass
