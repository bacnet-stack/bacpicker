# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.22 WriteProperty Service Execution Tests."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.primitivedata import ObjectIdentifier, Unsigned

from ..context import TestContext
from ..registry import conformance_test
from ._common import (
    Written,
    cast_property,
    different_value,
    expect_simple_ack,
    is_array,
    priority_slot_value,
    ranged_property,
    read_only_property,
    restore,
    restore_priority_slot,
    wp_request,
    writable_properties,
)

SERVICE = ["write-property"]
REV4 = 4


async def _read(ctx: TestContext, objid: ObjectIdentifier, prop: str, index: Optional[int] = None) -> Any:
    return await ctx.read(objid, prop, index)


def _writable_scalar(ctx: TestContext) -> Optional[Tuple[ObjectIdentifier, str, Any]]:
    """A non-commandable property the standard marks writable. The value is filled by the caller."""
    from ..standard import object_spec

    for objid in ctx.test_objects():
        spec = object_spec(str(objid[0]))
        if spec is None:
            continue
        for prop in spec.properties:
            if prop.writable and not prop.commandable and not is_array(ctx.property_type(objid, prop.name)):
                return objid, prop.name, None
    return None


async def _commandable(ctx: TestContext) -> Optional[Tuple[ObjectIdentifier, Any]]:
    """Present_Value whose Priority_Array element 16 can be read."""
    for objid in ctx.test_objects():
        if "present-value" not in ctx.model_properties(objid):
            continue
        if "priority-array" not in ctx.model_properties(objid):
            continue
        try:
            slot = await _read(ctx, objid, "priority-array", 16)
            current = await _read(ctx, objid, "present-value")
        except ErrorRejectAbortNack:
            continue
        if different_value(current) is None:
            continue
        return objid, slot
    return None


# ---- 9.22.1 Positive -------------------------------------------------------


@conformance_test("9.22.1.1", "Writing a Single Element of an Array", services=SERVICE, writes=True)
async def writing_one_array_element(ctx: TestContext) -> None:
    chosen = None
    for objid in ctx.test_objects():
        for prop in await writable_properties(ctx, objid):
            if not is_array(ctx.property_type(objid, prop)):
                continue
            try:
                size = int(await _read(ctx, objid, prop, 0))
                if size < 1:
                    continue
                current = await _read(ctx, objid, prop, 1)
            except ErrorRejectAbortNack:
                continue
            new = different_value(current)
            if new is None:
                continue
            chosen = (objid, prop, current, new)
            break
        if chosen:
            break
    if chosen is None:
        ctx.skip("no writable array element with a known alternate value was found")
    objid, prop, current, new = chosen
    ctx.step(f"1. READ X = ({objid}), {prop}, ARRAY INDEX = 1")
    ctx.step(f"2. TRANSMIT WriteProperty-Request ({objid}), {prop}, ARRAY INDEX = 1")
    request = wp_request(ctx, objid, prop, new, 1)
    ctx.step("3. RECEIVE BACnet-SimpleACK-PDU")
    if not await expect_simple_ack(ctx, request):
        return
    try:
        ctx.step(f"4. VERIFY ({objid}), {prop}, ARRAY INDEX = 1")
        ctx.check_equal(await _read(ctx, objid, prop, 1), new, "array element was not written")
    finally:
        await restore(ctx, Written(objid, prop, current, 1))


@conformance_test(
    "9.22.1.2", "Writing a Commandable Property Without a Priority", services=SERVICE, writes=True
)
async def writing_commandable_without_priority(ctx: TestContext) -> None:
    found = await _commandable(ctx)
    if found is None:
        ctx.skip("no commandable Present_Value with a readable Priority_Array[16] was found")
    objid, slot = found
    current = await _read(ctx, objid, "present-value")
    new = different_value(current)
    ctx.step(f"1. READ X = ({objid}), Priority_Array, ARRAY INDEX = 16")
    ctx.step(f"2. TRANSMIT WriteProperty-Request ({objid}), Present_Value = {new} (no priority)")
    ctx.step("3. RECEIVE BACnet-SimpleACK-PDU")
    try:
        if not await expect_simple_ack(ctx, wp_request(ctx, objid, "present-value", new)):
            return
        ctx.step("4. VERIFY Priority_Array, ARRAY INDEX = 16")
        ctx.check_equal(
            priority_slot_value(await _read(ctx, objid, "priority-array", 16)),
            cast_property(ctx, objid, "present-value", new),
            "priority 16 was not written",
        )
    finally:
        await restore(ctx, restore_priority_slot(objid, slot))


@conformance_test(
    "9.22.1.3", "Writing a Non-Commandable Property with a Priority", services=SERVICE, writes=True
)
async def writing_non_commandable_with_priority(ctx: TestContext) -> None:
    target = _writable_scalar(ctx)
    if target is None:
        ctx.skip("no non-commandable writable scalar property is defined for the IUT")
    objid, prop, _ = target
    try:
        current = await _read(ctx, objid, prop)
    except ErrorRejectAbortNack as err:
        ctx.skip(f"{objid} {prop} cannot be read ({err})")
    new = different_value(current)
    if new is None:
        ctx.skip(f"no alternate value is known for {objid} {prop}")
    ctx.step(f"1. READ X = ({objid}), {prop}")
    ctx.step(f"2. TRANSMIT WriteProperty-Request ({objid}), {prop}, Priority = 8")
    ctx.step("3. RECEIVE BACnet-SimpleACK-PDU")
    if not await expect_simple_ack(ctx, wp_request(ctx, objid, prop, new, priority=8)):
        return
    try:
        ctx.step(f"4. VERIFY ({objid}), {prop}")
        ctx.check_equal(await _read(ctx, objid, prop), new, "property was not written")
    finally:
        await restore(ctx, Written(objid, prop, current))


@conformance_test("9.22.1.4", "Writing an Array Size", services=SERVICE, writes=True)
async def writing_an_array_size(ctx: TestContext) -> None:
    ctx.skip("no writable non-fixed-size array was identified from the object model")


@conformance_test("9.22.1.5", "Writing to Properties Based on Data Type", services=SERVICE, writes=True)
async def writing_by_data_type(ctx: TestContext) -> None:
    from ..context import BASE_TYPES, base_type

    covered = {}
    for objid in ctx.test_objects():
        for prop in await writable_properties(ctx, objid):
            ptype = ctx.property_type(objid, prop)
            base = base_type(ptype)
            if base is None or base in covered or is_array(ptype):
                continue
            try:
                current = await _read(ctx, objid, prop)
            except ErrorRejectAbortNack:
                continue
            new = different_value(current)
            if new is None or new == current:
                continue
            ctx.step(f"1. READ X = ({objid}), {prop} [{base.__name__}]")
            ctx.step("2. TRANSMIT WriteProperty-Request")
            ctx.step("3. RECEIVE BACnet-SimpleACK-PDU")
            if not await expect_simple_ack(ctx, wp_request(ctx, objid, prop, new)):
                continue
            try:
                ctx.step("4. VERIFY the written value")
                ctx.check_equal(await _read(ctx, objid, prop), new, f"{prop} was not written")
                covered[base] = f"{objid} {prop}"
            finally:
                await restore(ctx, Written(objid, prop, current))
        if len(covered) == len(BASE_TYPES):
            break
    if not covered:
        ctx.skip("no writable property with a known alternate value was found")
    for base, where in covered.items():
        ctx.note(f"{base.__name__}: {where}")


# ---- 9.22.2 Negative -------------------------------------------------------


@conformance_test("9.22.2.1", "Writing Non-Array Properties with an Array Index", services=SERVICE)
async def writing_non_array_with_index(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    prop = "object-name"
    current = await _read(ctx, device, prop)
    new = different_value(current)
    ctx.step(f"1. READ X = (Device, X), {prop}")
    ctx.step(f"2. TRANSMIT WriteProperty-Request (Device, X), {prop}, Array Index = 1")
    request = wp_request(ctx, device, prop, new, 1)
    revision = ctx.iut.protocol_revision
    if revision is not None and revision >= REV4:
        ctx.step("3. RECEIVE BACnet-Error-PDU PROPERTY / PROPERTY_IS_NOT_AN_ARRAY")
        await ctx.expect_error(request, ("property", "property-is-not-an-array"))
    else:
        ctx.step("3. RECEIVE BACnet-Error-PDU SERVICES / INCONSISTENT_PARAMETERS")
        await ctx.expect_error(request, ("services", "inconsistent-parameters"))
    ctx.step("4. VERIFY (Device, X), Object_Name = X")
    ctx.check_equal(await _read(ctx, device, prop), current, "Object_Name changed after a rejected write")


@conformance_test(
    "9.22.2.2", "Writing Array Properties with an Array Index that is Out of Range", services=SERVICE
)
async def writing_array_index_out_of_range(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    prop = "object-list"
    before = list(ctx.iut.object_list)
    index = len(before) + 1
    sample = before[0] if before else device
    ctx.step("1. READ X = (Device, X), Object_List")
    ctx.step(f"2. TRANSMIT WriteProperty-Request Object_List, Array Index = {index}")
    ctx.step("3. RECEIVE BACnet-Error-PDU PROPERTY / INVALID_ARRAY_INDEX")
    await ctx.expect_error(
        wp_request(ctx, device, prop, sample, index), ("property", "invalid-array-index")
    )
    ctx.step("4. VERIFY Object_List is unchanged")
    ctx.check_equal(list(await _read(ctx, device, prop)), before, "Object_List changed")


@conformance_test("9.22.2.3", "Writing with a Property Value Having the Wrong Datatype", services=SERVICE)
async def writing_wrong_datatype(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    current = await _read(ctx, device, "object-name")
    ctx.step("1. READ X = (Device, X), Object_Name")
    ctx.step("2. TRANSMIT WriteProperty-Request Object_Name = (an Unsigned)")
    ctx.step("3. RECEIVE Error INVALID_DATATYPE, or Reject INVALID_PARAMETER_DATATYPE or INVALID_TAG")
    request = wp_request(ctx, device, "object-name", Unsigned(1), cast=False)
    failed = await _error_or_reject(
        ctx,
        request,
        errors=(("property", "invalid-data-type"),),
        rejects=("invalid-parameter-data-type", "invalid-tag"),
    )
    if failed:
        ctx.step("4. VERIFY Object_Name = X")
        ctx.check_equal(await _read(ctx, device, "object-name"), current, "Object_Name changed")


@conformance_test("9.22.2.4", "Writing with a Property Value that is Out of Range", services=SERVICE)
async def writing_out_of_range(ctx: TestContext) -> None:
    found = ranged_property(ctx)
    if found is None:
        ctx.skip("no writable property with a restricted range is defined for the IUT")
    objid, prop, low, high = found
    try:
        current = await _read(ctx, objid, prop)
    except ErrorRejectAbortNack as err:
        ctx.skip(f"{objid} {prop} cannot be read ({err})")
    if high is not None:
        outside = high + 1
    elif low is not None:
        outside = low - 1
    else:
        ctx.skip(f"{prop} has no numeric bound")
    ctx.step(f"1. READ X = ({objid}), {prop}")
    ctx.step(f"2. TRANSMIT WriteProperty-Request {prop} = {outside}")
    request = wp_request(ctx, objid, prop, outside)
    revision = ctx.iut.protocol_revision
    errors = [("property", "value-out-of-range"), ("property", "optional-functionality-not-supported")]
    if revision is not None and revision >= REV4:
        ctx.step("3. RECEIVE BACnet-Error-PDU PROPERTY / VALUE_OUT_OF_RANGE or"
            "OPTIONAL_FUNCTIONALITY_NOT_SUPPORTED")
        await ctx.expect_error(request, *errors)
    else:
        ctx.step("3. RECEIVE Error VALUE_OUT_OF_RANGE or Reject PARAMETER_OUT_OF_RANGE")
        await _error_or_reject(ctx, request, errors=errors, rejects=("parameter-out-of-range",))
    ctx.step("4. VERIFY the property is unchanged")
    ctx.check_equal(await _read(ctx, objid, prop), current, f"{prop} changed")


@conformance_test(
    "9.22.2.5",
    "Writing To Non-Existent Objects",
    services=SERVICE,
    min_protocol_revision=REV4,
)
async def writing_unknown_object(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT WriteProperty-Request ({objid}), Object_Name")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(
        wp_request(ctx, objid, "object-name", "not-an-object"),
        ("object", "unknown-object"),
        ("property", "unknown-property"),
        ("property", "write-access-denied"),
        ("property", "invalid-data-type"),
        ("property", "value-out-of-range"),
        ("resources", "no-space-to-write-property"),
    )


@conformance_test(
    "9.22.2.6",
    "Writing To Non-Existent Properties",
    services=SERVICE,
    min_protocol_revision=REV4,
)
async def writing_unknown_property(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT WriteProperty-Request (Device, X), {prop}")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / UNKNOWN_PROPERTY")
    value = Unsigned(1)
    await ctx.expect_error(wp_request(ctx, device, prop, value, cast=False), ("property", "unknown-property"))


@conformance_test(
    "9.22.2.7",
    "Writing To Non-Writable Properties",
    services=SERVICE,
    min_protocol_revision=REV4,
)
async def writing_non_writable(ctx: TestContext) -> None:
    objid, prop, _ = read_only_property(ctx)
    try:
        current = await _read(ctx, objid, prop)
    except ErrorRejectAbortNack as err:
        ctx.skip(f"{objid} {prop} cannot be read ({err})")
    ctx.step(f"1. TRANSMIT WriteProperty-Request ({objid}), {prop}")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / WRITE_ACCESS_DENIED")
    await ctx.expect_error(wp_request(ctx, objid, prop, current), ("property", "write-access-denied"))


@conformance_test(
    "9.22.2.8",
    "Writing An Object_Name With A Value That Is Already In Use",
    services=SERVICE,
    min_protocol_revision=REV4,
)
async def writing_duplicate_name(ctx: TestContext) -> None:
    objects = ctx.test_objects()
    if len(objects) < 2:
        ctx.skip("the IUT has fewer than two objects")
    first, second = objects[0], objects[1]
    try:
        used = str(await _read(ctx, first, "object-name"))
    except ErrorRejectAbortNack as err:
        ctx.skip(f"Object_Name cannot be read ({err})")
    ctx.step(f"1. TRANSMIT WriteProperty-Request ({second}), Object_Name = '{used}'")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / DUPLICATE_NAME")
    request = wp_request(ctx, second, "object-name", used)
    from bacpypes3.apdu import ErrorPDU

    try:
        await ctx.send(request)
    except ErrorPDU as err:
        from ..assertions import error_class_code

        pair = tuple(str(part) for part in error_class_code(err))
        if pair == ("property", "write-access-denied"):
            ctx.skip(f"Object_Name of {second} is not writable")
        ctx.check(
            pair == ("property", "duplicate-name"),
            "Wrong error class or error code returned",
            expected="property / duplicate-name",
            actual=f"{pair[0]} / {pair[1]}",
            request=request,
            response=err,
        )
        return
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected PROPERTY / DUPLICATE_NAME", actual=err, request=request, response=err)
        return
    ctx.defect("Object_Name already in use was accepted", request=request)


@conformance_test("9.22.2.9", "Writing Non-Array Read-only Property with an Array Index", services=SERVICE)
async def writing_read_only_with_index(ctx: TestContext) -> None:
    objid, prop, _ = read_only_property(ctx)
    if is_array(ctx.property_type(objid, prop)):
        ctx.skip(f"{prop} is an array")
    try:
        current = await _read(ctx, objid, prop)
    except ErrorRejectAbortNack as err:
        ctx.skip(f"{objid} {prop} cannot be read ({err})")
    ctx.step(f"1. TRANSMIT WriteProperty-Request ({objid}), {prop}, Array Index = 1")
    request = wp_request(ctx, objid, prop, current, 1)
    revision = ctx.iut.protocol_revision
    if revision is not None and revision >= REV4:
        ctx.step("2. RECEIVE PROPERTY / WRITE_ACCESS_DENIED or PROPERTY_IS_NOT_AN_ARRAY")
        await ctx.expect_error(
            request,
            ("property", "write-access-denied"),
            ("property", "property-is-not-an-array"),
        )
    else:
        ctx.step("2. RECEIVE an error permitted before Protocol_Revision 4")
        await ctx.expect_error(
            request,
            ("services", "inconsistent-parameters"),
            ("property", "write-access-denied"),
            ("property", "property-is-not-an-array"),
        )


@conformance_test("9.22.2.10", "Resizing a writable fixed size array property", services=SERVICE)
async def resizing_fixed_array(ctx: TestContext) -> None:
    ctx.skip("no writable fixed-size array was identified from the object model")


@conformance_test(
    "9.22.2.11",
    "Writing a Property Value Related to Non-supported Optional Functionality",
    services=SERVICE,
)
async def writing_unsupported_optional(ctx: TestContext) -> None:
    ctx.skip("the EPICS does not identify a value that requires unsupported optional functionality")


async def _error_or_reject(ctx: TestContext, request, *, errors=(), rejects=()) -> bool:
    """True when the IUT returned one of the allowed errors or rejects."""
    from bacpypes3.apdu import ErrorPDU, ErrorRejectAbortNack, RejectPDU
    from bacpypes3.basetypes import ErrorClass, ErrorCode

    from ..assertions import error_class_code, format_pdu

    expected_errors = [(ErrorClass(c), ErrorCode(e)) for c, e in errors]
    try:
        ack = await ctx.send(request)
    except RejectPDU as err:
        actual = str(err.apduAbortRejectReason)
        return ctx.check(
            actual in rejects,
            "Wrong reject reason",
            expected=" | ".join(rejects),
            actual=format_pdu(err),
            request=request,
            response=err,
        )
    except ErrorPDU as err:
        return ctx.check(
            error_class_code(err) in expected_errors,
            "Wrong error class or error code returned",
            expected=errors,
            actual=format_pdu(err),
            request=request,
            response=err,
        )
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected an Error or Reject", actual=format_pdu(err), request=request, response=err)
        return False
    ctx.defect("Expected an Error or Reject but the request was acknowledged", actual=format_pdu(ack),
        request=request)
    return False
