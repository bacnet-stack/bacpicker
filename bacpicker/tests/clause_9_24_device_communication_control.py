# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.24 DeviceCommunicationControl Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import DeviceCommunicationControlRequest, ErrorPDU

from ..assertions import error_class_code, format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import expect_simple_ack, register_manual

SERVICE = ["device-communication-control"]
_SILENCE = (
    "can disable communication, and the tester does not know whether a password is required or what it is"
)

for _clause, _title in (
    ("9.24.1.1", "Indefinite Time Duration Restored by DeviceCommunicationControl"),
    ("9.24.1.2", "Indefinite Time Duration Restored by ReinitializeDevice"),
    ("9.24.1.3", "Finite Time Duration"),
    ("9.24.1.4", "Finite Time Duration Restored by DeviceCommunicationControl"),
    ("9.24.1.5", "Finite Time Duration Restored by ReinitializeDevice"),
    ("9.24.1.6", "Indefinite Time Duration, Disable-Initiation, Restored by DeviceCommunicationControl"),
    ("9.24.1.7", "Indefinite Time Duration, Disable-Initiation, Restored by ReinitializeDevice"),
    ("9.24.1.8", "Finite Time Duration, Disable Initiation"),
    ("9.24.1.9", "Disable of Service Initiation Restored by Time Duration"),
    ("9.24.1.10", "Disable of Service Initiation Restored by DeviceCommunicationControl"),
    ("9.24.1.12", "Disable of Service Initiation Restored by ReinitializeDevice"),
    ("9.24.2.1", "Invalid Password"),
    ("9.24.2.2", "Missing Password"),
    ("9.24.2.3", "Restore by ReinitializeDevice with Invalid 'Reinitialized State of Device'"),
):
    register_manual(_clause, _title, _SILENCE, services=SERVICE, writes=True)


@conformance_test(
    "9.24.1.11",
    "Ensure that DISABLE Option is not Supported by IUT Claiming PR >= 20",
    services=SERVICE,
    min_protocol_revision=20,
    writes=True,
)
async def disable_not_supported(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    status = await ctx.read(device, "system-status")
    ctx.step("1. TRANSMIT DeviceCommunicationControl-Request, Enable/Disable = DISABLE")
    request = DeviceCommunicationControlRequest(enableDisable="disable", destination=ctx.iut.address)
    ctx.step("2. RECEIVE BACnet-Error-PDU SERVICES / SERVICE_REQUEST_DENIED")
    try:
        await ctx.send(request)
    except ErrorPDU as err:
        pair = tuple(str(part) for part in error_class_code(err))
        if pair == ("security", "password-failure"):
            ctx.skip("IUT rejected the request for lack of a password; none was provided")
        ctx.check(
            pair == ("services", "service-request-denied"),
            "DISABLE was not rejected with SERVICE_REQUEST_DENIED",
            expected="services / service-request-denied",
            actual=pair,
            response=err,
        )
    else:
        ctx.defect("PR >= 20 IUT accepted Enable/Disable = DISABLE", request=request)
        enable = DeviceCommunicationControlRequest(enableDisable="enable", destination=ctx.iut.address)
        if not await expect_simple_ack(ctx, enable):
            ctx.note(f"could not re-enable communication: {format_pdu(enable)}")
    ctx.step("3. VERIFY System_Status")
    ctx.check_equal(await ctx.read(device, "system-status"), status, "System_Status changed")
