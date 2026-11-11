# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from bacpypes3.basetypes import ChannelValue, ObjectTypesSupported, ReadAccessResultElement
from bacpypes3.local.object import Object as LocalObject
from bacpypes3.object import DeviceObject, LightingOutputObject, NetworkPortObject
from bacpypes3.pdu import PDUData
from bacpypes3.primitivedata import (
    Boolean,
    ObjectIdentifier,
    ObjectType,
    PropertyIdentifier,
    Real,
    TagList,
    Unsigned,
)
from bacpypes3.vendor import get_vendor_info
from test_end_to_end import run_suite
from test_epics import generate

from bacpicker.bacpypes_compat import (
    ColorCommand,
    ColorObject,
    ColorOperation,
    ColorTemperatureObject,
    XYColor,
)
from bacpicker.database import read_database
from bacpicker.epics import format_value, parse_epics
from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.result import Status


class LocalColorObject(LocalObject, ColorObject):
    pass


class LocalColorTemperatureObject(LocalObject, ColorTemperatureObject):
    pass


def round_trip(cls, value, data_hex):
    data = bytes.fromhex(data_hex)
    assert value.encode().encode().pduData == data
    decoded = cls.decode(TagList.decode(PDUData(data)))
    assert decoded.encode().encode().pduData == data
    return decoded


def test_names():
    assert ObjectType("color") == 63
    assert str(ObjectType(64)) == "color-temperature"
    assert PropertyIdentifier("color-command") == 4194334
    assert str(PropertyIdentifier(4194331)) == "default-color-temperature"
    assert PropertyIdentifier("max-proxied-i-ams-per-second") == 4194349
    assert str(PropertyIdentifier(4194349)) == "max-proxied-i-ams-per-second"
    assert str(PropertyIdentifier(4194341)) == "default-on-value"
    assert str(PropertyIdentifier(4194339)) == "device-address-proxy-table"
    # bit names set the encoded length, which must stay at Protocol_Revision 22's 63 bits
    assert ObjectTypesSupported._bitstring_length == 63
    assert str(ColorOperation(4)) == "step-up-cct"
    # context-tagged fields are Enumerated subclasses created before the names were added
    property_class = ReadAccessResultElement._elements["propertyIdentifier"]
    assert property_class is not PropertyIdentifier
    assert str(property_class(4194328)) == "color-override"
    object_type_class = ObjectIdentifier("color,1").object_type_class
    assert str(object_type_class(63)) == "color"


def test_object_classes():
    vendor_info = get_vendor_info(0)
    assert vendor_info.get_object_class(63) is ColorObject
    assert vendor_info.get_object_class(64) is ColorTemperatureObject
    assert ColorObject.get_property_type("present-value") is XYColor
    assert ColorTemperatureObject.get_property_type("color-command") is ColorCommand
    assert LightingOutputObject.get_property_type("color-reference") is not None
    assert LightingOutputObject.get_property_type("last-on-value") is Real
    assert LightingOutputObject.get_property_type("default-on-value") is Real
    assert NetworkPortObject.get_property_type("device-address-proxy-enable") is Boolean
    assert NetworkPortObject.get_property_type("device-address-proxy-timeout") is Unsigned
    assert DeviceObject.get_property_type("max-proxied-i-ams-per-second") is Unsigned


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
    assert getattr(value, "xyColor", None) is None


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
