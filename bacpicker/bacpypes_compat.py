# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Color and Color Temperature object support for BACpypes3 releases that lack it.

BACpypes3 0.0.110 and earlier stop at the Audit Reporter object type (62), so Color (63)
and Color Temperature (64) objects (135-2020 clauses 12.65 and 12.66) cannot be decoded
or named. This adds them to the BACpypes3 type system in place, and leaves anything the
installed BACpypes3 already defines alone. It must run before any vendor-specific
ObjectType or PropertyIdentifier subclass is created, which is why the package imports it.

ObjectTypesSupported is left alone: its bit names set the encoded length, and the
BACpypes3 local Device object claims Protocol_Revision 22, which predates these types.
bacpicker names Protocol_Object_Types_Supported bits from its own CSML data.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from bacpypes3 import basetypes
from bacpypes3 import object as objects
from bacpypes3.basetypes import ChannelValue, ValueSource
from bacpypes3.constructeddata import Sequence
from bacpypes3.object import LightingOutputObject, Object
from bacpypes3.primitivedata import (
    Boolean,
    Enumerated,
    ObjectIdentifier,
    ObjectType,
    PropertyIdentifier,
    Real,
    Unsigned,
    attr_to_asn1,
)

OBJECT_TYPES = {"color": 63, "colorTemperature": 64}

PROPERTY_IDENTIFIERS = {
    "colorOverride": 4194328,
    "colorReference": 4194329,
    "defaultColor": 4194330,
    "defaultColorTemperature": 4194331,
    "overrideColorReference": 4194332,
    "colorCommand": 4194334,
}


def _add_enumeration(cls: Any, attr: str, value: int) -> None:
    # Enumerated subclasses copy the maps when created, and BACpypes3 has already
    # made one per context-tagged field (e.g. ReadAccessResultElement.propertyIdentifier)
    for subclass in cls.__subclasses__():
        _add_enumeration(subclass, attr, value)
    if attr in cls._enum_map:
        return
    name = attr_to_asn1(attr)
    cls._enum_map[attr] = value
    cls._enum_map[name] = value
    cls._attr_map[value] = attr
    cls._asn1_map[value] = name
    setattr(cls, attr, value)


for _attr, _value in OBJECT_TYPES.items():
    _add_enumeration(ObjectType, _attr, _value)
for _attr, _value in PROPERTY_IDENTIFIERS.items():
    _add_enumeration(PropertyIdentifier, _attr, _value)


def _color_types() -> Tuple[Any, Any, Any, Any, Any]:
    if hasattr(basetypes, "ColorCommand"):
        return (
            basetypes.ColorOperation,
            basetypes.ColorOperationInProgress,
            basetypes.ColorTransition,
            basetypes.XYColor,
            basetypes.ColorCommand,
        )

    class ColorOperation(Enumerated):
        none = 0
        fadeToColor = 1
        fadeToCct = 2
        rampToCct = 3
        stepUpCct = 4
        stepDownCct = 5
        stop = 6

    class ColorOperationInProgress(Enumerated):
        idle = 0
        fadeActive = 1
        rampActive = 2
        notControlled = 3
        other = 4

    class ColorTransition(Enumerated):
        none = 0
        fade = 1
        ramp = 2

    class XYColor(Sequence):
        _order = ("xCoordinate", "yCoordinate")
        xCoordinate = Real()
        yCoordinate = Real()

    class ColorCommand(Sequence):
        _order = (
            "operation",
            "targetColor",
            "targetColorTemperature",
            "fadeTime",
            "rampRate",
            "stepIncrement",
        )
        operation = ColorOperation(_context=0)
        targetColor = XYColor(_context=1, _optional=True)
        targetColorTemperature = Unsigned(_context=2, _optional=True)
        fadeTime = Unsigned(_context=3, _optional=True)
        rampRate = Unsigned(_context=4, _optional=True)
        stepIncrement = Unsigned(_context=5, _optional=True)

    return ColorOperation, ColorOperationInProgress, ColorTransition, XYColor, ColorCommand


ColorOperation, ColorOperationInProgress, ColorTransition, XYColor, ColorCommand = _color_types()


def _add_choice(cls: Any, attr: str, element: Any) -> None:
    if attr in cls._elements:
        return
    cls._elements[attr] = element.__class__
    cls._debug_contents = (*cls._debug_contents, attr)


_add_choice(ChannelValue, "xyColor", XYColor(_context=1))
_add_choice(ChannelValue, "colorCommand", ColorCommand(_context=2))

for _attr, _type in (
    ("colorOverride", Boolean),
    ("colorReference", ObjectIdentifier),
    ("overrideColorReference", ObjectIdentifier),
):
    LightingOutputObject._elements.setdefault(_attr, _type)


def _object_class(name: str, object_type: str, properties: Dict[str, Any], required: Tuple[str, ...]) -> Any:
    """An ASHRAE object class, registered with the standard vendor information."""
    if hasattr(objects, name):
        return getattr(objects, name)
    namespace = {
        "__module__": __name__,
        "__annotations__": properties,
        "_vendor_id": 0,
        "_required": required,
        "objectType": ObjectType(object_type),
    }
    return type(Object)(name, (Object,), namespace)


ColorObject = _object_class(
    "ColorObject",
    "color",
    {
        "presentValue": XYColor,
        "trackingValue": XYColor,
        "colorCommand": ColorCommand,
        "inProgress": ColorOperationInProgress,
        "defaultColor": XYColor,
        "defaultFadeTime": Unsigned,
        "transition": ColorTransition,
        "valueSource": ValueSource,
    },
    ("presentValue", "trackingValue", "colorCommand", "inProgress", "defaultColor", "defaultFadeTime"),
)

ColorTemperatureObject = _object_class(
    "ColorTemperatureObject",
    "colorTemperature",
    {
        "presentValue": Unsigned,
        "trackingValue": Unsigned,
        "colorCommand": ColorCommand,
        "inProgress": ColorOperationInProgress,
        "defaultColorTemperature": Unsigned,
        "defaultFadeTime": Unsigned,
        "defaultRampRate": Unsigned,
        "defaultStepIncrement": Unsigned,
        "transition": ColorTransition,
        "minPresValue": Unsigned,
        "maxPresValue": Unsigned,
        "valueSource": ValueSource,
    },
    (
        "presentValue",
        "trackingValue",
        "colorCommand",
        "inProgress",
        "defaultColorTemperature",
        "defaultFadeTime",
        "defaultRampRate",
        "defaultStepIncrement",
    ),
)
