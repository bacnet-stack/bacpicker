# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""EPICS (135.1 clause 4) writer and parser.

The writer turns the test database read from the IUT into an EPICS. Annex K BIBBs the
device appears to support are listed uncommented, with the reason each was included.
DS-RP-B is always listed uncommented, because every device must support it; when that
support cannot be inferred, the reason says so. A-side BIBBs that the device properties
make possible stay commented, with a possible-inclusion note. The remaining Annex K
BIBBs are listed commented out. Initiate roles that Annex K requires of a suggested
BIBB are inferred, because Protocol_Services_Supported has no Initiate bits. The user
reviews those claims (and can edit Initiate support, Fail Times and restrictions), then
passes the file with --epics.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from bacpypes3.constructeddata import Array, Choice, Sequence
from bacpypes3.primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Enumerated,
    Null,
    ObjectIdentifier,
    OctetString,
    Time,
)

from . import STANDARD_EDITION, __version__
from .standard import (
    bibbs,
    canonical_object_type,
    canonical_service,
    object_spec,
    object_type_epics_name,
    service_epics_name,
)

SIGNATURE = "BACnet Protocol Implementation Conformance Statement"
END = "End of BACnet Protocol Implementation Conformance Statement"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


# ---- value formatting (135.1 4.4) ----------------------------------------------


def _quote(text: str) -> str:
    return f"'{text}'" if '"' in text else f'"{text}"'


def format_value(value: Any) -> str:
    if value is None:
        return "?"
    if isinstance(value, Null):
        return "NULL"
    if isinstance(value, (Boolean, bool)):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Enumerated):
        return str(value)
    if isinstance(value, BitString):
        return "{" + ",".join("T" if b else "F" for b in value) + "}"
    if isinstance(value, ObjectIdentifier):
        object_type, instance = value
        if int(object_type) >= 128:
            return f"(proprietary {int(object_type)}, {instance})"
        return f"({object_type}, {instance})"
    if isinstance(value, (CharacterString, str)):
        return _quote(str(value))
    if isinstance(value, (OctetString, bytes, bytearray)):
        return f"X'{bytes(value).hex().upper()}'"
    if isinstance(value, Date):
        year, month, day, dow = value
        parts = [
            "*" if day == 255 else str(day),
            "*" if month in (255, 13, 14) else MONTHS[month - 1],
            "*" if year == 255 else str(year + 1900),
        ]
        prefix = "" if dow == 255 else f"{DAYS[dow - 1]}, "
        return f"({prefix}{'-'.join(parts)})"
    if isinstance(value, Time):
        hour, minute, second, hundredth = value
        f = lambda v, w: "*" if v == 255 else str(v).zfill(w)  # noqa: E731
        return f"{f(hour, 1)}:{f(minute, 2)}:{f(second, 2)}.{f(hundredth, 2)}"
    if isinstance(value, float):
        text = repr(float(value))
        return text if "." in text or "e" in text else text + ".0"
    if isinstance(value, int):
        return str(int(value))
    if isinstance(value, Array):
        return "{" + ", ".join(format_value(v) for v in value) + "}"
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(format_value(v) for v in value) + ")"
    if isinstance(value, Choice):
        for attr in getattr(value, "_elements", {}):
            chosen = getattr(value, attr, None)
            if chosen is not None:
                return format_value(chosen)
        return "?"
    if isinstance(value, Sequence):
        items = [getattr(value, attr, None) for attr in getattr(value, "_order", ())]
        return "{" + ", ".join(format_value(v) for v in items if v is not None) + "}"
    return "?"


# ---- writer --------------------------------------------------------------------


# Listed even when support cannot be inferred, so clause 5(e) still reports a missing
# ReadProperty bit instead of skipping for lack of any declared BIBB.
MANDATORY_BIBBS = {"DS-RP-B": "required of all BACnet devices"}

# These execute lists are ordinary services, so the BIBB is suggested only when the
# proxy properties Annex K requires are actually present.
_PROXY_PROPERTIES = {
    "DM-SP-B": (
        "subordinate-proxy-enable",
        "manual-subordinate-address-binding",
        "auto-subordinate-discovery",
        "subordinate-address-binding",
    ),
    "DM-DAP-B": ("device-address-proxy-table",),
}
_TIME_SYNC_BIBBS = ("DM-ATS-A", "DM-TS-A", "DM-UTC-A")
_TIME_SYNC_NOTE = (
    "possible inclusion: time-synchronization-interval and time-synchronization-recipients"
)
# I-Am and I-Have execute bits are dropped when those services are inferred as Initiate.
# Other services keep an execute bit that is set alongside an inferred Initiate role.
_INITIATE_ONLY_WHEN_INFERRED = {"i-am", "i-have"}


def _read_properties(record: Any) -> Set[str]:
    if record is None:
        return set()
    return {name for name, prop in record.properties.items() if prop.present and prop.error is None}


def _present_properties(database: Any) -> Set[str]:
    names: Set[str] = set()
    for record in database.objects.values():
        names |= _read_properties(record)
    return names


def _device_properties(profile: Any, database: Any) -> Set[str]:
    return _read_properties(database.objects.get(profile.device_id))


def _suggested_bibbs(profile: Any, database: Any) -> Dict[str, str]:
    """B-side BIBBs whose execute services and object types the IUT appears to support."""
    present = {r.object_type for r in database.objects.values()}
    properties = _present_properties(database)
    suggestions = {}
    for acronym, bibb in bibbs().items():
        if not acronym.endswith("-B") or not (bibb.execute or bibb.object_types):
            continue
        if not all(profile.supports_service(s) for s in bibb.execute):
            continue
        if not all(any(t in present for t in alt) for alt in bibb.object_types):
            continue
        required = _PROXY_PROPERTIES.get(acronym)
        if required and not all(name in properties for name in required):
            continue
        if bibb.execute:
            suggestions[acronym] = "executes " + ", ".join(service_epics_name(s) for s in bibb.execute)
        else:
            suggestions[acronym] = "required object types present"
    # Where an external (-E-B) and internal (-I-B) variant both match, assume internal only.
    for acronym in [a for a in suggestions if a.endswith("-E-B")]:
        if acronym[:-4] + "-I-B" in suggestions:
            del suggestions[acronym]
    return suggestions


def bibb_listing(profile: Any, database: Any) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Uncommented BIBB hints, and commented A-side BIBBs that are a possible inclusion.

    Property-driven B-side BIBBs have no execute bit Protocol_Services_Supported can show.
    The A-side time-sync BIBBs stay commented so clause 5 does not treat them as claimed.
    """
    suggestions = _suggested_bibbs(profile, database)
    possible: Dict[str, str] = {}
    device_props = _device_properties(profile, database)
    if {"time-synchronization-interval", "time-synchronization-recipients"} <= device_props:
        for acronym in _TIME_SYNC_BIBBS:
            possible[acronym] = _TIME_SYNC_NOTE
    if "restart-notification-recipients" in device_props:
        suggestions["DM-R-B"] = "initiates " + service_epics_name("unconfirmed-cov-notification")
    if any(record.object_type == "notification-class" for record in database.objects.values()):
        suggestions["AE-N-I-B"] = "initiates " + service_epics_name("unconfirmed-event-notification")
    return suggestions, possible


def inferred_roles(profile: Any, database: Any) -> Dict[Tuple[str, str], str]:
    """(service, role) pairs implied by Annex K, with the evidence for each.

    Role is "initiate" or "execute". Suggested BIBBs contribute their required Initiate
    services. I-Am is always initiated. Executing You-Are also implies Who-Am-I Initiate
    and Who-Is Execute. Conditional Annex K cells are not included.
    """
    suggestions, possible = bibb_listing(profile, database)
    known = bibbs()
    reasons: Dict[Tuple[str, str], List[str]] = {}

    def add(service: str, role: str, reason: str) -> None:
        reasons.setdefault((service, role), [])
        if reason not in reasons[(service, role)]:
            reasons[(service, role)].append(reason)

    add("i-am", "initiate", "every BACnet device initiates I-Am")
    for acronym, hint in {**suggestions, **possible}.items():
        bibb = known.get(acronym)
        if bibb is None:
            continue
        for service in bibb.initiate:
            add(service, "initiate", f"{acronym} ({hint})")
    if profile.supports_service("you-are"):
        add("who-am-i", "initiate", "executes You-Are")
        add("who-is", "execute", "executes You-Are")
    return {key: "; ".join(values) for key, values in reasons.items()}


def write_epics(path: Path, profile: Any, database: Any, config: Any) -> None:
    device = database.objects.get(profile.device_id)
    device_props = device.properties if device else {}

    def device_text(name: str) -> str:
        record = device_props.get(name)
        return str(record.value) if record is not None and record.value is not None else ""

    lines: List[str] = [
        "PICS 0",
        SIGNATURE,
        "",
        f"-- Generated by bacpicker {__version__} ({STANDARD_EDITION}) by reading",
        f"-- {profile.device_id} at {profile.address}.",
        "-- Review the BIBBs below. Ones the device appears to support are uncommented,",
        "-- with the reason they were included. Comment out any the product does not",
        "-- claim, uncomment any that were missed, add Initiate support, then rerun",
        "-- with --epics <this file>.",
        "",
        f"Vendor Name: {_quote(profile.vendor_name or '')}",
        f"Product Name: {_quote(profile.model_name or '')}",
        f"Product Model Number: {_quote(profile.model_name or '')}",
        f"Product Description: {_quote(device_text('description'))}",
        "",
        "BIBBs Supported:",
        "{",
        "-- Uncommented BIBBs are ones the device appears to support, based on",
        "-- Protocol_Services_Supported, the objects present, and Device properties.",
        "-- DS-RP-B is always listed; it is required of all BACnet devices.",
        "-- A commented BIBB with 'possible inclusion' is an A-side claim the",
        "-- device properties support. Remove the leading '--' to claim it.",
    ]
    suggestions, possible = bibb_listing(profile, database)
    for acronym in sorted(bibbs()):
        hint = suggestions.get(acronym) or MANDATORY_BIBBS.get(acronym)
        if hint:
            lines.append(f"{acronym:<19}-- {hint}")
        elif acronym in possible:
            lines.append(f"-- {acronym:<16}-- {possible[acronym]}")
        else:
            lines.append(f"-- {acronym}")
    roles = inferred_roles(profile, database)
    initiated = {service for service, role in roles if role == "initiate"}
    executed = (set(profile.services_supported) - (initiated & _INITIATE_ONLY_WHEN_INFERRED)) | {
        service for service, role in roles if role == "execute"
    }
    lines += [
        "}",
        "",
        "BACnet Standard Application Services Supported:",
        "{",
        "-- Execute is from Protocol_Services_Supported. Initiate is inferred from",
        "-- suggested BIBBs and from Device properties: time-synchronization-interval",
        "-- with time-synchronization-recipients, restart-notification-recipients,",
        "-- and a Notification Class object. I-Am is always inferred. Who-Am-I",
        "-- Initiate and Who-Is Execute follow You-Are.",
    ]
    for service in sorted(initiated | executed, key=service_epics_name):
        words = (["Initiate"] if service in initiated else []) + (["Execute"] if service in executed else [])
        lines.append(f"{service_epics_name(service)} {' '.join(words)}")
    lines += ["}", "", "Standard Object Types Supported:", "{"]
    types = set(profile.object_types_supported) | {r.object_type for r in database.objects.values()}
    for object_type in sorted(t for t in types if canonical_object_type(t)):
        lines.append(object_type_epics_name(object_type))
    lines += [
        "}",
        "",
        "Data Link Layer Option:",
        "{",
        "BACnet/IP, 'DIX' Ethernet",
        "}",
        "",
        "Character Sets Supported:",
        "{",
        "ANSI X3.4",
        "}",
        "",
        "Special Functionality:",
        "{",
        f"Maximum APDU size in octets: {profile.max_apdu_length_accepted}",
    ]
    if profile.segmentation_supported in ("segmented-both", "segmented-receive"):
        lines.append("Segmented Requests Supported, window size: 1 -- edit window size")
    if profile.segmentation_supported in ("segmented-both", "segmented-transmit"):
        lines.append("Segmented Responses Supported, window size: 1 -- edit window size")
    lines += [
        "}",
        "",
        "Default Property Value Restrictions:",
        "{",
        "}",
        "",
        "Fail Times:",
        "{",
        f"Unconfirmed Response Fail Time: {config.unconfirmed_response_fail_time}",
        f"Internal Processing Fail Time: {config.internal_processing_fail_time}",
        "}",
        "",
        "List of Objects in Test Device:",
        "{",
    ]
    for record in database.objects.values():
        spec = object_spec(record.object_type)
        lines.append("  {")
        names = ["object-identifier", "object-name", "object-type"] + [
            n for n in record.properties if n not in ("object-identifier", "object-name", "object-type")
        ]
        for name in names:
            prop = record.properties.get(name)
            if prop is None or not prop.present:
                continue
            if prop.error:
                lines.append(f"    {name}: ? -- {prop.error}")
                continue
            pspec = spec.get(name) if spec else None
            writable = prop.writable if prop.writable is not None else bool(pspec and pspec.writable)
            mark = " W" if writable else ""
            lines.append(f"    {name}: {format_value(prop.value)}{mark}")
        lines.append("  }")
    lines += ["}", "", END, ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("\r\n".join(lines).encode("utf-8"))


# ---- parser --------------------------------------------------------------------


@dataclass
class EpicsProperty:
    name: str
    value: str
    flag: Optional[str] = None  # "W", "C" or None
    restrictions: Dict[str, str] = field(default_factory=dict)


@dataclass
class EpicsObject:
    object_identifier: str
    properties: Dict[str, EpicsProperty] = field(default_factory=dict)


@dataclass
class Epics:
    general: Dict[str, str] = field(default_factory=dict)
    bibbs: List[str] = field(default_factory=list)
    services: Dict[str, Set[str]] = field(default_factory=dict)  # bit name -> {"initiate","execute"}
    object_types: Dict[str, Set[str]] = field(default_factory=dict)  # name -> {"createable","deleteable"}
    fail_times: Dict[str, float] = field(default_factory=dict)
    default_restrictions: Dict[str, Dict[str, str]] = field(default_factory=dict)
    objects: List[EpicsObject] = field(default_factory=list)
    unknown: List[str] = field(default_factory=list)  # entries that did not match the standard


def _strip_comments(text: str) -> str:
    out, quote, i = [], None, 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == quote or ch == "\n":
                quote = None
        elif ch in "\"'`":
            quote = "'" if ch == "`" else ch
            out.append(ch)
        elif text.startswith("--", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _block(text: str, start: int) -> Tuple[str, int]:
    """The contents of the brace block opening at text[start] and the index after it."""
    depth, quote = 0, None
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if ch == quote or ch == "\n":
                quote = None
        elif ch in "\"'`":
            quote = "'" if ch == "`" else ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
    raise ValueError("unbalanced braces in EPICS")


SECTION = re.compile(r"^[ \t]*([A-Za-z][A-Za-z0-9 /_\-]*?)\s*:\s*", re.M)
GENERAL = ("vendor name", "product name", "product model number", "product description")


def _sections(text: str) -> List[Tuple[str, Any]]:
    sections, pos = [], 0
    while True:
        m = SECTION.search(text, pos)
        if not m:
            return sections
        name, pos = m.group(1).strip(), m.end()
        if pos < len(text) and text[pos] == "{":
            body, pos = _block(text, pos)
            sections.append((name, body))
        else:
            end = text.find("\n", pos)
            end = len(text) if end < 0 else end
            sections.append((name, text[pos:end].strip()))
            pos = end


def _lines(body: str) -> List[str]:
    return [line.strip() for line in body.splitlines() if line.strip()]


def _unquote(text: str) -> str:
    text = text.strip()
    return text[1:-1] if len(text) >= 2 and text[0] in "\"'`" else text


def _parse_property(name: str, text: str) -> EpicsProperty:
    restrictions = {}
    m = re.search(r"<([^<>]*)>\s*$", text)
    if m:
        for part in m.group(1).split(";"):
            if ":" in part:
                key, val = part.split(":", 1)
                restrictions[key.strip().lower()] = val.strip()
        text = text[: m.start()].rstrip()
    flag = None
    m = re.search(r"\s([WC])$", text)
    if m:
        flag, text = m.group(1), text[: m.start()].rstrip()
    return EpicsProperty(name, text, flag, restrictions)


def _parse_object(body: str) -> EpicsObject:
    obj = EpicsObject("")
    pos = 0
    pattern = re.compile(r"\s*([A-Za-z0-9_\-]+)\s*:\s*")
    while True:
        m = pattern.match(body, pos)
        if not m:
            break
        name, pos = m.group(1).lower().replace("_", "-"), m.end()
        depth, quote, i = 0, None, pos
        while i < len(body):
            ch = body[i]
            if quote:
                if ch == quote:
                    quote = None
            elif ch in "\"'`":
                quote = "'" if ch == "`" else ch
            elif ch in "{(<":
                depth += 1
            elif ch in "})>":
                depth -= 1
            elif ch == "\n" and depth <= 0:
                break
            i += 1
        obj.properties[name] = _parse_property(name, body[pos:i].strip())
        pos = i
    if "object-identifier" in obj.properties:
        obj.object_identifier = obj.properties["object-identifier"].value
    return obj


def parse_epics(path: Path) -> Epics:
    text = _strip_comments(path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n"))
    if SIGNATURE not in text:
        raise ValueError(f"{path} is not an EPICS file (missing signature line)")
    text = text.split(SIGNATURE, 1)[1].split(END, 1)[0]
    epics = Epics()
    for name, body in _sections(text):
        key = name.lower()
        if key in GENERAL:
            epics.general[key] = _unquote(body)
        elif key == "bibbs supported":
            epics.bibbs = [line.split()[0].upper() for line in _lines(body)]
        elif key == "bacnet standard application services supported":
            for line in _lines(body):
                words = line.split()
                roles = {w.lower() for w in words if w.lower() in ("initiate", "execute")}
                service = canonical_service(
                    " ".join(w for w in words if w.lower() not in ("initiate", "execute"))
                )
                if service:
                    epics.services[service] = roles
                else:
                    epics.unknown.append(f"service: {line}")
        elif key == "standard object types supported":
            for line in _lines(body):
                words = line.split()
                flags = {w.lower() for w in words if w.lower() in ("createable", "deleteable")}
                object_type = canonical_object_type(" ".join(w for w in words if w.lower() not in flags))
                if object_type:
                    epics.object_types[object_type] = flags
                else:
                    epics.unknown.append(f"object type: {line}")
        elif key == "fail times":
            for line in _lines(body):
                if ":" in line:
                    label, value = line.split(":", 1)
                    with contextlib.suppress(ValueError):
                        epics.fail_times[label.strip().lower()] = float(value.strip())
        elif key == "default property value restrictions":
            for line in _lines(body):
                if ":" in line:
                    datatype, rest = line.split(":", 1)
                    epics.default_restrictions[datatype.strip().lower()] = _parse_property(
                        datatype, "x " + rest.strip()
                    ).restrictions
        elif key.startswith("list of objects"):
            pos = 0
            while True:
                start = body.find("{", pos)
                if start < 0:
                    break
                inner, pos = _block(body, start)
                epics.objects.append(_parse_object(inner))
    return epics
