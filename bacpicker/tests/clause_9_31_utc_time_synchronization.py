# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.31 UTCTimeSynchronization Service Execution Tests."""

from __future__ import annotations

from bacpypes3.apdu import ErrorRejectAbortNack, TimeSynchronizationRequest, UTCTimeSynchronizationRequest
from bacpypes3.basetypes import DateTime
from bacpypes3.primitivedata import Date, Time

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["utc-time-synchronization"]


def _utc() -> DateTime:
    # 1991-01-02 12:00:00 UTC. Local time is this minus UTC_Offset, plus one hour when DST is in effect.
    return DateTime(date=Date((91, 1, 2, 3)), time=Time((12, 0, 0, 0)))


async def _sync(ctx: TestContext, destination, where: str) -> None:
    device = ctx.iut.device_id
    try:
        initial_date = await ctx.read(device, "local-date")
        initial_time = await ctx.read(device, "local-time")
        offset = int(await ctx.read(device, "utc-offset"))
    except ErrorRejectAbortNack as err:
        ctx.skip(f"Local_Date, Local_Time or UTC_Offset cannot be read ({err})")
    try:
        dst = bool(await ctx.read(device, "daylight-savings-status"))
    except ErrorRejectAbortNack:
        dst = False
    ctx.step("1. READ InitialDate = Local_Date")
    ctx.step("2. READ InitialTime = Local_Time")
    ctx.step(f"3. TRANSMIT UTCTimeSynchronization-Request, DESTINATION = {where}, 1991-01-02 12:00:00 UTC")
    await ctx.app.request(UTCTimeSynchronizationRequest(time=_utc(), destination=destination))
    # 135-2024 12.11.25: local standard time = UTC - UTC_Offset minutes. DST adds 60 minutes.
    minutes = 12 * 60 - offset + (60 if dst else 0)
    day = 2
    if minutes < 0:
        day -= 1
        minutes += 24 * 60
    elif minutes >= 24 * 60:
        day += 1
        minutes -= 24 * 60
    expect_date = (91, 1, day)
    expect_h, expect_m = divmod(minutes, 60)
    ctx.step("4. VERIFY Local_Date from UTC_Offset and Daylight_Savings_Status")
    ctx.step("5. VERIFY Local_Time ~= that local time")
    try:
        new_date = await ctx.read(device, "local-date")
        new_time = await ctx.read(device, "local-time")
    finally:
        ctx.note("cleanup: restore the date and time read in steps 1 and 2")
        await ctx.app.request(
            TimeSynchronizationRequest(
                time=DateTime(date=initial_date, time=initial_time), destination=ctx.iut.address
            )
        )
    ctx.check(tuple(new_date)[:3] == expect_date, "Local_Date was not converted from UTC",
        expected=expect_date, actual=new_date)
    ctx.check(
        int(new_time[0]) == expect_h and abs(int(new_time[1]) - expect_m) <= 1,
        "Local_Time was not converted from UTC",
        expected=f"{expect_h:02d}:{expect_m:02d}",
        actual=new_time,
    )


@conformance_test("9.31.1.1", "Local Broadcast", services=SERVICE, writes=True)
async def local_broadcast(ctx: TestContext) -> None:
    await _sync(ctx, ctx.destination("local"), "LOCAL BROADCAST")


@conformance_test("9.31.1.2", "Directed to the IUT", services=SERVICE, writes=True)
async def directed(ctx: TestContext) -> None:
    await _sync(ctx, ctx.iut.address, "the IUT")
