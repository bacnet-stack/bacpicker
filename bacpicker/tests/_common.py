# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Building blocks shared by the 135.1 test modules (135.1 test language: READ, VERIFY, ...)."""

from __future__ import annotations

import uuid
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple, Union

from bacpypes3.apdu import (
    ErrorRejectAbortNack,
    ReadPropertyACK,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
    ReadPropertyRequest,
    SimpleAckPDU,
    WritePropertyMultipleRequest,
    WritePropertyRequest,
)
from bacpypes3.basetypes import (
    PriorityValue,
    PropertyIdentifier,
    PropertyReference,
    PropertyValue,
    ReadAccessSpecification,
    WriteAccessSpecification,
)
from bacpypes3.constructeddata import Array, SequenceOf
from bacpypes3.primitivedata import Boolean, Enumerated, Null, ObjectIdentifier, ObjectType, Unsigned

from ..assertions import SkipTest, format_pdu
from ..context import BASE_TYPES, TestContext, application_tag, base_type, value_tags
from ..registry import conformance_test
from ..standard import object_spec

MAX_INSTANCE = 4194303
COMMON_PROPERTIES = ("object-identifier", "object-name", "object-type")

PropSpec = Union[str, Tuple[str, int]]
AccessSpecs = Sequence[Tuple[ObjectIdentifier, Sequence[PropSpec]]]


# ---- requests --------------------------------------------------------------


def rp_request(
    ctx: TestContext, objid: ObjectIdentifier, prop: str, index: Optional[int] = None
) -> ReadPropertyRequest:
    request = ReadPropertyRequest(
        objectIdentifier=objid,
        propertyIdentifier=PropertyIdentifier(prop),
        destination=ctx.iut.address,
    )
    if index is not None:
        request.propertyArrayIndex = index
    return request


def rpm_request(ctx: TestContext, specs: AccessSpecs) -> ReadPropertyMultipleRequest:
    access_specs = []
    for objid, props in specs:
        refs = []
        for prop in props:
            name, index = (prop, None) if isinstance(prop, str) else prop
            ref = PropertyReference(propertyIdentifier=PropertyIdentifier(name))
            if index is not None:
                ref.propertyArrayIndex = index
            refs.append(ref)
        access_specs.append(
            ReadAccessSpecification(objectIdentifier=objid, listOfPropertyReferences=refs)
        )
    return ReadPropertyMultipleRequest(
        listOfReadAccessSpecs=SequenceOf(ReadAccessSpecification)(access_specs),
        destination=ctx.iut.address,
    )


class Element(NamedTuple):
    """One property result from a ReadProperty-ACK or ReadPropertyMultiple-ACK."""

    objid: ObjectIdentifier
    prop: str
    array_index: Optional[int]
    value: Any
    error: Any

    @property
    def prop_number(self) -> int:
        return prop_number(self.prop)

    def label(self) -> str:
        suffix = f"[{self.array_index}]" if self.array_index is not None else ""
        return f"{self.objid} {self.prop}{suffix}"


def prop_number(name: str) -> int:
    return int(name) if name.isdigit() else int(PropertyIdentifier(name))


def is_standard_property(name: str) -> bool:
    return prop_number(name) < 512


def rpm_elements(ack: ReadPropertyMultipleACK) -> List[Element]:
    return [
        Element(
            objid=result.objectIdentifier,
            prop=str(element.propertyIdentifier),
            array_index=element.propertyArrayIndex,
            value=element.readResult.propertyValue,
            error=element.readResult.propertyAccessError,
        )
        for result in ack.listOfReadAccessResults
        for element in result.listOfResults
    ]


async def read_one(
    ctx: TestContext,
    objid: ObjectIdentifier,
    prop: str,
    index: Optional[int] = None,
    *,
    service: str = "rp",
) -> Optional[Element]:
    """Read one property with ReadProperty ("rp") or ReadPropertyMultiple ("rpm").

    Error/Reject/Abort PDUs are raised; an RPM embedded error is returned in Element.error.
    Returns None (after recording a defect) if the ACK is malformed.
    """
    if service == "rp":
        request = rp_request(ctx, objid, prop, index)
        ack = await ctx.send(request)
        if not ctx.check(
            isinstance(ack, ReadPropertyACK),
            "Unexpected acknowledgement type",
            expected="ReadProperty-ACK",
            actual=type(ack).__name__,
            request=request,
        ):
            return None
        return Element(
            ack.objectIdentifier, str(ack.propertyIdentifier), ack.propertyArrayIndex,
            ack.propertyValue, None,
        )

    request = rpm_request(ctx, [(objid, [prop if index is None else (prop, index)])])
    ack = await ctx.send(request)
    elements = rpm_elements(ack) if isinstance(ack, ReadPropertyMultipleACK) else []
    if not ctx.check(
        len(elements) == 1,
        "ReadPropertyMultiple-ACK does not contain exactly one result",
        expected="ReadPropertyMultiple-ACK with one result",
        actual=format_pdu(ack),
        request=request,
    ):
        return None
    return elements[0]


def check_echo(
    ctx: TestContext,
    element: Element,
    objid: ObjectIdentifier,
    prop: str,
    index: Optional[int] = None,
) -> bool:
    expected = Element(objid, prop, index, None, None).label()
    return ctx.check(
        (element.objid, element.prop, element.array_index) == (objid, prop, index),
        "ACK does not identify the requested object/property/array index",
        expected=expected,
        actual=element.label(),
    )


def check_value(ctx: TestContext, element: Element, message: str = "") -> bool:
    """CHECK (V is any valid value of the correct data type for the property)."""
    if element.error is not None:
        return ctx.check(
            False,
            message or f"Expected a value for {element.label()}",
            expected="property value",
            actual=f"error-class={element.error.errorClass}, error-code={element.error.errorCode}",
        )
    ptype = ctx.property_type(element.objid, element.prop)
    if element.array_index is not None and isinstance(ptype, type) and issubclass(ptype, Array):
        ptype = Unsigned if element.array_index == 0 else ptype._subtype
    base = base_type(ptype)
    if base is not None:
        expected_tag = dict(BASE_TYPES)[base]
        actual_tag = application_tag(element.value)
        if not ctx.check(
            actual_tag == expected_tag,
            message or f"Value of {element.label()} has the wrong data type",
            expected=f"{base.__name__} (application tag {expected_tag})",
            actual=f"application tag {actual_tag}" if actual_tag is not None else "not a primitive value",
        ):
            return False
    try:
        ctx.decode(element.objid, element.prop, element.array_index, element.value)
    except Exception as err:
        return ctx.check(
            False,
            message or f"Value of {element.label()} cannot be decoded",
            expected=getattr(ptype, "__name__", "valid value"),
            actual=f"{type(err).__name__}: {err}",
        )
    return True


def tag_signature(value: Any) -> List[Tuple[int, int, bytes]]:
    tags = value_tags(value)
    return [(int(t.tag_class), int(t.tag_number), bytes(t.tag_data or b"")) for t in tags]


async def verify(
    ctx: TestContext,
    objid: ObjectIdentifier,
    prop: str,
    expected: Any,
    index: Optional[int] = None,
    *,
    service: str = "rp",
    source: str = "",
) -> Optional[Element]:
    """VERIFY (objid), prop = expected. source names where the expected value came from."""
    element = await read_one(ctx, objid, prop, index, service=service)
    if element is None:
        return None
    check_echo(ctx, element, objid, prop, index)
    if not check_value(ctx, element):
        return element
    value = ctx.decode(objid, prop, index, element.value)
    if isinstance(expected, list):
        value = list(value)
    ctx.check(
        value == expected,
        f"{element.label()} does not have the expected value" + (f" ({source})" if source else ""),
        expected=expected,
        actual=value,
    )
    return element


def all_objects(ctx: TestContext) -> List[ObjectIdentifier]:
    """Every object in the IUT, for checks against a device-wide summary.

    Raises SkipTest when --max-objects truncates the scan, since an object outside the scan
    could make a correct summary look wrong.
    """
    if not ctx.iut.object_list:
        raise SkipTest("Object_List was not read; a device-wide summary needs every object")
    objects = [ctx.iut.device_id] + [o for o in ctx.iut.object_list if o != ctx.iut.device_id]
    limit = max(1, ctx.config.max_objects)
    if len(objects) > limit:
        raise SkipTest(
            f"the IUT has {len(objects)} objects but --max-objects is {limit}; "
            "a device-wide summary needs every object"
        )
    return objects


def iut_instance_ranges(ctx: TestContext) -> dict:
    """Device instance ranges relative to the IUT instance X used by 9.32 / 9.33."""
    x = ctx.iut.device_instance
    return {
        "inside": (x - 1, x + 1) if 0 < x < MAX_INSTANCE else None,
        "low_equal": (x, x + 1) if x < MAX_INSTANCE else None,
        "high_equal": (x - 1, x) if x > 0 else None,
    }


# ---- shared procedures -------------------------------------------------------


async def reading_properties_based_on_data_type(ctx: TestContext, service: str) -> None:
    """9.18.1.5 / 9.20.1.13: read one property of each supported base data type."""
    covered = {}
    all_bases = [b for b, _ in BASE_TYPES]
    for objid in ctx.test_objects():
        property_list = await ctx.property_list(objid)
        props = list(COMMON_PROPERTIES) + (
            property_list if property_list is not None else sorted(ctx.model_properties(objid))
        )
        for prop in props:
            if not is_standard_property(prop):
                continue
            base = base_type(ctx.property_type(objid, prop))
            if base is None or base in covered:
                continue
            ctx.step(f"1. READ V = ({objid}), {prop}  [{base.__name__}]")
            try:
                element = await read_one(ctx, objid, prop, service=service)
            except ErrorRejectAbortNack as err:
                if property_list is not None and prop in property_list:
                    ctx.defect(
                        f"Property {prop} listed in Property_List could not be read",
                        expected="property value",
                        actual=format_pdu(err),
                    )
                continue
            if element is None:
                continue
            if element.error is not None and (property_list is None or prop not in property_list):
                continue
            ctx.step(f"2. CHECK (V is a valid {base.__name__} value)")
            check_echo(ctx, element, objid, prop)
            check_value(ctx, element)
            covered[base] = f"{objid} {prop}"
        if len(covered) == len(all_bases):
            break
    for base, where in covered.items():
        ctx.note(f"{base.__name__}: {where}")
    missing = [b.__name__ for b in all_bases if b not in covered]
    if missing:
        ctx.note("no property found for data type(s): " + ", ".join(missing))
    if not covered:
        ctx.skip("no readable property of a known base data type was found")


async def network_port_unknown_instance(ctx: TestContext, service: str) -> None:
    """9.18.1.8 / 9.20.1.14: read the Network Port object using instance 4194303."""
    ports = [o for o in ctx.iut.object_list if str(o[0]) == "network-port"]
    if not ports:
        ctx.skip("IUT has no Network Port object")
    wildcard = ObjectIdentifier((ObjectType("network-port"), MAX_INSTANCE))

    ctx.step(f"1. TRANSMIT {service.upper()} ({wildcard}), Object_Identifier")
    element = await read_one(ctx, wildcard, "object-identifier", service=service)
    if element is None:
        return
    ctx.step("2. RECEIVE ACK 'Object Identifier' = (Network Port, X), value = (Network Port, X)")
    if not check_value(ctx, element):
        return
    port = element.objid
    ctx.require(
        port in ports,
        "ACK does not identify one of the IUT's Network Port objects",
        expected=f"one of {[str(p) for p in ports]}",
        actual=port,
    )
    ctx.check_equal(
        ctx.decode(port, "object-identifier", None, element.value),
        port,
        "Object_Identifier value differs from the object identified in the ACK",
    )

    props = await ctx.property_list(port)
    if props is None:
        ctx.note("Property_List unreadable; using the tester's object model")
        props = sorted(ctx.model_properties(port))
    for prop in list(COMMON_PROPERTIES) + [p for p in props if p not in COMMON_PROPERTIES]:
        ctx.step(f"3. REPEAT P = {prop}: read via ({wildcard}) and VERIFY ({port}), {prop} = V")
        try:
            via_wildcard = await read_one(ctx, wildcard, prop, service=service)
        except ErrorRejectAbortNack as err:
            ctx.defect(f"Reading {prop} via instance 4194303 failed", actual=format_pdu(err))
            continue
        if via_wildcard is None or via_wildcard.error is not None:
            continue
        ctx.check_equal(via_wildcard.objid, port, "ACK 'Object Identifier' is not (Network Port, X)")
        direct = await read_one(ctx, port, prop, service=service)
        if direct is None or direct.error is not None:
            continue
        ctx.check(
            tag_signature(direct.value) == tag_signature(via_wildcard.value),
            f"{prop} read via instance 4194303 differs from the value read from {port}",
            expected=ctx.decode(port, prop, None, direct.value),
            actual=ctx.decode(port, prop, None, via_wildcard.value),
        )


# ---- writes ----------------------------------------------------------------


class Written(NamedTuple):
    """A property the tester changed, so the test can put the previous value back."""

    objid: ObjectIdentifier
    prop: str
    previous: Any
    array_index: Optional[int] = None
    priority: Optional[int] = None


def register_manual(clause: str, title: str, reason: str, **options: Any):
    """Register a 135.1 procedure the tester cannot execute, reported as SKIP."""

    async def test(ctx: TestContext) -> None:
        return None

    test.__name__ = "manual_" + clause.replace(".", "_").replace("-", "_")
    return conformance_test(clause, title, manual=reason, **options)(test)


def is_array(ptype: Any) -> bool:
    return isinstance(ptype, type) and issubclass(ptype, Array)


def cast_property(ctx: TestContext, objid: ObjectIdentifier, prop: str, value: Any,
    index: Optional[int] = None) -> Any:
    """Encode value as the property's datatype. index selects an array element or the size."""
    ptype = ctx.property_type(objid, prop)
    if not isinstance(ptype, type):
        return value
    if issubclass(ptype, Array):
        ptype = Unsigned if index == 0 else (ptype._subtype if index is not None else ptype)
    if isinstance(value, (ptype, Null)):
        return value
    return ptype(value)


_ENUM_ALTERNATES = {
    "active": "inactive",
    "inactive": "active",
    "operational": "operational-read-only",
    "operational-read-only": "operational",
}


def different_value(current: Any) -> Any:
    """Another valid value of the same primitive type, or None when none is known."""
    # Enumerated and Boolean are int subclasses in bacpypes3, so test them before int
    if isinstance(current, Enumerated):
        return _ENUM_ALTERNATES.get(str(current))
    if isinstance(current, (bool, Boolean)):
        return not bool(current)
    if isinstance(current, float):
        return current + 1.0
    if isinstance(current, int):
        return current + 1
    if isinstance(current, str):
        return f"{current}-{uuid.uuid4().hex[:4]}"
    return _ENUM_ALTERNATES.get(str(current))


def wp_request(
    ctx: TestContext,
    objid: ObjectIdentifier,
    prop: str,
    value: Any,
    index: Optional[int] = None,
    priority: Optional[int] = None,
    *,
    cast: bool = True,
) -> WritePropertyRequest:
    request = WritePropertyRequest(
        objectIdentifier=objid,
        propertyIdentifier=PropertyIdentifier(prop),
        propertyValue=cast_property(ctx, objid, prop, value, index) if cast else value,
        destination=ctx.iut.address,
    )
    if index is not None:
        request.propertyArrayIndex = index
    if priority is not None:
        request.priority = priority
    return request


def _property_value(
    ctx: TestContext,
    objid: ObjectIdentifier,
    prop: str,
    value: Any,
    index: Optional[int],
    priority: Optional[int],
    cast: bool,
) -> PropertyValue:
    item = PropertyValue(
        propertyIdentifier=PropertyIdentifier(prop),
        value=cast_property(ctx, objid, prop, value, index) if cast else value,
    )
    if index is not None:
        item.propertyArrayIndex = index
    if priority is not None:
        item.priority = priority
    return item


def wpm_request(
    ctx: TestContext,
    groups: Sequence[Tuple[ObjectIdentifier, Sequence[Tuple]]],
) -> WritePropertyMultipleRequest:
    """groups are (object, [(prop, value, index, priority, cast), ...]). cast defaults to True."""
    specs = []
    for objid, props in groups:
        items = []
        for spec in props:
            prop, value = spec[0], spec[1]
            index = spec[2] if len(spec) > 2 else None
            priority = spec[3] if len(spec) > 3 else None
            cast = spec[4] if len(spec) > 4 else True
            items.append(_property_value(ctx, objid, prop, value, index, priority, cast))
        specs.append(
            WriteAccessSpecification(
                objectIdentifier=objid,
                listOfProperties=SequenceOf(PropertyValue)(items),
            )
        )
    return WritePropertyMultipleRequest(
        listOfWriteAccessSpecs=SequenceOf(WriteAccessSpecification)(specs),
        destination=ctx.iut.address,
    )


async def restore(ctx: TestContext, change: Written) -> None:
    """Put a property back. A failed restore is recorded; it is not part of the 135.1 procedure."""
    try:
        await ctx.app.write_property(
            ctx.iut.address,
            change.objid,
            change.prop,
            change.previous,
            change.array_index,
            change.priority,
        )
    except ErrorRejectAbortNack as err:
        ctx.defect(
            f"Could not restore {change.objid} {change.prop}",
            expected=change.previous,
            actual=format_pdu(err),
        )


async def expect_simple_ack(ctx: TestContext, request: Any) -> bool:
    ack = await ctx.expect_ack(request, SimpleAckPDU)
    return ack is not None


def priority_slot_value(slot: Any) -> Any:
    """The application value held in a BACnetPriorityValue; Null for an empty slot."""
    if not isinstance(slot, PriorityValue):
        return slot
    for name in PriorityValue._elements:
        value = getattr(slot, name, None)
        if value is not None:
            return Null(()) if name == "null" else value
    return Null(())


def restore_priority_slot(objid: ObjectIdentifier, slot: Any, priority: int = 16) -> Written:
    """Put back a Priority_Array entry read before a write: relinquish only if it was NULL."""
    value = priority_slot_value(slot)
    if isinstance(value, Enumerated):
        value = int(value)
    return Written(objid, "present-value", value, priority=priority)


async def writable_properties(ctx: TestContext, objid: ObjectIdentifier) -> List[str]:
    """Properties known to be writable: conformance code W, or accepted by the --allow-writes
    write-back probe. Commandable properties are excluded, since a write changes the priority array."""
    spec = object_spec(str(objid[0]))
    commandable = {p.name for p in spec.properties if p.commandable} if spec else set()
    names = {p.name for p in spec.properties if p.writable} if spec else set()
    database = await ctx.test_database()
    record = database.objects.get(objid)
    if record is not None:
        # A conformance-code W property the device does not have is not writable here.
        # A whole-array read can fail because the value is too large; the property is
        # still present and an indexed read may succeed.
        present = {name for name, prop in record.properties.items() if prop.present}
        names &= present
        for name, prop in record.properties.items():
            if prop.writable is True:
                names.add(name)
            elif prop.writable is False:
                names.discard(name)
        priority_array = record.properties.get("priority-array")
        if priority_array is not None and priority_array.error is None:
            commandable.add("present-value")
    return sorted(names - commandable)


def read_only_property(ctx: TestContext) -> Tuple[ObjectIdentifier, str, Any]:
    """A present property whose conformance code is not W. Raises SkipTest when none is known."""
    for objid in ctx.test_objects():
        spec = object_spec(str(objid[0]))
        if spec is None:
            continue
        for prop in spec.properties:
            if prop.writable is not False or prop.commandable:
                continue
            return objid, prop.name, None
    raise SkipTest("no read-only standard property is known for the IUT's object types")


def property_is_present(ctx: TestContext, objid, name: str) -> bool:
    """True when the property was read from the IUT, or when the test database is not loaded yet."""
    database = ctx.shared.get("database")
    if database is None:
        return True
    record = database.objects.get(objid)
    prop = record.properties.get(name) if record is not None else None
    return prop is not None and prop.error is None


def ranged_property(ctx: TestContext):
    """(objid, property name, minimum, maximum) for a writable property with a numeric range."""
    for objid in ctx.test_objects():
        spec = object_spec(str(objid[0]))
        if spec is None:
            continue
        for prop in spec.properties:
            if not prop.writable:
                continue
            if prop.minimum is None and prop.maximum is None:
                continue
            if not property_is_present(ctx, objid, prop.name):
                continue
            return objid, prop.name, prop.minimum, prop.maximum
    return None
