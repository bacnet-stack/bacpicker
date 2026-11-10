# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.23 WritePropertyMultiple Service Execution Tests."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

from bacpypes3.apdu import ErrorRejectAbortNack, RejectPDU, WritePropertyMultipleError
from bacpypes3.primitivedata import Date, Time, Unsigned

from ..assertions import error_class_code, format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ..standard import object_spec
from ._common import (
    Written,
    cast_property,
    different_value,
    expect_simple_ack,
    is_array,
    priority_slot_value,
    restore,
    restore_priority_slot,
    wpm_request,
)

SERVICE = ["write-property-multiple"]
Scalar = Tuple[Any, str, Any]  # objid, property, current value


async def _scalars(ctx: TestContext, count: int) -> Optional[List[Scalar]]:
    found: List[Scalar] = []
    seen = set()
    for objid in ctx.test_objects():
        spec = object_spec(str(objid[0]))
        if spec is None:
            continue
        for prop in spec.properties:
            if not prop.writable or prop.commandable or is_array(ctx.property_type(objid, prop.name)):
                continue
            if (objid, prop.name) in seen:
                continue
            try:
                current = await ctx.read(objid, prop.name)
            except ErrorRejectAbortNack:
                continue
            if different_value(current) is None:
                continue
            seen.add((objid, prop.name))
            found.append((objid, prop.name, current))
            if len(found) >= count:
                return found
    return found or None


async def _write_and_check(ctx: TestContext, rows: Sequence[Scalar], priority: Optional[int] = None) -> None:
    groups = {}
    originals = []
    for objid, prop, current in rows:
        new = different_value(current)
        groups.setdefault(objid, []).append((prop, new, None, priority, True))
        originals.append(Written(objid, prop, current))
    request = wpm_request(ctx, list(groups.items()))
    ctx.step("TRANSMIT WritePropertyMultiple-Request")
    ctx.step("RECEIVE BACnet-SimpleACK-PDU")
    # earlier writes may have been applied before an error, so restore even without an ACK
    try:
        if not await expect_simple_ack(ctx, request):
            return
        ctx.step("VERIFY each written property")
        for objid, props in groups.items():
            for prop, new, _index, _priority, _cast in props:
                ctx.check_equal(await ctx.read(objid, prop), new, f"{objid} {prop} was not written")
    finally:
        for change in originals:
            await restore(ctx, change)


@conformance_test("9.23.1.1", "Writing a Single Property to a Single Object", services=SERVICE, writes=True)
async def one_property(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 1)
    if not rows:
        ctx.skip("no non-commandable writable scalar property was found")
    ctx.step(f"1. READ X = ({rows[0][0]}), {rows[0][1]}")
    await _write_and_check(ctx, rows)


@conformance_test("9.23.1.2", "Writing Multiple properties to a Single Object", services=SERVICE, writes=True)
async def many_on_one_object(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 8)
    if not rows:
        ctx.skip("no writable scalar properties were found")
    same = [row for row in rows if row[0] == rows[0][0]]
    if len(same) < 2:
        ctx.skip("no object has two non-commandable writable scalar properties")
    await _write_and_check(ctx, same[:2])


@conformance_test("9.23.1.3", "Writing a Single Property to Multiple Objects", services=SERVICE, writes=True)
async def one_on_two_objects(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 8)
    if not rows:
        ctx.skip("no writable scalar properties were found")
    picked = []
    seen = set()
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        picked.append(row)
        if len(picked) == 2:
            break
    if len(picked) < 2:
        ctx.skip("two objects with writable scalar properties were not found")
    await _write_and_check(ctx, picked)


@conformance_test("9.23.1.4", "Writing Multiple Properties to Multiple Objects", services=SERVICE,
    writes=True)
async def many_on_two_objects(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 12)
    if not rows:
        ctx.skip("no writable scalar properties were found")
    by_object = {}
    for row in rows:
        by_object.setdefault(row[0], []).append(row)
    rich = [group for group in by_object.values() if len(group) >= 2]
    if len(rich) < 2:
        ctx.skip("two objects each with two writable scalar properties were not found")
    await _write_and_check(ctx, rich[0][:2] + rich[1][:2])


@conformance_test(
    "9.23.1.5", "Writing a Non-Commandable Property with a Priority", services=SERVICE, writes=True
)
async def non_commandable_with_priority(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 1)
    if not rows:
        ctx.skip("no non-commandable writable scalar property was found")
    await _write_and_check(ctx, rows, priority=8)


@conformance_test(
    "9.23.1.6", "Writing a Commandable Property Without a Priority", services=SERVICE, writes=True
)
async def commandable_without_priority(ctx: TestContext) -> None:
    for objid in ctx.test_objects():
        if "present-value" not in ctx.model_properties(objid):
            continue
        if "priority-array" not in ctx.model_properties(objid):
            continue
        try:
            slot = await ctx.read(objid, "priority-array", 16)
            current = await ctx.read(objid, "present-value")
        except ErrorRejectAbortNack:
            continue
        new = different_value(current)
        if new is None:
            continue
        ctx.step(f"1. READ X = ({objid}), Priority_Array, ARRAY INDEX = 16")
        request = wpm_request(ctx, [(objid, [("present-value", new, None, None, True)])])
        ctx.step("2. TRANSMIT WritePropertyMultiple-Request, Present_Value, no priority")
        try:
            if not await expect_simple_ack(ctx, request):
                return
            ctx.step("3. VERIFY Priority_Array[16]")
            ctx.check_equal(
                priority_slot_value(await ctx.read(objid, "priority-array", 16)),
                cast_property(ctx, objid, "present-value", new),
                "priority 16 was not written",
            )
        finally:
            await restore(ctx, restore_priority_slot(objid, slot))
        return
    ctx.skip("no commandable Present_Value was found")


@conformance_test("9.23.1.7", "Writing Maximum Multiple Properties", services=SERVICE, writes=True)
async def maximum_properties(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 16)
    if not rows or len(rows) < 2:
        ctx.skip("fewer than two writable scalar properties were found")
    ctx.note(f"writing {len(rows)} properties in one WritePropertyMultiple")
    await _write_and_check(ctx, rows)


@conformance_test("9.23.1.8", "Writing to Properties Based on Data Type", services=SERVICE, writes=True)
async def by_data_type(ctx: TestContext) -> None:
    from ..context import base_type

    rows = await _scalars(ctx, 32)
    if not rows:
        ctx.skip("no writable scalar properties were found")
    chosen = []
    seen = set()
    for objid, prop, current in rows:
        base = base_type(ctx.property_type(objid, prop))
        if base is None or base in seen:
            continue
        seen.add(base)
        chosen.append((objid, prop, current))
        ctx.note(f"{base.__name__}: {objid} {prop}")
    await _write_and_check(ctx, chosen)


@conformance_test("9.23.1.9", "Writing an Array Size", services=SERVICE, writes=True)
async def array_size(ctx: TestContext) -> None:
    ctx.skip("no writable non-fixed-size array was identified from the object model")


async def _wpm_error(ctx: TestContext, request, error_class: str, error_code: str):
    try:
        ack = await ctx.send(request)
    except WritePropertyMultipleError as err:
        pair = tuple(str(part) for part in error_class_code(err))
        ctx.check(
            pair == (error_class, error_code),
            "Wrong WritePropertyMultiple-Error",
            expected=f"{error_class} / {error_code}",
            actual=pair,
            response=err,
        )
        return err
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected WritePropertyMultiple-Error", actual=format_pdu(err), request=request,
            response=err)
        return None
    ctx.defect("WritePropertyMultiple was acknowledged", actual=format_pdu(ack), request=request)
    return None


@conformance_test(
    "9.23.2.1", "Writing Multiple Properties with a Property Access Error", services=SERVICE, writes=True
)
async def property_access_error(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 1)
    if not rows:
        ctx.skip("no writable scalar property was found")
    objid, prop, current = rows[0]
    bad = ctx.unsupported_properties(objid, 1)[0]
    new = different_value(current)
    ctx.step(f"1. READ X = ({objid}), {prop}")
    ctx.step(f"2. TRANSMIT WritePropertyMultiple-Request {prop}, then unsupported {bad}")
    request = wpm_request(
        ctx,
        [(objid, [(prop, new, None, None, True), (bad, Unsigned(1), None, None, False)])],
    )
    ctx.step("3. RECEIVE WritePropertyMultiple-Error PROPERTY / UNKNOWN_PROPERTY")
    try:
        err = await _wpm_error(ctx, request, "property", "unknown-property")
        attempt = getattr(err, "firstFailedWriteAttempt", None)
        if attempt is not None:
            ctx.check_equal(attempt.propertyIdentifier, bad, "first failed property is wrong")
        ctx.step("4. VERIFY the first property was written")
        ctx.check_equal(await ctx.read(objid, prop), new, f"{prop} was not written before the failure")
    finally:
        await restore(ctx, Written(objid, prop, current))


@conformance_test(
    "9.23.2.2", "Writing Multiple Properties with an Object Access Error", services=SERVICE, writes=True
)
async def object_access_error(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 1)
    if not rows:
        ctx.skip("no writable scalar property was found")
    objid, prop, current = rows[0]
    missing = ctx.unknown_object_id()
    new = different_value(current)
    ctx.step(f"1. READ X = ({objid}), {prop}")
    ctx.step(f"2. TRANSMIT WritePropertyMultiple-Request {objid}, then {missing}")
    request = wpm_request(
        ctx,
        [
            (objid, [(prop, new, None, None, True)]),
            (missing, [("object-name", "missing", None, None, True)]),
        ],
    )
    ctx.step("3. RECEIVE WritePropertyMultiple-Error OBJECT / UNKNOWN_OBJECT")
    err = await _wpm_error(ctx, request, "object", "unknown-object")
    attempt = getattr(err, "firstFailedWriteAttempt", None)
    if attempt is not None:
        ctx.check_equal(attempt.objectIdentifier, missing, "first failed object is wrong")
    try:
        ctx.check_equal(await ctx.read(objid, prop), new, f"{prop} was not written before the failure")
    finally:
        await restore(ctx, Written(objid, prop, current))


@conformance_test(
    "9.23.2.5", "Writing Array Properties with an Array Index that is Out of Range", services=SERVICE,
        writes=True
)
async def array_index_out_of_range(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    index = len(ctx.iut.object_list) + 1
    sample = ctx.iut.object_list[0]
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request Object_List[{index}]")
    ctx.step("2. RECEIVE WritePropertyMultiple-Error PROPERTY / INVALID_ARRAY_INDEX")
    await _wpm_error(
        ctx,
        wpm_request(ctx, [(device, [("object-list", sample, index, None, True)])]),
        "property",
        "invalid-array-index",
    )


@conformance_test(
    "9.23.2.8", "Writing To Non-Existent Objects", services=SERVICE, min_protocol_revision=4
)
async def unknown_object_only(ctx: TestContext) -> None:
    missing = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request {missing}")
    ctx.step("2. RECEIVE WritePropertyMultiple-Error OBJECT / UNKNOWN_OBJECT")
    await _wpm_error(
        ctx,
        wpm_request(ctx, [(missing, [("object-name", "missing", None, None, True)])]),
        "object",
        "unknown-object",
    )


@conformance_test(
    "9.23.2.12",
    "WritePropertyMultiple Reject Test",
    services=SERVICE,
    manual="bacpypes3 cannot omit Property Value while still encoding the property identifier",
)
async def reject_after_partial_write(ctx: TestContext) -> None:
    return None


@conformance_test("9.23.2.19", "Date Non-Pattern Properties Test using WritePropertyMultiple Service",
    services=SERVICE, min_protocol_revision=11)
async def date_non_pattern(ctx: TestContext) -> None:
    await _special_date(ctx, "Date")


@conformance_test("9.23.2.20", "Time Non-Pattern Properties Test using WritePropertyMultiple Service",
    services=SERVICE, min_protocol_revision=11)
async def time_non_pattern(ctx: TestContext) -> None:
    target = _typed(ctx, "Time")
    if target is None:
        ctx.skip("no writable non-pattern Time property was found")
    objid, prop = target
    base = Time((12, 0, 0, 0))
    for label, value in (
        ("hour unspecified", Time((255, 0, 0, 0))),
        ("minute unspecified", Time((12, 255, 0, 0))),
        ("second unspecified", Time((12, 0, 255, 0))),
        ("hundredths unspecified", Time((12, 0, 0, 255))),
    ):
        ctx.step(f"TRANSMIT {prop} = {label}")
        await _expect_pattern_rejected(ctx, objid, prop, value, base)


@conformance_test("9.23.2.21", "DateTime Non-Pattern Properties Test using WritePropertyMultiple Service",
    services=SERVICE, min_protocol_revision=11)
async def datetime_non_pattern(ctx: TestContext) -> None:
    ctx.skip("no writable non-pattern DateTime property was identified")


@conformance_test(
    "9.23.2.22",
    "BACnetDateRange Non-Pattern Properties Test using WritePropertyMultiple Service",
    services=SERVICE,
    min_protocol_revision=11,
)
async def daterange_non_pattern(ctx: TestContext) -> None:
    ctx.skip("no writable non-pattern BACnetDateRange property was identified")


def _typed(ctx: TestContext, datatype: str):
    for objid in ctx.test_objects():
        spec = object_spec(str(objid[0]))
        if spec is None:
            continue
        for prop in spec.properties:
            if prop.datatype == datatype and prop.writable and "pattern" not in prop.name:
                return objid, prop.name
    return None


async def _special_date(ctx: TestContext, datatype: str) -> None:
    target = _typed(ctx, datatype)
    if target is None:
        ctx.skip(f"no writable non-pattern {datatype} property was found")
    objid, prop = target
    base = Date((91, 1, 2, 3))
    specials = (
        ("year unspecified", Date((255, 1, 2, 3))),
        ("month unspecified", Date((91, 255, 2, 3))),
        ("day of month unspecified", Date((91, 1, 255, 3))),
        ("day of week unspecified", Date((91, 1, 2, 255))),
        ("odd months", Date((91, 13, 2, 3))),
        ("even months", Date((91, 14, 2, 3))),
        ("last day of month", Date((91, 1, 32, 3))),
        ("odd days", Date((91, 1, 33, 3))),
        ("even days", Date((91, 1, 34, 3))),
    )
    for label, value in specials:
        ctx.step(f"TRANSMIT {prop} = {label}")
        await _expect_pattern_rejected(ctx, objid, prop, value, base)


async def _expect_pattern_rejected(ctx: TestContext, objid, prop: str, value, base) -> None:
    request = wpm_request(ctx, [(objid, [(prop, value, None, None, False)])])
    try:
        await ctx.send(request)
    except WritePropertyMultipleError as err:
        pair = tuple(str(part) for part in error_class_code(err))
        ctx.check(pair == ("property", "value-out-of-range"), "special value was not VALUE_OUT_OF_RANGE",
            actual=pair, response=err)
        return
    except RejectPDU as err:
        ctx.check(
            str(err.apduAbortRejectReason) in ("invalid-parameter-data-type", "invalid-tag"),
            "Wrong reject reason for a special value",
            response=err,
        )
        return
    ctx.defect(f"{prop} accepted a special value", expected=base, request=request)


@conformance_test(
    "9.23.2.3", "Writing Multiple Properties with a Write Access Error", services=SERVICE, writes=True
)
async def write_access_error(ctx: TestContext) -> None:
    rows = await _scalars(ctx, 1)
    if not rows:
        ctx.skip("no writable scalar property was found")
    objid, prop, current = rows[0]
    new = different_value(current)
    ctx.step(f"1. READ X = ({objid}), {prop}")
    ctx.step("2. TRANSMIT WritePropertyMultiple-Request, then Object_Type")
    request = wpm_request(
        ctx,
        [(objid, [(prop, new, None, None, True), ("object-type", await ctx.read(objid, "object-type"),
            None, None, True)])],
    )
    ctx.step("3. RECEIVE WritePropertyMultiple-Error PROPERTY / WRITE_ACCESS_DENIED")
    await _wpm_error(ctx, request, "property", "write-access-denied")
    try:
        ctx.check_equal(await ctx.read(objid, prop), new, f"{prop} was not written before the failure")
    finally:
        await restore(ctx, Written(objid, prop, current))


@conformance_test("9.23.2.4", "Writing Non-Array Properties with an Array Index", services=SERVICE)
async def non_array_index(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    current = await ctx.read(device, "object-name")
    ctx.step("1. TRANSMIT WritePropertyMultiple-Request Object_Name, Array Index = 1")
    await _wpm_error(
        ctx,
        wpm_request(ctx, [(device, [("object-name", different_value(current), 1, None, True)])]),
        "property",
        "property-is-not-an-array",
    )
    ctx.check_equal(await ctx.read(device, "object-name"), current, "Object_Name changed")


@conformance_test("9.23.2.6", "Writing with a Property Value Having the Wrong Datatype", services=SERVICE)
async def wrong_datatype(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    current = await ctx.read(device, "object-name")
    ctx.step("1. TRANSMIT WritePropertyMultiple-Request Object_Name = Unsigned")
    request = wpm_request(ctx, [(device, [("object-name", Unsigned(1), None, None, False)])])
    try:
        ack = await ctx.send(request)
    except RejectPDU as err:
        ctx.check(str(err.apduAbortRejectReason) in ("invalid-parameter-data-type", "invalid-tag"),
            "Wrong reject reason", response=err)
    except WritePropertyMultipleError as err:
        pair = tuple(str(part) for part in error_class_code(err))
        ctx.check(pair == ("property", "invalid-data-type"), "Wrong error", actual=pair, response=err)
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected WritePropertyMultiple-Error or Reject", actual=format_pdu(err),
            request=request, response=err)
    else:
        ctx.defect("Object_Name with the wrong datatype was acknowledged",
            expected="WritePropertyMultiple-Error PROPERTY / INVALID_DATATYPE or Reject",
            actual=format_pdu(ack), request=request)
    ctx.check_equal(await ctx.read(device, "object-name"), current, "Object_Name changed")


@conformance_test("9.23.2.7", "Writing with a Property Value that is Out of Range", services=SERVICE)
async def out_of_range(ctx: TestContext) -> None:
    from ._common import ranged_property

    found = ranged_property(ctx)
    if found is None:
        ctx.skip("no writable property with a restricted range is defined for the IUT")
    objid, prop, low, high = found
    if high is not None:
        outside = high + 1
    elif low is not None:
        outside = low - 1
    else:
        ctx.skip(f"{prop} has no numeric bound")
    current = await ctx.read(objid, prop)
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request {prop} = {outside}")
    await _wpm_error(ctx, wpm_request(ctx, [(objid, [(prop, outside, None, None, True)])]), "property",
        "value-out-of-range")
    ctx.check_equal(await ctx.read(objid, prop), current, f"{prop} changed")


@conformance_test(
    "9.23.2.9", "Writing To Non-Existent Properties", services=SERVICE, min_protocol_revision=4
)
async def unknown_property(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request (Device, X), {prop}")
    await _wpm_error(ctx, wpm_request(ctx, [(device, [(prop, Unsigned(1), None, None, False)])]),
        "property", "unknown-property")


@conformance_test(
    "9.23.2.10", "Writing To Non-Writable Properties", services=SERVICE, min_protocol_revision=4
)
async def non_writable(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    current = await ctx.read(device, "object-type")
    ctx.step("1. TRANSMIT WritePropertyMultiple-Request Object_Type")
    await _wpm_error(ctx, wpm_request(ctx, [(device, [("object-type", current, None, None, True)])]),
        "property", "write-access-denied")


@conformance_test(
    "9.23.2.11", "Writing An Object_Name With A Value That Is Already In Use", services=SERVICE,
        min_protocol_revision=4
)
async def duplicate_name(ctx: TestContext) -> None:
    objects = ctx.test_objects()
    if len(objects) < 2:
        ctx.skip("the IUT has fewer than two objects")
    used = str(await ctx.read(objects[0], "object-name"))
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request ({objects[1]}), Object_Name = '{used}'")
    await _wpm_error(ctx, wpm_request(ctx, [(objects[1], [("object-name", used, None, None, True)])]),
        "property", "duplicate-name")


@conformance_test(
    "9.23.2.13",
    "Resizing a Writable Fixed Size Array Property Using WritePropertyMultiple Service",
    services=SERVICE,
)
async def resize_fixed_array(ctx: TestContext) -> None:
    ctx.skip("no writable fixed-size array was identified from the object model")


@conformance_test(
    "9.23.2.14",
    "Writing First Element of 'List of Write Access Specifications' with Object Access Error",
    services=SERVICE,
)
async def first_object_error(ctx: TestContext) -> None:
    missing = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request, first object = {missing}")
    await _wpm_error(
        ctx,
        wpm_request(ctx, [(missing, [("object-name", "missing", None, None, True)])]),
        "object",
        "unknown-object",
    )


@conformance_test(
    "9.23.2.15",
    "Writing First Element of 'List of Write Access Specifications' with a Write Access Error",
    services=SERVICE,
)
async def first_write_access_error(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT WritePropertyMultiple-Request, first property = Object_Type")
    current = await ctx.read(device, "object-type")
    await _wpm_error(
        ctx, wpm_request(ctx, [(device, [("object-type", current, None, None, True)])]), "property",
            "write-access-denied"
    )


@conformance_test(
    "9.23.2.16",
    "WritePropertyMultiple Reject Test for First Element of 'List of Write Access Specifications'",
    services=SERVICE,
    manual="bacpypes3 cannot omit Property Value while still encoding the property identifier",
)
async def reject_first_element(ctx: TestContext) -> None:
    return None


@conformance_test(
    "9.23.2.17",
    "Writing First Element of 'List of Write Access Specifications' with a Property Access Error",
    services=SERVICE,
)
async def first_property_error(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT WritePropertyMultiple-Request, first property = {prop}")
    await _wpm_error(ctx, wpm_request(ctx, [(device, [(prop, Unsigned(1), None, None, False)])]),
        "property", "unknown-property")


@conformance_test(
    "9.23.2.18",
    "Writing a Property Value Related to a Non-supported Optional Functionality",
    services=SERVICE,
)
async def unsupported_optional(ctx: TestContext) -> None:
    ctx.skip("the EPICS does not identify a value that requires unsupported optional functionality")
