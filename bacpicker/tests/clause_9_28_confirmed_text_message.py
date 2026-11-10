# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.28 ConfirmedTextMessage Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import ConfirmedTextMessageRequest
from bacpypes3.primitivedata import CharacterString

from ..context import TestContext
from ..registry import conformance_test
from ._common import expect_simple_ack, register_manual

SERVICE = ["confirmed-text-message"]
_CLASS = "requires the vendor's list of supported message classes"

register_manual("9.28.2", "Text Message With an Unsigned Message Class", _CLASS, services=SERVICE)
register_manual("9.28.3", "Text Message With a CharacterString Message Class", _CLASS, services=SERVICE)
register_manual("9.28.4", "Text Message With Urgent Priority", _CLASS, services=SERVICE)


@conformance_test("9.28.1", "Text Message With No Message Class", services=SERVICE)
async def no_message_class(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT ConfirmedTextMessage-Request, Message Priority = NORMAL")
    ctx.step("2. RECEIVE BACnet-SimpleACK-PDU")
    request = ConfirmedTextMessageRequest(
        textMessageSourceDevice=ctx.app.device_object.objectIdentifier,
        messagePriority="normal",
        message=CharacterString("bacpicker"),
        destination=ctx.iut.address,
    )
    if await expect_simple_ack(ctx, request):
        ctx.step("3. CHECK vendor-specified action")
        ctx.note("no vendor-specified action is declared for ConfirmedTextMessage")
