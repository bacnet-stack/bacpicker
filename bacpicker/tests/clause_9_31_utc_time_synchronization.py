# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.31 UTCTimeSynchronization Service Execution Tests."""

from __future__ import annotations

import datetime
import time
from typing import Any, Optional

from bacpypes3.apdu import ErrorRejectAbortNack, UTCTimeSynchronizationRequest
from bacpypes3.basetypes import DateTime
from bacpypes3.primitivedata import Date, Time

from ..context import TestContext
from ..registry import conformance_test

SERVICE = ["utc-time-synchronization"]
# allowed difference between the restored clock and the clock the test started with
RESTORE_TOLERANCE = datetime.timedelta(seconds=90)


def _utc() -> DateTime:
    # 1991-01-02 12:00:00 UTC. Local time is this minus UTC_Offset, plus one hour when DST is in effect.
    return DateTime(date=Date((91, 1, 2, 3)), time=Time((12, 0, 0, 0)))


def _local(local_date: Any, local_time: Any) -> Optional[datetime.datetime]:
    """Local_Date and Local_Time as a datetime, or None when a field is unspecified."""
    year, month, day = tuple(local_date)[:3]
    hour, minute, second, hundredths = tuple(local_time)
    if 255 in (year, month, day, hour, minute, second):
        return None
    hundredths = 0 if hundredths == 255 else hundredths
    try:
        return datetime.datetime(1900 + year, month, day, hour, minute, second, hundredths * 10000)
    except ValueError:
        return None


def _bacnet_utc(local: datetime.datetime, offset: int, dst: bool) -> DateTime:
    # 135-2024 12.11.25: UTC = local standard time + UTC_Offset minutes; DST adds 60 minutes to local
    utc = local + datetime.timedelta(minutes=offset - (60 if dst else 0))
    return DateTime(
        date=Date((utc.year - 1900, utc.month, utc.day, utc.isoweekday())),
        time=Time((utc.hour, utc.minute, utc.second, utc.microsecond // 10000)),
    )


async def _restore_clock(ctx: TestContext, initial: Optional[datetime.datetime], started: float,
    offset: int, dst: bool) -> None:
    """Put the IUT clock back with UTCTimeSynchronization and verify it. Not part of the 135.1 procedure."""
    device = ctx.iut.device_id
    if initial is None:
        ctx.note("cleanup: InitialDate/InitialTime have unspecified fields; the IUT clock was not restored")
        return
    ctx.note("cleanup: restore the date and time read in steps 1 and 2 with UTCTimeSynchronization")
    expected = initial + datetime.timedelta(seconds=time.monotonic() - started)
    await ctx.app.request(
        UTCTimeSynchronizationRequest(time=_bacnet_utc(expected, offset, dst), destination=ctx.iut.address)
    )
    try:
        restored = _local(await ctx.read(device, "local-date"), await ctx.read(device, "local-time"))
    except ErrorRejectAbortNack as err:
        ctx.defect("Could not read Local_Date/Local_Time after restoring the IUT clock", actual=err)
        return
    ctx.check(
        restored is not None and abs(restored - expected) <= RESTORE_TOLERANCE,
        "Could not restore the IUT clock",
        expected=expected.isoformat(timespec="seconds"),
        actual=restored.isoformat(timespec="seconds") if restored else "unspecified",
    )


async def _sync(ctx: TestContext, destination, where: str) -> None:
    device = ctx.iut.device_id
    try:
        initial_date = await ctx.read(device, "local-date")
        initial_time = await ctx.read(device, "local-time")
        started = time.monotonic()
        offset = int(await ctx.read(device, "utc-offset"))
    except ErrorRejectAbortNack as err:
        ctx.skip(f"Local_Date, Local_Time or UTC_Offset cannot be read ({err})")
    try:
        dst = bool(await ctx.read(device, "daylight-savings-status"))
    except ErrorRejectAbortNack:
        dst = False
    initial = _local(initial_date, initial_time)
    ctx.step("1. READ InitialDate = Local_Date")
    ctx.step("2. READ InitialTime = Local_Time")
    ctx.step(f"3. TRANSMIT UTCTimeSynchronization-Request, DESTINATION = {where}, 1991-01-02 12:00:00 UTC")
    try:
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
        new_date = await ctx.read(device, "local-date")
        new_time = await ctx.read(device, "local-time")
    finally:
        await _restore_clock(ctx, initial, started, offset, dst)
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
