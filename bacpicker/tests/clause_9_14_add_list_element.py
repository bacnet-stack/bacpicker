# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.14 AddListElement Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import AddListElementRequest
from bacpypes3.primitivedata import CharacterString, Unsigned

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["add-list-element"]
_LIST = "requires a standard list property the tester can extend with AddListElement and then restore"

for _clause, _title in (
    ("9.14.1.1", "Adding a Single Element"),
    ("9.14.1.2", "Adding Multiple Elements"),
    ("9.14.1.3", "Adding a Redundant Element"),
    ("9.14.2.3", "An AddListElement Failure Part Way Through a List"),
):
    register_manual(_clause, _title, _LIST, services=SERVICE, writes=True)


def _request(ctx: TestContext, objid, prop: str, value) -> AddListElementRequest:
    return AddListElementRequest(
        objectIdentifier=objid,
        propertyIdentifier=prop,
        listOfElements=value,
        destination=ctx.iut.address,
    )


@conformance_test("9.14.2.1", "Adding a List Element to a Property That is Not a List", services=SERVICE)
async def not_a_list(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT AddListElement-Request (Device, X), Object_Name")
    ctx.step("2. RECEIVE AddListElement-Error SERVICES / PROPERTY_IS_NOT_A_LIST, First Failed Element = 0")
    await ctx.expect_error(
        _request(ctx, device, "object-name", CharacterString("x")),
        ("services", "property-is-not-alist"),
    )


@conformance_test("9.14.2.2", "Adding a List Element With an Invalid Datatype", services=SERVICE)
async def invalid_datatype(ctx: TestContext) -> None:
    from bacpypes3.apdu import ErrorPDU, RejectPDU

    from ..assertions import error_class_code

    device = ctx.iut.device_id
    for prop in ("device-address-binding", "active-cov-subscriptions", "time-synchronization-recipients"):
        if prop not in ctx.model_properties(device):
            continue
        ctx.step(f"1. TRANSMIT AddListElement-Request (Device, X), {prop}, element = Unsigned")
        request = _request(ctx, device, prop, Unsigned(1))
        try:
            await ctx.send(request)
        except RejectPDU as err:
            reason = str(err.apduAbortRejectReason)
            ctx.check(
                reason in ("invalid-parameter-data-type", "invalid-tag"),
                "Wrong reject reason",
                expected="invalid-parameter-data-type | invalid-tag",
                actual=reason,
                response=err,
            )
            return
        except ErrorPDU as err:
            pair = tuple(str(part) for part in error_class_code(err))
            ctx.check(
                pair == ("property", "invalid-data-type"),
                "Wrong error for an invalid list element datatype",
                expected="property / invalid-data-type",
                actual=pair,
                response=err,
            )
            return
        ctx.defect(f"AddListElement of an Unsigned to {prop} was acknowledged", request=request)
        return
    ctx.skip("no Device list property was found to receive an invalid element")
