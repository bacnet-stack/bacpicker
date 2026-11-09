# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.25 ConfirmedPrivateTransfer Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import (
    AbortPDU,
    ConfirmedPrivateTransferRequest,
    ErrorPDU,
    ErrorRejectAbortNack,
    RejectPDU,
)

from ..assertions import format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import register_manual

SERVICE = ["confirmed-private-transfer"]

register_manual(
    "9.25.1.1",
    "Correctly Executes a Supported ConfirmedPrivateTransfer Service",
    "requires the vendor identifier, service number and parameters of a service the IUT implements",
    services=SERVICE,
)


@conformance_test(
    "9.25.2.1",
    "Correctly Executes a Non-Supported ConfirmedPrivateTransfer Service",
    services=SERVICE,
)
async def unsupported_private_transfer(ctx: TestContext) -> None:
    ctx.step("1. TRANSMIT ConfirmedPrivateTransfer-Request, Vendor ID = 0, Service Number = 0")
    ctx.step("2. RECEIVE ConfirmedPrivateTransfer-Error, or Reject, or Abort")
    request = ConfirmedPrivateTransferRequest(
        vendorID=0, serviceNumber=0, destination=ctx.iut.address
    )
    try:
        ack = await ctx.send(request)
    except (ErrorPDU, RejectPDU, AbortPDU):
        ctx.step("3. CHECK vendor-defined results")
        ctx.note("no vendor-defined result is declared for this vendor/service pair")
        return
    except ErrorRejectAbortNack as err:
        ctx.defect("Expected an Error, Reject or Abort", actual=format_pdu(err), request=request,
            response=err)
        return
    ctx.defect(
        "Unsupported ConfirmedPrivateTransfer was acknowledged",
        actual=format_pdu(ack),
        request=request,
        response=ack,
    )
