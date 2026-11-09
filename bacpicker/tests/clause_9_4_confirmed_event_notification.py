# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.4 ConfirmedEventNotification Service Execution Tests.

BACnet requires only that the IUT return a SimpleACK. Vendor-defined actions are
noted when the EPICS does not declare any.
"""

from __future__ import annotations

from typing import Optional

from bacpypes3.apdu import ConfirmedEventNotificationRequest
from bacpypes3.basetypes import (
    DateTime,
    NotificationParameters,
    NotificationParametersChangeOfState,
    PropertyStates,
    TimeStamp,
)
from bacpypes3.primitivedata import CharacterString, Date, ObjectIdentifier, Time

from ..context import TestContext
from ..registry import conformance_test
from ._common import expect_simple_ack

SERVICE = ["confirmed-event-notification"]


def _request(ctx: TestContext, stamp: TimeStamp, message: Optional[CharacterString] = None):
    request = ConfirmedEventNotificationRequest(
        processIdentifier=1,
        initiatingDeviceIdentifier=ctx.app.device_object.objectIdentifier,
        eventObjectIdentifier=ObjectIdentifier("event-enrollment,1"),
        timeStamp=stamp,
        notificationClass=1,
        priority=100,
        eventType="change-of-state",
        notifyType="alarm",
        ackRequired=False,
        fromState="normal",
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


def _time() -> TimeStamp:
    return TimeStamp(time=Time((0, 0, 0, 0)))


async def _execute(ctx: TestContext, request, form: str) -> None:
    ctx.step(f"1. TRANSMIT ConfirmedEventNotification-Request ({form})")
    ctx.step("2. RECEIVE BACnet-SimpleACK-PDU")
    if await expect_simple_ack(ctx, request):
        ctx.step("3. CHECK vendor-defined observable actions")
        ctx.note("no vendor-defined action is declared for ConfirmedEventNotification")


@conformance_test(
    "9.4.1",
    "ConfirmedEventNotification Using the Time Form of the 'Timestamp' Parameter and Conveying a"
        "Message Text",
    services=SERVICE,
)
async def time_form_with_message(ctx: TestContext) -> None:
    await _execute(ctx, _request(ctx, _time(), CharacterString("bacpicker")), "Time, with Message Text")


@conformance_test(
    "9.4.2",
    "ConfirmedEventNotification Using the DateTime Form of the 'Timestamp' Parameter and no Message Text",
    services=SERVICE,
)
async def datetime_form(ctx: TestContext) -> None:
    stamp = TimeStamp(dateTime=DateTime(date=Date((90, 1, 1, 1)), time=Time((0, 0, 0, 0))))
    await _execute(ctx, _request(ctx, stamp), "DateTime, no Message Text")


@conformance_test(
    "9.4.3",
    "ConfirmedEventNotification Using the Sequence Number Form of the 'Timestamp' Parameter and no"
        "Message Text",
    services=SERVICE,
)
async def sequence_form(ctx: TestContext) -> None:
    await _execute(ctx, _request(ctx, TimeStamp(sequenceNumber=1)), "sequence number, no Message Text")


@conformance_test("9.4.5", "ConfirmedEventNotification Simple Presentation", services=SERVICE)
async def simple_presentation(ctx: TestContext) -> None:
    await _execute(ctx, _request(ctx, _time(), CharacterString("bacpicker")), "simple presentation")


@conformance_test("9.4.6", "ConfirmedEventNotification Full Presentation", services=SERVICE)
async def full_presentation(ctx: TestContext) -> None:
    await _execute(ctx, _request(ctx, _time(), CharacterString("bacpicker")), "full presentation")


@conformance_test(
    "9.4.7",
    "Unsupported Message Text Character Set ConfirmedEventNotification Test",
    services=SERVICE,
    manual="requires a message text whose character set the IUT does not support",
)
async def unsupported_character_set(ctx: TestContext) -> None:
    return None


@conformance_test(
    "9.4.8",
    "Decoding BACnetPropertyStates in 'Event Values'",
    services=SERVICE,
    manual="requires the IUT to expose the decoded Event Values of a received notification",
)
async def decoding_property_states(ctx: TestContext) -> None:
    return None
