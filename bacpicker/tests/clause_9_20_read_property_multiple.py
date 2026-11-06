# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.20 ReadPropertyMultiple Service Execution Tests."""

from __future__ import annotations

from typing import List, Optional, Set

from bacpypes3.apdu import ErrorPDU, ErrorRejectAbortNack, ReadPropertyMultipleACK
from bacpypes3.primitivedata import ObjectIdentifier, ObjectType

from ..assertions import format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import (
    COMMON_PROPERTIES,
    MAX_INSTANCE,
    AccessSpecs,
    Element,
    check_echo,
    check_value,
    is_standard_property,
    network_port_unknown_instance,
    reading_properties_based_on_data_type,
    rpm_elements,
    rpm_request,
    verify,
)

SERVICES = ["read-property-multiple"]


async def _transmit_receive(ctx: TestContext, specs: AccessSpecs) -> Optional[List[Element]]:
    """TRANSMIT ReadPropertyMultiple-Request; RECEIVE ReadPropertyMultiple-ACK in request order."""
    request = rpm_request(ctx, specs)
    ack = await ctx.expect_ack(request, ReadPropertyMultipleACK)
    if ack is None:
        return None
    elements = rpm_elements(ack)
    expected = [
        Element(objid, *((p, None) if isinstance(p, str) else p), None, None).label()
        for objid, props in specs
        for p in props
    ]
    ctx.check(
        [e.label() for e in elements] == expected,
        "ReadPropertyMultiple-ACK results do not match the requested objects/properties in order",
        expected=expected,
        actual=[e.label() for e in elements],
        request=request,
        response=ack,
    )
    return elements


def _check_values(ctx: TestContext, elements: List[Element]) -> None:
    for e in elements:
        check_value(ctx, e, f"Expected any valid value for {e.label()}")


def _check_errors(ctx: TestContext, elements: List[Element], alternatives, what: str) -> None:
    for e in elements:
        ctx.check_access_error(e.error, alternatives, f"{what}: {e.label()}")


def _nonexistent_object(ctx: TestContext) -> ObjectIdentifier:
    """A non-existent object of a type supported by the IUT."""
    return ctx.unknown_object_id()


# ---- 9.20.1 Positive ReadPropertyMultiple Service Execution Tests -----------


@conformance_test("9.20.1.1", "Reading a Single Property from a Single Object", services=SERVICES)
async def single_property_single_object(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    specs = [(object1, ["object-name"])]
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1 = Object_Name")
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK with any valid value for P1")
    elements = await _transmit_receive(ctx, specs)
    if elements:
        _check_values(ctx, elements)


@conformance_test("9.20.1.2", "Reading Multiple properties from a Single Object", services=SERVICES)
async def multiple_properties_single_object(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    specs = [(object1, list(COMMON_PROPERTIES))]
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1, P2, P3")
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK with a valid value for each property")
    elements = await _transmit_receive(ctx, specs)
    if elements:
        _check_values(ctx, elements)


@conformance_test("9.20.1.3", "Reading a Single Property from Multiple Objects", services=SERVICES)
async def single_property_multiple_objects(ctx: TestContext) -> None:
    object1, object2 = ctx.two_objects()
    specs = [(object1, ["object-name"]), (object2, ["object-type"])]
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1, ({object2}), P2")
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK with a valid value for each property")
    elements = await _transmit_receive(ctx, specs)
    if elements:
        _check_values(ctx, elements)


@conformance_test("9.20.1.4", "Reading Multiple Properties from Multiple Objects", services=SERVICES)
async def multiple_properties_multiple_objects(ctx: TestContext) -> None:
    object1, object2 = ctx.two_objects()
    specs = [(object1, list(COMMON_PROPERTIES)), (object2, list(COMMON_PROPERTIES))]
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1-P3, ({object2}), P4-P6")
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK with a valid value for each property")
    elements = await _transmit_receive(ctx, specs)
    if elements:
        _check_values(ctx, elements)


@conformance_test(
    "9.20.1.5", "Reading Multiple Properties with a Single Embedded Access Error", services=SERVICES
)
async def single_embedded_access_error(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    (p3,) = ctx.unsupported_properties(object1, 1)
    specs = [(object1, ["object-identifier", "object-name", p3, "object-type"])]
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1, P2, P3 = {p3}, P4")
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK, P3 = PROPERTY / UNKNOWN_PROPERTY")
    elements = await _transmit_receive(ctx, specs)
    if not elements or len(elements) != 4:
        return
    _check_values(ctx, [elements[0], elements[1], elements[3]])
    _check_errors(ctx, [elements[2]], [("property", "unknown-property")], "Wrong embedded error")


@conformance_test(
    "9.20.1.6", "Reading Multiple Properties with Multiple Embedded Access Errors", services=SERVICES
)
async def multiple_embedded_access_errors(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    p3, p4 = ctx.unsupported_properties(object1, 2)
    object2 = _nonexistent_object(ctx)
    specs = [
        (object1, ["object-identifier", "object-name", p3, p4]),
        (object2, ["object-name", "object-type"]),
    ]
    ctx.step(
        f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1, P2, P3 = {p3}, P4 = {p4}, "
        f"(nonexistent {object2}), P5, P6"
    )
    ctx.step(
        "2. RECEIVE ReadPropertyMultiple-ACK, P3/P4 = PROPERTY / UNKNOWN_PROPERTY, "
        "P5/P6 = OBJECT / UNKNOWN_OBJECT"
    )
    elements = await _transmit_receive(ctx, specs)
    if not elements or len(elements) != 6:
        return
    _check_values(ctx, elements[0:2])
    _check_errors(ctx, elements[2:4], [("property", "unknown-property")], "Wrong embedded error")
    _check_errors(ctx, elements[4:6], [("object", "unknown-object")], "Wrong embedded error")


async def _special_property(ctx: TestContext, special: str) -> None:
    """Shared procedure for 9.20.1.7 ALL, 9.20.1.8 OPTIONAL and 9.20.1.9 REQUIRED."""
    revision = ctx.iut.protocol_revision or 0
    for objx in ctx.one_per_type():
        ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({objx}), {special.upper()}")
        request = rpm_request(ctx, [(objx, [special])])
        ack = await ctx.expect_ack(request, ReadPropertyMultipleACK)
        if ack is None:
            continue
        ctx.step(f"   RECEIVE ReadPropertyMultiple-ACK ({objx}), List Of Results")
        ctx.check(
            [r.objectIdentifier for r in ack.listOfReadAccessResults] == [objx],
            "ACK does not contain exactly one result for ObjectX",
            expected=[str(objx)],
            actual=[str(r.objectIdentifier) for r in ack.listOfReadAccessResults],
        )
        elements = rpm_elements(ack)
        props = [e.prop for e in elements]
        duplicates = sorted({p for p in props if props.count(p) > 1})
        ctx.check(not duplicates, f"{objx}: properties returned more than once", actual=duplicates)
        if special != "optional":
            ctx.check(
                "property-list" not in props,
                f"{objx}: Property_List (371) shall not appear in the List of Results",
                actual="property-list present",
            )

        for e in elements:
            if e.error is None:
                check_value(ctx, e)
            elif revision >= 7:
                ctx.check_access_error(
                    e.error,
                    [("property", "read-access-denied")],
                    f"{objx}: Protocol_Revision >= 7 only allows READ_ACCESS_DENIED for {e.prop}",
                )

        expected = await _expected_special_set(ctx, objx, special)
        returned = {p for p in props if special == "all" or is_standard_property(p)}
        if expected is None:
            if special == "optional":
                wrong = sorted(returned & ctx.model_required(objx))
                ctx.check(not wrong, f"{objx}: OPTIONAL returned required properties", actual=wrong)
            elif special == "required":
                wrong = sorted(returned - ctx.model_required(objx))
                ctx.check(not wrong, f"{objx}: REQUIRED returned optional properties", actual=wrong)
            missing = [p for p in COMMON_PROPERTIES if special != "optional" and p not in returned]
            ctx.check(not missing, f"{objx}: required properties missing", actual=missing)
            continue
        missing = sorted(expected - returned)
        extra = sorted(returned - expected)
        ctx.check(
            not missing,
            f"{objx}: properties missing from {special.upper()} results",
            expected=sorted(expected),
            actual=f"missing: {', '.join(missing)}",
        )
        ctx.check(
            not extra,
            f"{objx}: unexpected properties in {special.upper()} results",
            expected=sorted(expected),
            actual=f"unexpected: {', '.join(extra)}",
        )


async def _expected_special_set(
    ctx: TestContext, objx: ObjectIdentifier, special: str
) -> Optional[Set[str]]:
    """Properties expected for ALL/OPTIONAL/REQUIRED, from Property_List in place of the EPICS."""
    property_list = await ctx.property_list(objx)
    if property_list is None:
        ctx.note(f"{objx}: Property_List unreadable; completeness cannot be checked without EPICS")
        return None
    present = (set(property_list) | set(COMMON_PROPERTIES)) - {"property-list"}
    if special == "all":
        return present
    required = ctx.model_required(objx)
    standard = {p for p in present if is_standard_property(p)}
    return standard & required if special == "required" else standard - required


@conformance_test("9.20.1.7", "Reading ALL Properties", services=SERVICES)
async def reading_all_properties(ctx: TestContext) -> None:
    await _special_property(ctx, "all")


@conformance_test("9.20.1.8", "Reading OPTIONAL Properties", services=SERVICES)
async def reading_optional_properties(ctx: TestContext) -> None:
    await _special_property(ctx, "optional")


@conformance_test("9.20.1.9", "Reading REQUIRED Properties", services=SERVICES)
async def reading_required_properties(ctx: TestContext) -> None:
    await _special_property(ctx, "required")


@conformance_test("9.20.1.10", "Reading the Size of an Array", services=SERVICES)
async def reading_the_size_of_an_array_rpm(ctx: TestContext) -> None:
    ctx.step("9.18.1.1 using ReadPropertyMultiple: VERIFY (Device, X), Object_List[0] = size")
    await verify(
        ctx,
        ctx.iut.device_id,
        "object-list",
        len(ctx.iut.object_list),
        0,
        service="rpm",
        source="Object_List read during discovery, in place of the EPICS",
    )


@conformance_test(
    "9.20.1.11",
    "Reading a Property From the Device Object using the Unknown Instance",
    services=SERVICES,
    min_protocol_revision=4,
)
async def reading_device_using_unknown_instance_rpm(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    wildcard = ObjectIdentifier((ObjectType("device"), MAX_INSTANCE))
    ctx.step("1. TRANSMIT ReadPropertyMultiple-Request (Device, 4194303), Object_Identifier")
    request = rpm_request(ctx, [(wildcard, ["object-identifier"])])
    ack = await ctx.expect_ack(request, ReadPropertyMultipleACK)
    if ack is None:
        return
    ctx.step("2. RECEIVE ReadPropertyMultiple-ACK (Device, X), Object_Identifier = (Device, X)")
    elements = rpm_elements(ack)
    if not ctx.check(len(elements) == 1, "Expected exactly one result", actual=len(elements)):
        return
    check_echo(ctx, elements[0], device, "object-identifier")
    if check_value(ctx, elements[0]):
        ctx.check_equal(
            ctx.decode(device, "object-identifier", None, elements[0].value),
            device,
            "Object_Identifier value is not the IUT's Device object",
        )


async def _max_segments_accepted(ctx: TestContext) -> Optional[int]:
    try:
        return int(await ctx.read(ctx.iut.device_id, "max-segments-accepted"))
    except ErrorRejectAbortNack:
        return None


@conformance_test("9.20.1.12", "Reading Maximum Multiple Properties", services=SERVICES)
async def reading_maximum_multiple_properties(ctx: TestContext) -> None:
    max_apdu = ctx.iut.max_apdu_length_accepted
    segmentation = ctx.iut.segmentation_supported
    if segmentation in ("segmented-both", "segmented-receive"):
        max_rx_segs = await _max_segments_accepted(ctx)
        if max_rx_segs:
            max_per_request = ((max_apdu - 6) * max_rx_segs - 7) // 2
        else:
            ctx.note("Max_Segments_Accepted unreadable; using the non-segmented request formula")
            max_per_request = (max_apdu - 11) // 2
    else:
        max_per_request = (max_apdu - 11) // 2
    # max segments generated per response is only in the EPICS; use the non-segmented formula
    max_per_response = (max_apdu - 10) // 9
    if ctx.iut.segmented_transmit():
        ctx.note("IUT segments responses; MaxTxSegs is EPICS-only, so a single-APDU response is used")
    count = min(max_per_request, max_per_response)
    ctx.note(f"MaxAPDU = {max_apdu}, MaxPropsPerRqst = {max_per_request}, "
             f"MaxPropsPerResp = {max_per_response}, NumPropertiesToUse = {count}")

    device = ctx.iut.device_id
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request (Device, X), Object_Identifier x {count}")
    ctx.step(f"2. RECEIVE ReadPropertyMultiple-ACK, {count} x Object_Identifier = (Device, X)")
    elements = await _transmit_receive(ctx, [(device, ["object-identifier"] * count)])
    if not elements:
        return
    wrong = [
        i for i, e in enumerate(elements, 1)
        if e.error is not None or ctx.decode(device, "object-identifier", None, e.value) != device
    ]
    ctx.check(
        not wrong,
        "Not every Object_Identifier result equals (Device, X)",
        expected=f"{count} x {device}",
        actual=f"wrong at positions {wrong[:10]}{'...' if len(wrong) > 10 else ''}",
    )


@conformance_test("9.20.1.13", "Reading Properties Based on Data Type", services=SERVICES)
async def reading_properties_based_on_data_type_rpm(ctx: TestContext) -> None:
    await reading_properties_based_on_data_type(ctx, "rpm")


@conformance_test(
    "9.20.1.14",
    "ReadPropertyMultiple of the Network Port Object using the Unknown Instance",
    services=SERVICES,
)
async def network_port_unknown_instance_rpm(ctx: TestContext) -> None:
    await network_port_unknown_instance(ctx, "rpm")


@conformance_test(
    "9.20.1.15",
    "ReadPropertyMultiple Service when Non-BACnet Device Offline",
    services=SERVICES,
    manual="requires an object backed by a non-BACnet device that the tester takes offline",
)
async def non_bacnet_device_offline_rpm(ctx: TestContext) -> None:
    pass


# ---- 9.20.2 Negative ReadPropertyMultiple Service Execution Tests -----------


async def _error_or_embedded(
    ctx: TestContext, specs: AccessSpecs, alternatives, what: str
) -> None:
    """RECEIVE (BACnet-Error-PDU, alternatives) | (ReadPropertyMultiple-ACK, every result an error)."""
    request = rpm_request(ctx, specs)
    expected = " | ".join(f"{c} / {e or 'any'}" for c, e in alternatives)
    try:
        ack = await ctx.send(request)
    except ErrorPDU as err:
        ctx.check_access_error(err, alternatives, f"{what}: wrong Error PDU")
        return
    except ErrorRejectAbortNack as err:
        ctx.defect(
            f"{what}: Reject/Abort returned",
            expected=f"Error PDU or embedded errors: {expected}",
            actual=format_pdu(err),
            request=request,
            response=err,
        )
        return
    elements = rpm_elements(ack) if isinstance(ack, ReadPropertyMultipleACK) else []
    if not ctx.check(
        len(elements) == sum(len(props) for _, props in specs),
        f"{what}: ACK does not contain one result per requested property",
        actual=format_pdu(ack),
    ):
        return
    _check_errors(ctx, elements, alternatives, f"{what}: wrong embedded error")


@conformance_test(
    "9.20.2.1", "Reading a Single, Unsupported Property from a Single Object", services=SERVICES
)
async def single_unsupported_property(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    (p1,) = ctx.unsupported_properties(object1, 1)
    ctx.step(f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), P1 = {p1}")
    ctx.step("2. RECEIVE BACnet-Error-PDU | ReadPropertyMultiple-ACK: PROPERTY / UNKNOWN_PROPERTY")
    await _error_or_embedded(
        ctx, [(object1, [p1])], [("property", "unknown-property")], "Unsupported property"
    )


@conformance_test(
    "9.20.2.2", "Reading Multiple Properties with Access Errors for Every Property", services=SERVICES
)
async def access_errors_for_every_property(ctx: TestContext) -> None:
    object1, _ = ctx.two_objects()
    p1, p2, p3 = ctx.unsupported_properties(object1, 3)
    object2 = _nonexistent_object(ctx)
    specs = [(object1, [p1, p2, p3]), (object2, list(COMMON_PROPERTIES))]
    ctx.step(
        f"1. TRANSMIT ReadPropertyMultiple-Request ({object1}), {p1}, {p2}, {p3}, "
        f"(nonexistent {object2}), P4-P6"
    )
    ctx.step("2. RECEIVE BACnet-Error-PDU | ReadPropertyMultiple-ACK: OBJECT | PROPERTY / any code")
    await _error_or_embedded(
        ctx, specs, [("object", None), ("property", None)], "Access errors for every property"
    )


@conformance_test(
    "9.20.2.3",
    "Reading a Single Non-Array Property with an Array Index",
    services=SERVICES,
    min_protocol_revision=4,
)
async def single_non_array_with_index(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT ReadPropertyMultiple-Request (Device, X), Vendor_Name, Array Index = 1")
    ctx.step("2. RECEIVE BACnet-Error-PDU | ReadPropertyMultiple-ACK: PROPERTY / PROPERTY_IS_NOT_AN_ARRAY")
    await _error_or_embedded(
        ctx,
        [(ctx.iut.device_id, [("vendor-name", 1)])],
        [("property", "property-is-not-an-array")],
        "Non-array property with an array index",
    )
