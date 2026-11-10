# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.9 LifeSafetyOperation Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import LifeSafetyOperationRequest
from bacpypes3.primitivedata import CharacterString

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["life-safety-operation"]
_POSITIVE = "requires a life-safety object that can be reset or silenced from its current state"

for _clause, _title in (
    ("9.9.1.1", "Reset Single Object Execution Tests"),
    ("9.9.1.2", "Reset Multiple Object Execution Tests"),
    ("9.9.1.3", "Silencing/Unsilencing Execution Tests"),
):
    register_manual(_clause, _title, _POSITIVE, services=SERVICE)


def _request(ctx: TestContext, objid) -> LifeSafetyOperationRequest:
    return LifeSafetyOperationRequest(
        requestingProcessIdentifier=1,
        requestingSource=CharacterString("bacpicker"),
        request="reset",
        objectIdentifier=objid,
        destination=ctx.iut.address,
    )


@conformance_test("9.9.2.1", "LifeSafetyOperation for an Object Which Does Not Exist", services=SERVICE)
async def object_does_not_exist(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id("life-safety-point")
    ctx.step(f"1. TRANSMIT LifeSafetyOperation-Request RESET, Object Identifier = {objid}")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(_request(ctx, objid), ("object", "unknown-object"))


register_manual(
    "9.9.2.2",
    "LifeSafetyOperation which is Invalid given the Object's Current State",
    "requires a life-safety object in a state where a normally accepted operation is invalid",
    services=SERVICE,
)


@conformance_test("9.9.2.3", "LifeSafetyOperation On An Object Which Does Not Support It", services=SERVICE)
async def object_does_not_support_it(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT LifeSafetyOperation-Request RESET for the Device object")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / OPTIONAL_FUNCTIONALITY_NOT_SUPPORTED")
    await ctx.expect_error(_request(ctx, device), ("object", "optional-functionality-not-supported"))
