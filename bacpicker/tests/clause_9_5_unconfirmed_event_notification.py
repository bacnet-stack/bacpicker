# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.5 UnconfirmedEventNotification Service Execution Tests."""

from __future__ import annotations

from typing import Optional

from bacpypes3.apdu import UnconfirmedEventNotificationRequest
from bacpypes3.basetypes import (
    NotificationParameters,
    NotificationParametersChangeOfState,
    PropertyStates,
    TimeStamp,
)
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, Time

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["unconfirmed-event-notification"]


def _request(
    ctx: TestContext, message: Optional[CharacterString] = None
) -> UnconfirmedEventNotificationRequest:
    request = UnconfirmedEventNotificationRequest(
        processIdentifier=1,
        initiatingDeviceIdentifier=ctx.app.device_object.objectIdentifier,
        eventObjectIdentifier=ObjectIdentifier("event-enrollment,1"),
        timeStamp=TimeStamp(time=Time((0, 0, 0, 0))),
        notificationClass=1,
        priority=100,
        eventType="change-of-state",
        notifyType="alarm",
        toState="offnormal",
        eventValues=NotificationParameters(
            changeOfState=NotificationParametersChangeOfState(
                newState=PropertyStates(binaryValue="active"),
                statusFlags=[0, 0, 0, 0],
            )
        ),
        destination=ctx.iut.address,
    )
    if message is not None:
        request.messageText = message
    return request


async def _send(ctx: TestContext, request) -> None:
    ctx.step("1. TRANSMIT UnconfirmedEventNotification-Request")
    await ctx.app.request(request)
    ctx.step("2. CHECK vendor-defined observable actions")
    ctx.note("no vendor-defined action is declared for UnconfirmedEventNotification")
    await ctx.read(ctx.iut.device_id, "object-name")


@conformance_test("9.5.1", "UnconfirmedEventNotification Simple Presentation", services=SERVICE)
async def simple_presentation(ctx: TestContext) -> None:
    await _send(ctx, _request(ctx, CharacterString("bacpicker")))


@conformance_test("9.5.2", "UnconfirmedEventNotification Full Presentation", services=SERVICE)
async def full_presentation(ctx: TestContext) -> None:
    await _send(ctx, _request(ctx, CharacterString("bacpicker")))


@conformance_test(
    "9.5.3",
    "Unsupported Message Text Character Set UnconfirmedEventNotification Test",
    services=SERVICE,
    manual="requires a message text whose character set the IUT does not support",
)
async def unsupported_character_set(ctx: TestContext) -> None:
    return None


@conformance_test(
    "9.5.4",
    "Decoding BACnetPropertyStates in 'Event Values'",
    services=SERVICE,
    manual="requires the IUT to expose the decoded Event Values of a received notification",
)
async def decoding_property_states(ctx: TestContext) -> None:
    return None
