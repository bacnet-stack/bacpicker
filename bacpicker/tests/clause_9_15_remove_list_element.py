# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.15 RemoveListElement Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import RemoveListElementRequest
from bacpypes3.primitivedata import CharacterString

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["remove-list-element"]
_LIST = "requires a standard list property the tester can remove elements from and then restore"

for _clause, _title in (
    ("9.15.1.1", "Removing a Single Element from a List"),
    ("9.15.1.2", "Removing Multiple Elements from a List"),
    ("9.15.2.2", "A RemoveListElement Failure Part Way Through a List"),
):
    register_manual(_clause, _title, _LIST, services=SERVICE, writes=True)


@conformance_test(
    "9.15.2.1", "Removing a List Element from a Property That is Not a List", services=SERVICE
)
async def not_a_list(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT RemoveListElement-Request (Device, X), Object_Name")
    ctx.step("2. RECEIVE RemoveListElement-Error SERVICES / PROPERTY_IS_NOT_A_LIST")
    await ctx.expect_error(
        RemoveListElementRequest(
            objectIdentifier=device,
            propertyIdentifier="object-name",
            listOfElements=CharacterString("x"),
            destination=ctx.iut.address,
        ),
        ("services", "property-is-not-alist"),
    )
