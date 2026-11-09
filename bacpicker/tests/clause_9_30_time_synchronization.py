# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.30 TimeSynchronization Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import ErrorRejectAbortNack, TimeSynchronizationRequest
from bacpypes3.basetypes import DateTime
from bacpypes3.primitivedata import Date, Time

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["time-synchronization"]


def _request(ctx: TestContext, destination) -> TimeSynchronizationRequest:
    # 2 January 1991 01:02:03.0, chosen to differ from a live clock.
    return TimeSynchronizationRequest(
        time=DateTime(date=Date((91, 1, 2, 3)), time=Time((1, 2, 3, 0))),
        destination=destination,
    )


async def _sync(ctx: TestContext, destination, where: str) -> None:
    device = ctx.iut.device_id
    try:
        initial_date = await ctx.read(device, "local-date")
        initial_time = await ctx.read(device, "local-time")
    except ErrorRejectAbortNack as err:
        ctx.skip(f"Local_Date or Local_Time cannot be read ({err})")
    ctx.step("1. READ InitialDate = Local_Date")
    ctx.step("2. READ InitialTime = Local_Time")
    ctx.step(f"3. TRANSMIT TimeSynchronization-Request, DESTINATION = {where}, date = 1991-01-02,"
        "time = 01:02:03.00")
    await ctx.app.request(_request(ctx, destination))
    ctx.step("4. VERIFY Local_Date = 1991-01-02")
    ctx.step("5. VERIFY Local_Time ~= 01:02:03.00")
    try:
        new_date = await ctx.read(device, "local-date")
        new_time = await ctx.read(device, "local-time")
    finally:
        ctx.note("cleanup: restore the date and time read in steps 1 and 2")
        await ctx.app.request(
            TimeSynchronizationRequest(
                time=DateTime(date=initial_date, time=initial_time),
                destination=destination,
            )
        )
    ctx.check(tuple(new_date)[:3] == (91, 1, 2), "Local_Date was not set", expected="1991-01-02",
        actual=new_date)
    hour, minute, second = (int(new_time[0]), int(new_time[1]), int(new_time[2]))
    ctx.check(
        (hour, minute) == (1, 2) and abs(second - 3) <= 5,
        "Local_Time is not approximately 01:02:03",
        expected="01:02:03",
        actual=new_time,
    )


@conformance_test("9.30.1.1", "TimeSynchronization Local Broadcast", services=SERVICE, writes=True)
async def local_broadcast(ctx: TestContext) -> None:
    await _sync(ctx, ctx.destination("local"), "LOCAL BROADCAST")


@conformance_test("9.30.1.2", "Directed to the IUT", services=SERVICE, writes=True)
async def directed(ctx: TestContext) -> None:
    await _sync(ctx, ctx.iut.address, "the IUT")
