# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.18 ReadProperty Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import AbortPDU, ErrorRejectAbortNack
from bacpypes3.constructeddata import Array
from bacpypes3.primitivedata import ObjectIdentifier, ObjectType

from ..assertions import format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import (
    MAX_INSTANCE,
    check_echo,
    check_value,
    network_port_unknown_instance,
    read_one,
    reading_properties_based_on_data_type,
    rp_request,
    rpm_request,
    verify,
)

SERVICES = ["read-property"]
EPICS_SOURCE = "Object_List read during discovery, in place of the EPICS"


# ---- 9.18.1 Positive ReadProperty Service Execution Tests -------------------


@conformance_test("9.18.1.1", "Reading the Size of an Array", services=SERVICES)
async def reading_the_size_of_an_array(ctx: TestContext) -> None:
    ctx.step("1. VERIFY (Device, X), Object_List = (size of the Object_List), ARRAY INDEX = 0")
    await verify(
        ctx, ctx.iut.device_id, "object-list", len(ctx.iut.object_list), 0, source=EPICS_SOURCE
    )


@conformance_test("9.18.1.2", "Reading a Single Element of an Array", services=SERVICES)
async def reading_a_single_element_of_an_array(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. READ V = (Device, X), Object_List ARRAY INDEX = 1")
    element = await read_one(ctx, device, "object-list", 1)
    if element is None:
        return
    check_echo(ctx, element, device, "object-list", 1)
    ctx.step("2. CHECK (V is of type object-identifier)")
    check_value(ctx, element)


@conformance_test(
    "9.18.1.3",
    "Reading a Property From the Device Object using the Unknown Instance",
    services=SERVICES,
    min_protocol_revision=4,
)
async def reading_device_using_unknown_instance(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    wildcard = ObjectIdentifier((ObjectType("device"), MAX_INSTANCE))
    ctx.step("1. TRANSMIT ReadProperty-Request (Device, 4194303), Object_Identifier")
    element = await read_one(ctx, wildcard, "object-identifier")
    if element is None:
        return
    ctx.step("2. RECEIVE ReadProperty-ACK (Device, X), Object_Identifier = (Device, X)")
    check_echo(ctx, element, device, "object-identifier")
    if check_value(ctx, element):
        ctx.check_equal(
            ctx.decode(device, "object-identifier", None, element.value),
            device,
            "Object_Identifier value is not the IUT's Device object",
        )


@conformance_test("9.18.1.4", "Reading Entire Arrays", services=SERVICES)
async def reading_entire_arrays(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. VERIFY (Device, X), Object_List = (the entire Object_List array)")
    try:
        await verify(ctx, device, "object-list", list(ctx.iut.object_list), source=EPICS_SOURCE)
        return
    except AbortPDU as err:
        reason = str(err.apduAbortRejectReason)
        ctx.check(
            reason in ("segmentation-not-supported", "buffer-overflow"),
            "Object_List read aborted with a reason other than segmentation-not-supported "
            "or buffer-overflow",
            expected="ReadProperty-ACK | Abort: segmentation-not-supported | buffer-overflow",
            actual=format_pdu(err),
        )
        ctx.note(f"Object_List too long for one response ({reason}); repeating with a smaller array")

    for objid in ctx.test_objects():
        for prop in sorted(ctx.model_properties(objid)):
            ptype = ctx.property_type(objid, prop)
            if prop == "object-list" or not (isinstance(ptype, type) and issubclass(ptype, Array)):
                continue
            try:
                size = await ctx.read(objid, prop, 0)
                if not size:
                    continue
                ctx.step(f"1. VERIFY ({objid}), {prop} = (entire array of {size} elements)")
                elements = [await ctx.read(objid, prop, i) for i in range(1, int(size) + 1)]
            except ErrorRejectAbortNack:
                continue
            try:
                await verify(ctx, objid, prop, elements, source="element-by-element read")
            except AbortPDU as err:
                ctx.note(f"{objid} {prop} also aborted: {format_pdu(err)}")
                continue
            return
    ctx.note("no smaller array property was found to repeat the test with")


@conformance_test("9.18.1.5", "Reading Properties Based on Data Type", services=SERVICES)
async def reading_properties_based_on_data_type_rp(ctx: TestContext) -> None:
    await reading_properties_based_on_data_type(ctx, "rp")


@conformance_test("9.18.1.6", "Respects max-segments-accepted bit pattern", services=SERVICES)
async def respects_max_segments_accepted(ctx: TestContext) -> None:
    if not ctx.iut.segmented_transmit():
        ctx.skip(
            f"IUT cannot return a segmented response (Segmentation_Supported = "
            f"{ctx.iut.segmentation_supported}), so its largest response is not > 100 octets"
        )
    device = ctx.iut.device_id
    # an Object_List response is roughly 12 octets plus 5 per object identifier
    if 12 + 5 * len(ctx.iut.object_list) > 100:
        request = rp_request(ctx, device, "object-list")
        what = "ReadProperty (Device, X), Object_List"
    elif ctx.iut.supports_service("read-property-multiple"):
        request = rpm_request(ctx, [(device, ["all"])])
        what = "ReadPropertyMultiple (Device, X), ALL"
    else:
        ctx.skip("no request available whose response exceeds 100 octets")

    ctx.step(
        f"1. TRANSMIT {what}, 'max-APDU-length-accepted' = 50, "
        "'segmented-response-accepted' = TRUE, 'max-segments-accepted' = 2"
    )
    tester = ctx.app.device_object
    saved = (tester.maxApduLengthAccepted, tester.maxSegmentsAccepted)
    tester.maxApduLengthAccepted, tester.maxSegmentsAccepted = 50, 2
    try:
        ack = await ctx.send(request)
    except AbortPDU as err:
        ctx.step("2. RECEIVE BACnet-Abort-PDU, 'Abort Reason' = BUFFER_OVERFLOW")
        ctx.check(
            str(err.apduAbortRejectReason) == "buffer-overflow",
            "Wrong abort reason when the response needs more than max-segments-accepted",
            expected="Abort: buffer-overflow",
            actual=format_pdu(err),
            request=request,
            response=err,
        )
        return
    finally:
        tester.maxApduLengthAccepted, tester.maxSegmentsAccepted = saved
    ctx.defect(
        "IUT returned a response instead of aborting; 'max-segments-accepted' = 2 was not respected",
        expected="Abort: buffer-overflow",
        actual=format_pdu(ack),
        request=request,
    )


@conformance_test(
    "9.18.1.7", "Reading Array Properties at Different Array Indexes", services=SERVICES
)
async def reading_array_properties_at_different_indexes(ctx: TestContext) -> None:
    o1, p1 = ctx.iut.device_id, "object-list"
    x = len(ctx.iut.object_list)
    ctx.note(f"O1 = {o1}, P1 = Object_List, X = {x}")
    ctx.step("1. VERIFY P1 = X, ARRAY INDEX = 0")
    await verify(ctx, o1, p1, x, 0, source=EPICS_SOURCE)
    if x > 0:
        for index in (1, x):
            ctx.step(f"2. READ V = P1, ARRAY INDEX = {index}; CHECK (V is a valid value)")
            element = await read_one(ctx, o1, p1, index)
            if element is not None:
                check_echo(ctx, element, o1, p1, index)
                check_value(ctx, element)
    ctx.step(f"3. TRANSMIT ReadProperty-Request O1, P1, 'Property Array Index' = {x + 1}")
    ctx.step("4. RECEIVE BACnet-Error-PDU PROPERTY / INVALID_ARRAY_INDEX")
    await ctx.expect_error(rp_request(ctx, o1, p1, x + 1), ("property", "invalid-array-index"))


@conformance_test(
    "9.18.1.8",
    "ReadProperty of the Network Port Object using the Unknown Instance",
    services=SERVICES,
)
async def network_port_unknown_instance_rp(ctx: TestContext) -> None:
    await network_port_unknown_instance(ctx, "rp")


@conformance_test(
    "9.18.1.9",
    "ReadProperty Service when Non-BACnet Device Offline",
    services=SERVICES,
    manual="requires an object backed by a non-BACnet device that the tester takes offline",
)
async def non_bacnet_device_offline(ctx: TestContext) -> None:
    pass


# ---- 9.18.2 Negative ReadProperty Service Execution Tests -------------------


@conformance_test("9.18.2.1", "Reading Non-Array Properties with an Array Index", services=SERVICES)
async def reading_non_array_with_index(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT ReadProperty-Request (Device, X), Vendor_Name, Array Index = 1")
    request = rp_request(ctx, ctx.iut.device_id, "vendor-name", 1)
    revision = ctx.iut.protocol_revision
    if revision is not None and revision >= 4:
        ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / PROPERTY_IS_NOT_AN_ARRAY")
        await ctx.expect_error(request, ("property", "property-is-not-an-array"))
    else:
        ctx.step("2. RECEIVE BACnet-Error-PDU (Protocol_Revision absent or < 4 alternatives)")
        await ctx.expect_error(
            request,
            ("property", "property-is-not-an-array"),
            ("property", "invalid-array-index"),
            ("services", "inconsistent-parameters"),
        )


@conformance_test(
    "9.18.2.2",
    "Reading Array Properties with an Array Index that is Out of Range",
    services=SERVICES,
)
async def reading_array_index_out_of_range(ctx: TestContext) -> None:
    index = len(ctx.iut.object_list) + 1
    ctx.step(f"1. TRANSMIT ReadProperty-Request (Device, X), Object_List, Array Index = {index}")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / INVALID_ARRAY_INDEX")
    await ctx.expect_error(
        rp_request(ctx, ctx.iut.device_id, "object-list", index), ("property", "invalid-array-index")
    )


@conformance_test("9.18.2.3", "Reading an Unknown Object", services=SERVICES)
async def reading_an_unknown_object(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT ReadProperty-Request ({objid}), Object_Name")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(rp_request(ctx, objid, "object-name"), ("object", "unknown-object"))


@conformance_test("9.18.2.4", "Reading an Unknown Property", services=SERVICES)
async def reading_an_unknown_property(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT ReadProperty-Request (Device, X), {prop}")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / UNKNOWN_PROPERTY")
    await ctx.expect_error(rp_request(ctx, device, prop), ("property", "unknown-property"))
