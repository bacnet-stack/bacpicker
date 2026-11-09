# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.16 CreateObject Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import CreateObjectRequest
from bacpypes3.basetypes import CreateObjectRequestObjectSpecifier
from bacpypes3.primitivedata import ObjectIdentifier, ObjectType

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["create-object"]
_CREATABLE = (
    "requires an object type the PICS declares dynamically creatable; the tester does not have that list"
)

for _clause, _title, _writes in (
    ("9.16.1.1", "Creating Objects by Specifying the Object Type with No Initial Values", True),
    ("9.16.1.2", "Creating Objects by Specifying the Object Identifier with No Initial Values", True),
    ("9.16.1.3", "Creating Objects by Specifying the Object Type and Providing Initial Values", True),
    ("9.16.1.4", "Creating Objects by Specifying the Object Identifier and Providing Initial Values", True),
    ("9.16.2.1", "Attempting to Create an Object That Does Not Have a Unique Object Identifier", False),
    ("9.16.2.2", "Attempting to Create an Object with an Object Type That is Not Creatable by "
        "Specifying the Object Type", False),
    ("9.16.2.3", "Attempting to Create an Object with an Object Identifier That is Not Creatable by "
        "Specifying the Object Identifier", False),
    ("9.16.2.4", "Attempting to Create an Object with an Object Type Specifier and an Error in the "
        "Initial Values", False),
    ("9.16.2.5", "Attempting to Create an Object with an Object Identifier and an Error in the"
        "Initial Values", False),
):
    register_manual(_clause, _title, _CREATABLE, services=SERVICE, writes=_writes)


def _unsupported_type(ctx: TestContext) -> str:
    """A standard object type whose Protocol_Object_Types_Supported bit the IUT clears."""
    length = ctx.iut.object_types_supported_length
    if not ctx.iut.object_types_supported or not length:
        ctx.skip("Protocol_Object_Types_Supported was not read; no known-unsupported object type")
    numbers = {}
    for name, number in ObjectType._enum_map.items():
        numbers.setdefault(number, name)
    for number in sorted(numbers):
        name = numbers[number]
        if number < length and not ctx.iut.supports_object_type(name):
            return name
    ctx.skip("Protocol_Object_Types_Supported lists every standard object type it encodes")


@conformance_test(
    "9.16.2.7",
    "Attempting to Create a non-Supported Object Type (by Object Type)",
    services=SERVICE,
)
async def unsupported_by_type(ctx: TestContext) -> None:
    name = _unsupported_type(ctx)
    before = list(ctx.iut.object_list)
    ctx.step(f"1. TRANSMIT CreateObject-Request, Object Specifier = {name}")
    request = CreateObjectRequest(
        objectSpecifier=CreateObjectRequestObjectSpecifier(objectType=ObjectType(name)),
        destination=ctx.iut.address,
    )
    revision = ctx.iut.protocol_revision or 0
    if revision >= 10:
        ctx.step("2. RECEIVE CreateObject-Error OBJECT / UNSUPPORTED_OBJECT_TYPE")
        await ctx.expect_error(request, ("object", "unsupported-object-type"))
    else:
        ctx.step("2. RECEIVE CreateObject-Error")
        await ctx.expect_error(request, ("object", "unsupported-object-type"), ("object",
            "dynamic-creation-not-supported"))
    ctx.step("3. VERIFY Object_List does not contain a new object of that type")
    after = list(await ctx.read(ctx.iut.device_id, "object-list"))
    ctx.check(after == before, "Object_List changed", expected=len(before), actual=len(after))


@conformance_test(
    "9.16.2.8",
    "Attempting to Create a non-Supported Object Type (by Object Identifier)",
    services=SERVICE,
)
async def unsupported_by_identifier(ctx: TestContext) -> None:
    name = _unsupported_type(ctx)
    objid = ObjectIdentifier((ObjectType(name), 4194300))
    before = list(ctx.iut.object_list)
    ctx.step(f"1. TRANSMIT CreateObject-Request, Object Specifier = {objid}")
    request = CreateObjectRequest(
        objectSpecifier=CreateObjectRequestObjectSpecifier(objectIdentifier=objid),
        destination=ctx.iut.address,
    )
    if (ctx.iut.protocol_revision or 0) >= 10:
        ctx.step("2. RECEIVE CreateObject-Error OBJECT / UNSUPPORTED_OBJECT_TYPE")
        await ctx.expect_error(request, ("object", "unsupported-object-type"))
    else:
        await ctx.expect_error(request, ("object", "unsupported-object-type"), ("object",
            "dynamic-creation-not-supported"))
    after = list(await ctx.read(ctx.iut.device_id, "object-list"))
    ctx.check(objid not in after and after == before, "Object_List changed", expected=len(before),
        actual=len(after))
