# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.17 DeleteObject Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import DeleteObjectRequest

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["delete-object"]

register_manual(
    "9.17.1.1",
    "Successful Deletion of an Object",
    "requires an object the PICS declares deletable; the tester does not have that list",
    services=SERVICE,
    writes=True,
)


@conformance_test("9.17.2.1", "Attempting to Delete an Object That is Not Deletable", services=SERVICE)
async def not_deletable(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. READ V1 = (Device, X), Object_Name")
    name = await ctx.read(device, "object-name")
    ctx.step("2. TRANSMIT DeleteObject-Request (Device, X)")
    ctx.step("3. RECEIVE BACnet-Error-PDU OBJECT / OBJECT_DELETION_NOT_PERMITTED")
    await ctx.expect_error(
        DeleteObjectRequest(objectIdentifier=device, destination=ctx.iut.address),
        ("object", "object-deletion-not-permitted"),
    )
    ctx.step("4. VERIFY Object_Name = V1")
    ctx.check_equal(await ctx.read(device, "object-name"), name, "Object_Name changed")
    ctx.step("5. VERIFY Object_List still contains the Device object")
    listed = list(await ctx.read(device, "object-list"))
    ctx.check(device in listed, "Device object is no longer in Object_List", actual=listed)


@conformance_test("9.17.2.2", "Attempting to Delete an Object That Does Not Exist", services=SERVICE)
async def does_not_exist(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT DeleteObject-Request {objid}")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(
        DeleteObjectRequest(objectIdentifier=objid, destination=ctx.iut.address),
        ("object", "unknown-object"),
    )
