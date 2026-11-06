# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Reference data from the BACnet standard: object/property definitions (ASHRAE CSML XML),
Annex K BIBBs, and Protocol_Revision history."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

DATA = Path(__file__).resolve().parent / "data"
CSML_NS = "{http://bacnet.org/csml/1.2}"


# ---- object types and properties (bacnet-object-types.xml) -------------------


@dataclass(frozen=True)
class PropertySpec:
    name: str
    identifier: int
    datatype: str
    optional: bool
    writable: Optional[bool]  # True = conformance code W, False = read-only, None = not specified
    commandable: bool
    required_with: Tuple[str, ...]
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    minimum_length: Optional[int] = None
    minimum_size: Optional[int] = None
    maximum_size: Optional[int] = None


@dataclass(frozen=True)
class ObjectSpec:
    object_type: str
    properties: Tuple[PropertySpec, ...]

    def get(self, name: str) -> Optional[PropertySpec]:
        return next((p for p in self.properties if p.name == name), None)

    @property
    def names(self) -> Set[str]:
        return {p.name for p in self.properties}

    def required(self, revision: Optional[int] = None) -> Set[str]:
        """Properties with conformance code R or W, adjusted for the Protocol_Revision."""
        names = {p.name for p in self.properties if not p.optional}
        for prop, since in revisions()["properties_required_since"].items():
            if revision is not None and revision < since["revision"]:
                names.discard(prop)
        return names

    def optional(self) -> Set[str]:
        return {p.name for p in self.properties if p.optional}


def _num(value: Optional[str]) -> Optional[float]:
    return None if value is None else float(value)


def _int(value: Optional[str]) -> Optional[int]:
    return None if value is None else int(value)


@lru_cache(maxsize=None)
def object_specs() -> Dict[str, ObjectSpec]:
    """Standard object types keyed by name, e.g. 'analog-input'."""
    root = ET.parse(DATA / "bacnet-object-types.xml").getroot()
    specs = {}
    for obj in root.iter(f"{CSML_NS}Object"):
        props = []
        object_type = None
        for p in obj:
            attr = p.attrib
            if attr["name"] == "object-type":
                object_type = attr.get("value")
            props.append(
                PropertySpec(
                    name=attr["name"],
                    identifier=int(attr["propertyIdentifier"]),
                    datatype=p.tag.replace(CSML_NS, ""),
                    optional=attr.get("optional") == "true",
                    writable={"true": True, "false": False}.get(attr.get("writable", "")),
                    commandable=attr.get("commandable") == "true",
                    required_with=tuple(filter(None, attr.get("requiredWith", "").split(","))),
                    minimum=_num(attr.get("minimum")),
                    maximum=_num(attr.get("maximum")),
                    minimum_length=_int(attr.get("minimumLength")),
                    minimum_size=_int(attr.get("minimumSize")),
                    maximum_size=_int(attr.get("maximumSize")),
                )
            )
        if object_type:
            specs[object_type] = ObjectSpec(object_type, tuple(props))
    return specs


def object_spec(object_type: str) -> Optional[ObjectSpec]:
    return object_specs().get(canonical_object_type(object_type) or object_type)


# ---- data types (bacnet-data-types.xml) ---------------------------------------


@lru_cache(maxsize=None)
def _data_types() -> ET.Element:
    return ET.parse(DATA / "bacnet-data-types.xml").getroot()


def _definition(name: str) -> ET.Element:
    return next(e for e in _data_types().iter() if e.get("name") == name)


@lru_cache(maxsize=None)
def bitstring(name: str) -> Tuple[Dict[str, int], int]:
    """Named bits and defined length of a CSML BitString, e.g. '0-BACnetServicesSupported'."""
    element = _definition(name)
    bits = {b.attrib["name"]: int(b.attrib["bit"]) for b in element.iter(f"{CSML_NS}Bit")}
    return bits, int(element.attrib["length"])


def service_bits() -> Dict[str, int]:
    return bitstring("0-BACnetServicesSupported")[0]


def object_type_bits() -> Dict[str, int]:
    return bitstring("0-BACnetObjectTypesSupported")[0]


@lru_cache(maxsize=None)
def property_identifiers() -> Dict[int, str]:
    element = _definition("0-BACnetPropertyIdentifier")
    return {int(v.attrib["value"]): v.attrib["name"] for v in element.iter(f"{CSML_NS}Unsigned")}


def canonical_object_type(name: str) -> Optional[str]:
    """Map any spelling ('date-pattern-value', 'Date Pattern Value') to the CSML name."""
    return {normalize(n): n for n in object_type_bits()}.get(normalize(name))


def canonical_service(name: str) -> Optional[str]:
    return {normalize(n): n for n in service_bits()}.get(normalize(name))


# ---- BIBBs (Annex K) -----------------------------------------------------------

# Object types a B-side BIBB requires, curated from the Annex K prose of 135-2024.
# Each entry is a list of alternatives; at least one type of each tuple is required.
BIBB_OBJECT_TYPES: Dict[str, List[Tuple[str, ...]]] = {
    "DS-WG-I-B": [("channel",)],
    "DS-WG-E-B": [("channel",)],
    "DS-ACAD-B": [("access-door",)],
    "DS-ACCDI-B": [("credential-data-input",)],
    "DS-LO-B": [("lighting-output",)],
    "DS-BLO-B": [("binary-lighting-output",)],
    "AE-N-E-B": [("event-enrollment",)],
    "AE-LS-B": [("life-safety-point", "life-safety-zone")],
    "AE-EL-I-B": [("event-log",)],
    "AE-EL-E-B": [("event-log",)],
    "AE-NF-B": [("notification-forwarder",)],
    "AE-NF-I-B": [("notification-forwarder",)],
    "AE-CRL-B": [("notification-class", "notification-forwarder")],
    "AE-AC-B": [("access-point",)],
    "SCHED-I-B": [("calendar",), ("schedule",)],
    "SCHED-R-B": [("schedule",)],
    "SCHED-WS-I-B": [("schedule",)],
    "SCHED-TMR-I-B": [("timer",)],
    "T-VMT-I-B": [("trend-log",)],
    "T-ATR-B": [("trend-log",)],
    "T-VMMV-I-B": [("trend-log-multiple",)],
    "T-AMVR-B": [("trend-log-multiple",)],
    "AR-R-B": [("audit-reporter",)],
    "DM-BR-B": [("file",)],
}


@dataclass(frozen=True)
class Bibb:
    acronym: str
    clause: str
    title: str
    initiate: Tuple[str, ...]  # service bit names that must be initiated
    execute: Tuple[str, ...]  # service bit names that must be executed
    object_types: Tuple[Tuple[str, ...], ...]


@lru_cache(maxsize=None)
def bibbs() -> Dict[str, Bibb]:
    raw = json.loads((DATA / "bibbs.json").read_text(encoding="utf-8"))
    return {
        acronym: Bibb(
            acronym=acronym,
            clause=entry["clause"],
            title=entry["title"],
            # footnoted ("conditional") requirements depend on usage and are not enforced
            initiate=tuple(s for s, m in entry["services"].items() if m["initiate"] == "x"),
            execute=tuple(s for s, m in entry["services"].items() if m["execute"] == "x"),
            object_types=tuple(BIBB_OBJECT_TYPES.get(acronym, ())),
        )
        for acronym, entry in raw.items()
    }


# ---- Protocol_Revision history -------------------------------------------------


@lru_cache(maxsize=None)
def revisions() -> dict:
    return json.loads((DATA / "revisions.json").read_text(encoding="utf-8"))


def defined_bits(kind: str, revision: int) -> Tuple[int, bool]:
    """Bits of BACnetObjectTypesSupported ("object_types") or BACnetServicesSupported ("services")
    defined at a Protocol_Revision, and whether every entry used was verified."""
    data = revisions()
    names = object_type_bits() if kind == "object_types" else service_bits()
    count = data["baseline"][f"{kind}_bits"]
    verified = True
    for name, entry in data[kind].items():
        name = (canonical_object_type if kind == "object_types" else canonical_service)(name)
        if entry["revision"] <= revision and name in names:
            bit = names[name] + 1
            if bit > count:
                count = bit
                verified = entry["verified"]
    return count, verified


def introduced_in(kind: str, name: str) -> Optional[dict]:
    key = normalize(name)
    return next((e for n, e in revisions()[kind].items() if normalize(n) == key), None)


# ---- EPICS names ---------------------------------------------------------------

_HYPHENATED_SERVICES = {"who-is", "i-am", "who-has", "i-have", "vt-open", "vt-close", "vt-data", "you-are"}
_UPPER = {"cov": "COV", "utc": "UTC", "vt": "VT"}
_OBJECT_WORDS = {
    "characterstring": "CharacterString",
    "bitstring": "BitString",
    "octetstring": "OctetString",
    "datetime": "DateTime",
    "multi": "Multi",
}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def service_epics_name(bit_name: str) -> str:
    """'read-property' -> 'ReadProperty', 'who-is' -> 'Who-Is' (135.1 4.5.3)."""
    if normalize(bit_name) == "whoami":
        return "Who-Am-I"
    parts = bit_name.split("-")
    words = [_UPPER.get(p, p.capitalize()) for p in parts]
    return "-".join(words) if bit_name in _HYPHENATED_SERVICES else "".join(words)


def object_type_epics_name(type_name: str) -> str:
    """'analog-input' -> 'Analog Input' (135.1 4.5.4)."""
    return " ".join(_OBJECT_WORDS.get(p, p.capitalize()) for p in type_name.split("-")).replace(
        "Multi State", "Multi-state"
    )


def service_from_epics(text: str) -> Optional[str]:
    return canonical_service(text)


def object_type_from_epics(text: str) -> Optional[str]:
    return canonical_object_type(text)
