# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from bacpypes3.basetypes import ChannelValue, ColorCommand, ColorOperation, XYColor
from bacpypes3.local.object import Object as LocalObject
from bacpypes3.object import ColorObject, ColorTemperatureObject
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import ObjectIdentifier, TagList
from test_end_to_end import run_suite
from test_epics import generate

from bacpicker.database import read_database
from bacpicker.epics import format_value, parse_epics
from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.result import Status


class LocalColorObject(LocalObject, ColorObject):
    # bacpypes3 local objects look up Notification_Class after creation, which these lack
    notificationClass = None


class LocalColorTemperatureObject(LocalObject, ColorTemperatureObject):
    notificationClass = None


def round_trip(cls, value, data_hex):
    data = bytes.fromhex(data_hex)
    assert value.encode().encode().pduData == data
    decoded = cls.decode(TagList.decode(PDUData(data)))
    assert decoded.encode().encode().pduData == data
    return decoded


def test_encoding():
    command = round_trip(
        ColorCommand,
        ColorCommand(
            operation=ColorOperation("fade-to-color"),
            targetColor=XYColor(xCoordinate=0.5, yCoordinate=0.25),
            fadeTime=1000,
        ),
        "09 01 1e 44 3f000000 44 3e800000 1f 3a 03e8",
    )
    assert command.targetColorTemperature is None
    assert format_value(command) == "{fade-to-color, {0.5, 0.25}, 1000}"

    value = round_trip(
        ChannelValue, ChannelValue(colorCommand=command), "2e 09 01 1e 44 3f000000 44 3e800000 1f 3a 03e8 2f"
    )
    assert value.colorCommand.fadeTime == 1000
    assert value.xycolor is None


async def test_color_objects_read_and_match_epics(simulated_iut, loopback_config, tmp_path):
    app, _address = simulated_iut
    app.add_object(
        LocalColorObject(
            objectIdentifier="color,1",
            objectName="Color 1",
            presentValue=XYColor(xCoordinate=0.5, yCoordinate=0.25),
            trackingValue=XYColor(xCoordinate=0.5, yCoordinate=0.25),
            colorCommand=ColorCommand(operation=ColorOperation("none")),
            inProgress="idle",
            defaultColor=XYColor(xCoordinate=0.5, yCoordinate=0.25),
            defaultFadeTime=100,
        )
    )
    app.add_object(
        LocalColorTemperatureObject(
            objectIdentifier="color-temperature,1",
            objectName="Color Temperature 1",
            presentValue=2700,
            trackingValue=2700,
            colorCommand=ColorCommand(operation=ColorOperation("none")),
            inProgress="idle",
            defaultColorTemperature=5000,
            defaultFadeTime=100,
            defaultRampRate=100,
            defaultStepIncrement=50,
        )
    )

    tester = build_application(loopback_config)
    try:
        address, i_am = await discover_iut(tester, loopback_config)
        profile = await build_profile(tester, address, i_am)
        database = await read_database(tester, profile)
    finally:
        tester.close()
    color = database.objects[ObjectIdentifier("color,1")]
    assert color.read_error is None
    assert color.properties["object-identifier"].value == ObjectIdentifier("color,1")
    assert format_value(color.properties["present-value"].value) == "{0.5, 0.25}"
    assert str(color.properties["in-progress"].value) == "idle"
    temperature = database.objects[ObjectIdentifier("color-temperature,1")]
    assert temperature.properties["default-color-temperature"].value == 5000

    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    epics = parse_epics(path)
    assert {o.object_identifier for o in epics.objects} >= {"(color, 1)", "(color-temperature, 1)"}
    _profile, report = await run_suite(loopback_config, include=["5(h)", "5(i)"], epics=epics)
    assert {r.clause: r.status for r in report.results} == {"5(h)": Status.PASS, "5(i)": Status.PASS}, [
        (r.clause, [d.message for d in r.defects]) for r in report.results
    ]
