# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""The IUT's test database: every object in Object_List with its properties, read from the
device (as bacepics does) instead of taken from a hand-written EPICS."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bacpypes3.apdu import (
    ErrorPDU,
    ErrorRejectAbortNack,
    ReadPropertyMultipleACK,
    ReadPropertyMultipleRequest,
    ReadPropertyRequest,
    WritePropertyRequest,
)
from bacpypes3.basetypes import PropertyIdentifier, PropertyReference, ReadAccessSpecification
from bacpypes3.constructeddata import Any as AnyValue
from bacpypes3.constructeddata import SequenceOf
from bacpypes3.primitivedata import ObjectIdentifier, TagList
from bacpypes3.vendor import get_vendor_info

from .context import DeviceProfile, value_tags
from .standard import canonical_object_type, object_spec, property_identifiers

log = logging.getLogger(__name__)

COMMON_PROPERTIES = ("object-identifier", "object-name", "object-type")
# never write-probed: identity, structure, or a write would change the priority array
NO_PROBE = {
    "object-identifier", "object-type", "property-list", "object-list",
    "structured-object-list", "device-address-binding",
}
# abort reasons meaning the response did not fit
TOO_LARGE = ("segmentation-not-supported", "buffer-overflow", "apdu-too-long")
PROBE_TIMEOUT = 10.0
# writing a Network Port property, even with its own value, can set Changes_Pending
NO_PROBE_OBJECT_TYPES = {"network-port"}


@dataclass
class PropertyRecord:
    name: str
    identifier: int
    raw: Any = None  # bacpypes3 Any as received
    value: Any = None  # decoded value, or None if the tester has no datatype for it
    error: Optional[str] = None  # "error-class: error-code" when the read failed
    writable: Optional[bool] = None  # write-back probe result (None = not probed / inconclusive)

    @property
    def present(self) -> bool:
        return self.error is None or "unknown-property" not in self.error

    @property
    def standard(self) -> bool:
        return self.identifier < 512


@dataclass
class ObjectRecord:
    objid: ObjectIdentifier
    object_type: str
    source: str  # "rpm-all" | "property-list" | "standard-list"
    properties: Dict[str, PropertyRecord] = field(default_factory=dict)
    property_list: Optional[List[str]] = None
    read_error: Optional[str] = None

    def present(self) -> Dict[str, PropertyRecord]:
        return {n: p for n, p in self.properties.items() if p.present}


@dataclass
class TestDatabase:
    __test__ = False

    objects: Dict[ObjectIdentifier, ObjectRecord] = field(default_factory=dict)
    writes_probed: bool = False


def property_name(identifier: int) -> str:
    return property_identifiers().get(identifier) or str(identifier)


def _error_text(err: Any) -> str:
    if isinstance(err, ErrorPDU) or hasattr(err, "errorClass"):
        return f"{err.errorClass}: {err.errorCode}"
    return str(err)


def _strip(value: Any) -> Any:
    """A copy of the value without the enclosing context tags, for re-encoding."""
    return AnyValue(TagList(value_tags(value)))


def decode(vendor_id: int, objid: ObjectIdentifier, prop: str, value: Any) -> Any:
    """Decode an Any using the tester's datatype for the property, or None."""
    object_class = get_vendor_info(vendor_id).get_object_class(objid[0])
    try:
        ptype = object_class.get_property_type(PropertyIdentifier(prop)) if object_class else None
    except Exception:
        ptype = None
    if ptype is None:
        return None
    try:
        return value.cast_out(ptype)
    except Exception:
        return None


async def _read_all(
    app: Any, profile: DeviceProfile, objid: ObjectIdentifier
) -> Optional[Dict[str, PropertyRecord]]:
    request = ReadPropertyMultipleRequest(
        listOfReadAccessSpecs=SequenceOf(ReadAccessSpecification)(
            [
                ReadAccessSpecification(
                    objectIdentifier=objid,
                    listOfPropertyReferences=[PropertyReference(propertyIdentifier="all")],
                )
            ]
        ),
        destination=profile.address,
    )
    try:
        ack = await app.request(request)
    except ErrorRejectAbortNack as err:
        log.info("%s: ReadPropertyMultiple ALL failed (%s)", objid, err)
        return None
    if not isinstance(ack, ReadPropertyMultipleACK):
        return None
    records = {}
    for result in ack.listOfReadAccessResults:
        for element in result.listOfResults:
            identifier = int(element.propertyIdentifier)
            name = property_name(identifier)
            record = PropertyRecord(name, identifier)
            if element.readResult.propertyAccessError is not None:
                record.error = _error_text(element.readResult.propertyAccessError)
            else:
                record.raw = element.readResult.propertyValue
                record.value = decode(profile.vendor_id, objid, name, record.raw)
            records[name] = record
    return records


async def _read_one(app: Any, profile: DeviceProfile, objid: ObjectIdentifier, name: str) -> PropertyRecord:
    identifier = next((i for i, n in property_identifiers().items() if n == name), None)
    if identifier is None:
        identifier = int(name) if name.isdigit() else int(PropertyIdentifier(name))
    record = PropertyRecord(name, identifier)
    request = ReadPropertyRequest(
        objectIdentifier=objid, propertyIdentifier=identifier, destination=profile.address
    )
    try:
        ack = await app.request(request)
    except ErrorRejectAbortNack as err:
        record.error = _error_text(err)
        return record
    record.raw = ack.propertyValue
    record.value = decode(profile.vendor_id, objid, name, record.raw)
    return record


async def _read_array_by_element(
    app: Any, profile: DeviceProfile, objid: ObjectIdentifier, name: str
) -> PropertyRecord:
    """Large arrays (e.g. Object_List) that do not fit in one response."""
    record = PropertyRecord(name, int(PropertyIdentifier(name)))
    try:
        count = await app.read_property(profile.address, objid, name, 0)
        record.value = [
            await app.read_property(profile.address, objid, name, i) for i in range(1, int(count) + 1)
        ]
    except ErrorRejectAbortNack as err:
        record.error = _error_text(err)
    return record


async def read_object(app: Any, profile: DeviceProfile, objid: ObjectIdentifier) -> ObjectRecord:
    object_type = canonical_object_type(str(objid[0])) or str(objid[0])
    record = ObjectRecord(objid, object_type, source="rpm-all")

    records = None
    if profile.supports_service("read-property-multiple"):
        records = await _read_all(app, profile, objid)
        if records is not None and "property-list" not in records:
            # ALL never returns Property_List (135.1 9.20.1.7), so read it separately
            plist = await _read_one(app, profile, objid, "property-list")
            if plist.present:
                records["property-list"] = plist
    if records is None:
        plist = await _read_one(app, profile, objid, "property-list")
        if plist.error is None and plist.value is not None:
            record.source = "property-list"
            names = list(COMMON_PROPERTIES) + [str(PropertyIdentifier(p)) for p in plist.value]
            names = [property_name(int(PropertyIdentifier(n))) for n in names]
        else:
            # no Property_List: a pseudo list of the standard's required and optional properties
            record.source = "standard-list"
            spec = object_spec(object_type)
            names = list(COMMON_PROPERTIES) + sorted(
                (spec.names if spec else set()) - set(COMMON_PROPERTIES)
            )
        records = {}
        for name in dict.fromkeys(names):
            rec = await _read_one(app, profile, objid, name)
            if rec.error and any(k in rec.error for k in TOO_LARGE):
                rec = await _read_array_by_element(app, profile, objid, name)
            if record.source == "standard-list" and not rec.present:
                continue
            records[name] = rec

    record.properties = records
    if "property-list" in records and records["property-list"].value is not None:
        record.property_list = [
            property_name(int(p)) for p in records["property-list"].value
        ]
    if not records:
        record.read_error = "no properties could be read"
    return record


async def probe_writable(app: Any, profile: DeviceProfile, record: ObjectRecord) -> None:
    """Write each property's own value back to it to learn whether it is writable."""
    if record.object_type in NO_PROBE_OBJECT_TYPES:
        return
    spec = object_spec(record.object_type)
    for name, prop in record.properties.items():
        if prop.raw is None or name in NO_PROBE:
            continue
        pspec = spec.get(name) if spec else None
        if pspec is not None and pspec.commandable:
            continue
        request = WritePropertyRequest(
            objectIdentifier=record.objid,
            propertyIdentifier=prop.identifier,
            propertyValue=_strip(prop.raw),
            destination=profile.address,
        )
        try:
            log.debug("probe write %s %s", record.objid, name)
            await asyncio.wait_for(app.request(request), timeout=PROBE_TIMEOUT)
            prop.writable = True
        except ErrorPDU as err:
            code = str(err.errorCode)
            prop.writable = False if code in ("write-access-denied", "not-configurable") else None
        except (ErrorRejectAbortNack, asyncio.TimeoutError):
            prop.writable = None
        log.debug("probe write %s %s -> %s", record.objid, name, prop.writable)


async def read_database(app: Any, profile: DeviceProfile, *, probe_writes: bool = False) -> TestDatabase:
    database = TestDatabase(writes_probed=probe_writes)
    for objid in profile.object_list:
        if objid in database.objects:
            continue
        record = await read_object(app, profile, objid)
        if objid == profile.device_id and "object-list" in record.properties:
            object_list = record.properties["object-list"]
            if object_list.value is None or object_list.error:
                object_list.value, object_list.error = list(profile.object_list), None
        if probe_writes:
            await probe_writable(app, profile, record)
        database.objects[objid] = record
    return database
