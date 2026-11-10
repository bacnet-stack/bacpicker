# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.29 UnconfirmedTextMessage Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import UnconfirmedTextMessageRequest
from bacpypes3.primitivedata import CharacterString

from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["unconfirmed-text-message"]
_CLASS = "requires the vendor's list of supported message classes"

register_manual("9.29.2", "UnconfirmedTextMessage with an Unsigned Message Class", _CLASS, services=SERVICE)
register_manual("9.29.3", "UnconfirmedTextMessage with a CharacterString Message Class", _CLASS,
    services=SERVICE)


@conformance_test("9.29.1", "UnconfirmedTextMessage With No Message Class", services=SERVICE)
async def no_message_class(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT UnconfirmedTextMessage-Request, Message Priority = NORMAL")
    await ctx.app.request(
        UnconfirmedTextMessageRequest(
            textMessageSourceDevice=ctx.app.device_object.objectIdentifier,
            messagePriority="normal",
            message=CharacterString("bacpicker"),
            destination=ctx.iut.address,
        )
    )
    ctx.step("2. CHECK vendor-specified action")
    ctx.note("no vendor-specified action is declared for UnconfirmedTextMessage")
    await ctx.read(ctx.iut.device_id, "object-name")
