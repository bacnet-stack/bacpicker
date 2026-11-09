# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.11 SubscribeCOVProperty Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import ErrorPDU, SubscribeCOVPropertyRequest
from bacpypes3.primitivedata import ObjectIdentifier

from ..assertions import error_class_code
from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["subscribe-cov-property"]
_CHANGE = "requires changing the subscribed property and receiving the COV notification that follows"

for _clause, _title in (
    ("9.11.1.1", "Confirmed COV Notifications"),
    ("9.11.1.2", "Unconfirmed COV Notifications"),
    ("9.11.1.3", "Explicit Indefinite Lifetime COV Subscriptions"),
    ("9.11.1.4", "Canceling COV Subscriptions"),
    ("9.11.1.6", "Implied Indefinite Lifetime COV Subscriptions"),
    ("9.11.1.7", "Finite Lifetime Subscriptions"),
    ("9.11.1.8", "Updating Existing Subscriptions"),
    ("9.11.1.9", "Client-Supplied COV Increment"),
    ("9.11.1.11", "Confirmed Change of Value Notification from Property Value"),
    ("9.11.1.12", "Unconfirmed Change of Value Notification from Property Value"),
    ("9.11.1.13", "Confirmed Change of Value Notification from Status_Flags Property"),
    ("9.11.1.14", "Unconfirmed Change of Value Notification from Status_Flags Property"),
):
    register_manual(_clause, _title, _CHANGE, services=SERVICE, writes=True)

register_manual(
    "9.11.1.5",
    "Canceling Expired or Non-Existing Subscriptions",
    "cancels a subscription created by 9.11.1.1, which is not automated",
    services=SERVICE,
)
register_manual(
    "9.11.1.10",
    "Accepts SubscribeCOVProperty-Requests with 8 Hour Lifetimes",
    "requires waiting out an 8 hour subscription lifetime",
    services=SERVICE,
)


def _request(ctx: TestContext, objid: ObjectIdentifier, prop: str,
    lifetime: int = 60) -> SubscribeCOVPropertyRequest:
    return SubscribeCOVPropertyRequest(
        subscriberProcessIdentifier=2101,
        monitoredObjectIdentifier=objid,
        issueConfirmedNotifications=True,
        lifetime=lifetime,
        monitoredPropertyIdentifier=prop,
        destination=ctx.iut.address,
    )


@conformance_test("9.11.2.1", "The Monitored Object Does Not Support COV Notification", services=SERVICE)
async def object_without_cov(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT SubscribeCOVProperty-Request for (Device, X), Object_Name")
    request = _request(ctx, device, "object-name")
    try:
        await ctx.send(request)
    except ErrorPDU as err:
        pair = tuple(str(part) for part in error_class_code(err))
        ctx.check(
            pair in {("object", "optional-functionality-not-supported"), ("services",
                "service-request-denied"), ("property", "not-cov-property")},
            "Wrong error for an object that does not support COV",
            actual=pair,
            response=err,
        )
        return
    ctx.skip("the Device object accepted a COV-property subscription")


@conformance_test("9.11.2.2", "The Monitored Property Does Not Support COV Notification", services=SERVICE)
async def property_without_cov(ctx: TestContext) -> None:
    ctx.skip("no object that supports COV on one property and refuses another was identified")


@conformance_test("9.11.2.3", "Monitored Object Does Not Exist", services=SERVICE)
async def object_does_not_exist(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT SubscribeCOVProperty-Request for {objid}")
    ctx.step("2. RECEIVE OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(_request(ctx, objid, "present-value"), ("object", "unknown-object"))


@conformance_test("9.11.2.4", "Monitored Property Does Not Exist", services=SERVICE)
async def property_does_not_exist(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    (prop,) = ctx.unsupported_properties(device, 1)
    ctx.step(f"1. TRANSMIT SubscribeCOVProperty-Request (Device, X), {prop}")
    ctx.step("2. RECEIVE PROPERTY / UNKNOWN_PROPERTY")
    await ctx.expect_error(_request(ctx, device, prop), ("property", "unknown-property"), ("object",
        "optional-functionality-not-supported"))


@conformance_test("9.11.2.5", "There Is No Space For Subscription", services=SERVICE,
    manual="requires filling the IUT COV-property subscription table")
async def no_space(ctx: TestContext) -> None:
    return None


@conformance_test("9.11.2.6", "The Lifetime Parameter is Out of Range", services=SERVICE)
async def lifetime_out_of_range(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. TRANSMIT SubscribeCOVProperty-Request, Lifetime = 4294967294")
    ctx.step("2. RECEIVE SERVICES / VALUE_OUT_OF_RANGE")
    await ctx.expect_error(_request(ctx, device, "object-name", lifetime=4294967294), ("services",
        "value-out-of-range"))

