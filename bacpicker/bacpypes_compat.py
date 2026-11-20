# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Property identifier names where BACpypes3 differs from 135-2024 Clause 21.

bacpicker names properties from its CSML data, and passes those names back to BACpypes3.
BACpypes3 0.1.0 spells 4194346 "authorization-scopes", while 135-2024 Clause 21 and the
CSML data spell it "authorization-scope", so the standard name is mapped here. The
BACpypes3 attribute name is kept, because object classes look up property types by it.
"""

from __future__ import annotations

from typing import Any

from bacpypes3.primitivedata import PropertyIdentifier, attr_to_asn1

PROPERTY_IDENTIFIERS = {"authorizationScope": 4194346}


def _add_name(cls: Any, attr: str, value: int) -> None:
    # Enumerated subclasses copy the maps when created, and BACpypes3 has already
    # made one per context-tagged field (e.g. ReadAccessResultElement.propertyIdentifier)
    for subclass in cls.__subclasses__():
        _add_name(subclass, attr, value)
    name = attr_to_asn1(attr)
    cls._enum_map[attr] = value
    cls._enum_map[name] = value
    cls._asn1_map[value] = name


for _attr, _value in PROPERTY_IDENTIFIERS.items():
    _add_name(PropertyIdentifier, _attr, _value)
