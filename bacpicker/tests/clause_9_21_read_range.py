# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.21 ReadRange Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import ReadRangeRequest
from bacpypes3.basetypes import Range, RangeByPosition

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["read-range"]
_LOG = "requires a list or log buffer whose contents the tester knows"

for _clause, _title in (
    ("9.21.1.1", "Reading All Items in the List"),
    ("9.21.1.2", "Reading Items by Position with Positive Count"),
    ("9.21.1.3", "Reading Items by Position with Negative Count"),
    ("9.21.1.4", "Reading Items by Time"),
    ("9.21.1.6", "Reading a Range of Items that do not Exist (by Position)"),
    ("9.21.1.7", "Reading a Range of Items that do not Exist (Using by Sequence)"),
    ("9.21.1.8", "Reading a Range of Items that do Not Exist (Using by Time)"),
    ("9.21.1.9", "Reading Items by Sequence with Positive Count"),
    ("9.21.1.10", "Reading Items by Sequence with Negative Count"),
    ("9.21.1.12", "Status/Failure logging"),
    ("9.21.1.13", "Reading Items with Negative Count and MOREITEMS"),
    ("9.21.1.14", "ReadRange Support for All List Properties"),
):
    register_manual(_clause, _title, _LOG, services=SERVICE)

register_manual(
    "9.21.1.15",
    "ReadRange Service when Non-BACnet Device Offline",
    "requires an object backed by a non-BACnet device that the tester takes offline",
    services=SERVICE,
)


def _request(ctx: TestContext, objid, prop: str, index=None, by_position=None) -> ReadRangeRequest:
    request = ReadRangeRequest(
        objectIdentifier=objid,
        propertyIdentifier=prop,
        destination=ctx.iut.address,
    )
    if index is not None:
        request.propertyArrayIndex = index
    if by_position is not None:
        request.range = Range(byPosition=RangeByPosition(referenceIndex=by_position[0], count=by_position[1]))
    return request


@conformance_test(
    "9.21.2.1",
    "Attempting to Read a Property That Does not Exist",
    services=SERVICE,
    min_protocol_revision=10,
)
async def property_does_not_exist(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT ReadRange-Request (Device, X), {prop}")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / UNKNOWN_PROPERTY")
    await ctx.expect_error(_request(ctx, device, prop), ("property", "unknown-property"))


@conformance_test(
    "9.21.2.2",
    "Attempting to Read a Property That is not a List",
    services=SERVICE,
    min_protocol_revision=10,
)
async def property_is_not_a_list(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT ReadRange-Request (Device, X), Object_Name")
    ctx.step("2. RECEIVE BACnet-Error-PDU SERVICES / PROPERTY_IS_NOT_A_LIST")
    await ctx.expect_error(_request(ctx, device, "object-name"), ("services", "property-is-not-alist"))


@conformance_test(
    "9.21.2.3",
    "Attempting to Read a non-Array Property with an Array Index",
    services=SERVICE,
    min_protocol_revision=10,
)
async def non_array_with_index(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT ReadRange-Request (Device, X), Object_Name, Array Index = 1")
    ctx.step("2. RECEIVE BACnet-Error-PDU PROPERTY / PROPERTY_IS_NOT_AN_ARRAY")
    await ctx.expect_error(_request(ctx, device, "object-name", index=1), ("property",
        "property-is-not-an-array"))


@conformance_test("9.21.2.4", "Reading a Range of Items that do not Exist (by Position)", services=SERVICE)
async def range_does_not_exist(ctx: TestContext) -> None:
    ctx.skip("no list property with a known item count was selected")
