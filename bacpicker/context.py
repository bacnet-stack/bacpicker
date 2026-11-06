# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""IUT profile and the per-test context handed to every conformance test."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, NoReturn, Optional, Set, Tuple

from bacpypes3.apdu import APDU, ErrorRejectAbortNack
from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.constructeddata import Array
from bacpypes3.pdu import Address, GlobalBroadcast, LocalBroadcast
from bacpypes3.primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Enumerated,
    Integer,
    Null,
    ObjectIdentifier,
    ObjectType,
    OctetString,
    Real,
    TagClass,
    Time,
    Unsigned,
)
from bacpypes3.vendor import get_vendor_info

from .assertions import AssertionsMixin, SkipTest, format_pdu
from .config import RunConfig
from .registry import TestCase
from .result import Defect, TestResult
from .standard import normalize, object_spec

# properties every object has, used when the object type is proprietary
_COMMON_PROPERTY_TYPES = {
    "object-identifier": ObjectIdentifier,
    "object-name": CharacterString,
    "object-type": ObjectType,
}


@dataclass
class DeviceProfile:
    """What the tester learned about the IUT during discovery."""

    address: Address
    device_id: ObjectIdentifier
    vendor_id: int
    max_apdu_length_accepted: int
    segmentation_supported: str
    object_name: Optional[str] = None
    vendor_name: Optional[str] = None
    model_name: Optional[str] = None
    firmware_revision: Optional[str] = None
    application_software_version: Optional[str] = None
    protocol_version: Optional[int] = None
    protocol_revision: Optional[int] = None
    services_supported: Set[str] = field(default_factory=set)
    object_types_supported: Set[str] = field(default_factory=set)
    services_supported_length: Optional[int] = None
    object_types_supported_length: Optional[int] = None
    object_list: List[ObjectIdentifier] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def device_instance(self) -> int:
        return self.device_id[1]

    def supports_service(self, name: str) -> bool:
        return name in self.services_supported

    def supports_object_type(self, name: str) -> bool:
        return normalize(name) in {normalize(t) for t in self.object_types_supported}

    def segmented_transmit(self) -> bool:
        return self.segmentation_supported in ("segmented-both", "segmented-transmit")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "address": str(self.address),
            "device_id": str(self.device_id),
            "object_name": self.object_name,
            "vendor_id": self.vendor_id,
            "vendor_name": self.vendor_name,
            "model_name": self.model_name,
            "firmware_revision": self.firmware_revision,
            "application_software_version": self.application_software_version,
            "protocol_version": self.protocol_version,
            "protocol_revision": self.protocol_revision,
            "max_apdu_length_accepted": self.max_apdu_length_accepted,
            "segmentation_supported": self.segmentation_supported,
            "services_supported": sorted(self.services_supported),
            "object_types_supported": sorted(self.object_types_supported),
            "services_supported_length": self.services_supported_length,
            "object_types_supported_length": self.object_types_supported_length,
            "object_count": len(self.object_list),
            "warnings": list(self.warnings),
        }


class TestContext(AssertionsMixin):
    """Everything a test needs: the tester application, the IUT profile and result logging."""

    __test__ = False

    def __init__(
        self,
        app: Any,
        profile: DeviceProfile,
        config: RunConfig,
        case: TestCase,
        result: TestResult,
        shared: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.app = app
        self.iut = profile
        self.config = config
        self.case = case
        self.result = result
        # run-wide state shared between tests, e.g. the test database and the EPICS
        self.shared = shared if shared is not None else {}
        self.log = logging.getLogger(case.module)
        self._current_step = "setup"

    @property
    def clause(self) -> str:
        return self.case.clause

    @property
    def epics(self) -> Any:
        """The EPICS given with --epics, or None."""
        return self.shared.get("epics")

    async def test_database(self) -> Any:
        """The IUT's objects and property values, read once per run."""
        if "database" not in self.shared:
            from .database import read_database

            self.shared["database"] = await read_database(
                self.app, self.iut, probe_writes=self.config.allow_writes
            )
        return self.shared["database"]

    # ---- logging ---------------------------------------------------------

    def step(self, text: str) -> None:
        self._current_step = text
        self.result.steps.append(text)
        self.log.debug("[%s] %s", self.clause, text)

    def note(self, text: str) -> None:
        self.result.steps.append(f"  note: {text}")
        self.log.debug("[%s]   %s", self.clause, text)

    def skip(self, reason: str) -> NoReturn:
        raise SkipTest(reason)

    def defect(
        self,
        message: str,
        *,
        expected: Any = None,
        actual: Any = None,
        request: Any = None,
        response: Any = None,
        step: Optional[str] = None,
    ) -> None:
        defect = Defect(
            clause=self.clause,
            step=step or self._current_step,
            message=message,
            expected=None if expected is None else str(expected),
            actual=None if actual is None else str(actual),
            request=None if request is None else format_pdu(request),
            response=None if response is None else format_pdu(response),
        )
        self.result.defects.append(defect)
        self.log.debug("[%s] DEFECT %s", self.clause, defect)

    # ---- communication ---------------------------------------------------

    async def send(self, request: APDU) -> APDU:
        """Send a confirmed request to the IUT; Error/Reject/Abort are raised."""
        if request.pduDestination is None:
            request.pduDestination = self.iut.address
        self.log.debug("[%s] -> %s", self.clause, format_pdu(request))
        try:
            response = await self.app.request(request)
        except ErrorRejectAbortNack as err:
            self.log.debug("[%s] <- %s", self.clause, format_pdu(err))
            raise
        self.log.debug("[%s] <- %s", self.clause, format_pdu(response))
        return response

    async def collect(
        self,
        request: APDU,
        match: Callable[[APDU], bool],
        window: float,
        first_only: bool = False,
    ) -> List[APDU]:
        """Send an unconfirmed request and gather matching APDUs received within the window.

        first_only implements "BEFORE <time> RECEIVE": return as soon as one matches.
        """
        received: List[APDU] = []
        got_one = asyncio.Event()

        def listener(apdu: APDU) -> None:
            if match(apdu):
                received.append(apdu)
                got_one.set()

        self.app.add_listener(listener)
        try:
            self.log.debug("[%s] -> %s", self.clause, format_pdu(request))
            await self.app.request(request)
            if first_only:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(got_one.wait(), timeout=window)
            else:
                await asyncio.sleep(window)
        finally:
            self.app.remove_listener(listener)
        for apdu in received:
            self.log.debug("[%s] <- %s", self.clause, format_pdu(apdu))
        return received

    def destination(self, kind: str) -> Address:
        """135.1 DESTINATION: "local" broadcast, "global" broadcast, or the "iut"."""
        if kind == "iut":
            return self.iut.address
        if self.config.unicast:
            self.note(f"--unicast: {kind} broadcast sent directly to the IUT")
            return self.iut.address
        return LocalBroadcast() if kind == "local" else GlobalBroadcast()

    # ---- data helpers ----------------------------------------------------

    def object_class(self, objid: ObjectIdentifier) -> Any:
        return get_vendor_info(self.iut.vendor_id).get_object_class(objid[0])

    def property_type(self, objid: ObjectIdentifier, prop: str) -> Any:
        object_class = self.object_class(objid)
        ptype = object_class.get_property_type(PropertyIdentifier(prop)) if object_class else None
        return ptype or _COMMON_PROPERTY_TYPES.get(prop)

    def model_properties(self, objid: ObjectIdentifier) -> Set[str]:
        """Standard properties defined for this object type (ASHRAE CSML, else bacpypes3)."""
        spec = object_spec(str(objid[0]))
        if spec is not None:
            return spec.names
        object_class = self.object_class(objid)
        names = set(_COMMON_PROPERTY_TYPES)
        for cls in getattr(object_class, "__mro__", ()):
            names |= {_prop_name(p) for p in getattr(cls, "_elements", {}) or {}}
        return names

    def model_required(self, objid: ObjectIdentifier) -> Set[str]:
        """Properties with conformance code R or W (ASHRAE CSML, else bacpypes3)."""
        spec = object_spec(str(objid[0]))
        if spec is not None:
            return spec.required(self.iut.protocol_revision)
        object_class = self.object_class(objid)
        names = set(_COMMON_PROPERTY_TYPES)
        for cls in getattr(object_class, "__mro__", ()):
            names |= {_prop_name(p) for p in cls.__dict__.get("_required", ())}
        return names

    def unsupported_properties(self, objid: ObjectIdentifier, count: int) -> List[str]:
        """Standard properties that are not defined for this object's type."""
        defined = self.model_properties(objid)
        found = [p for p in _UNSUPPORTED_CANDIDATES if p not in defined]
        if len(found) < count:
            raise SkipTest(f"cannot find {count} standard properties undefined for {objid[0]}")
        return found[:count]

    async def property_list(self, objid: ObjectIdentifier) -> Optional[List[str]]:
        """The object's Property_List, or None if it cannot be read."""
        try:
            value = await self.read(objid, "property-list")
        except ErrorRejectAbortNack:
            return None
        return [str(PropertyIdentifier(p)) for p in value]

    def decode(self, objid: ObjectIdentifier, prop: str, index: Optional[int], value: Any) -> Any:
        """Cast an Any from an ACK to the property's datatype, if the tester knows it."""
        ptype = self.property_type(objid, prop)
        if ptype is None:
            return value
        if issubclass(ptype, Array) and index is not None:
            ptype = Unsigned if index == 0 else ptype._subtype
        return value.cast_out(ptype)

    async def read(self, objid: Any, prop: str, array_index: Optional[int] = None) -> Any:
        """Read and decode a property value; Error/Reject/Abort are raised."""
        return await self.app.read_property(self.iut.address, objid, prop, array_index)

    def test_objects(self) -> List[ObjectIdentifier]:
        """Objects to iterate over, limited by --max-objects (device object always first)."""
        objects = [self.iut.device_id] + [
            o for o in self.iut.object_list if o != self.iut.device_id
        ]
        return objects[: max(1, self.config.max_objects)]

    def one_per_type(self) -> List[ObjectIdentifier]:
        """One instance of each object type present in the IUT (Device first)."""
        seen: Dict[str, ObjectIdentifier] = {str(self.iut.device_id[0]): self.iut.device_id}
        for objid in self.iut.object_list:
            seen.setdefault(str(objid[0]), objid)
        return list(seen.values())

    def two_objects(self) -> Tuple[ObjectIdentifier, ObjectIdentifier]:
        """Object1 and Object2 for the 9.20 procedures (two objects from the IUT database)."""
        objects = self.test_objects()
        if len(objects) < 2:
            raise SkipTest("135.1 requires at least two objects in the IUT database")
        return objects[0], objects[1]

    def unknown_object_id(self, object_type: Optional[str] = None) -> ObjectIdentifier:
        """A standard object identifier that is not in the IUT's Object_List.

        Defaults to a type the IUT supports (other than Device), else analog-value.
        """
        if object_type is None:
            types = [
                o[0] for o in self.iut.object_list
                if o[0] != self.iut.device_id[0] and int(o[0]) < 128
            ]
            object_type = str(types[0]) if types else "analog-value"
        used = {o[1] for o in self.iut.object_list if str(o[0]) == object_type}
        instance = 4194302
        while instance in used:
            instance -= 1
        return ObjectIdentifier((ObjectType(object_type), instance))


def _prop_name(prop: Any) -> str:
    try:
        return str(PropertyIdentifier(prop))
    except Exception:
        return str(prop)


# standard properties used to provoke UNKNOWN_PROPERTY; the first ones not defined
# for the object's type in the tester's object model are chosen
_UNSUPPORTED_CANDIDATES = (
    "present-value",
    "priority-array",
    "relinquish-default",
    "units",
    "cov-increment",
    "polarity",
    "number-of-states",
    "vendor-name",
    "object-list",
)


# application tag number of each 135 base (primitive) data type
BASE_TYPES = (
    (Null, 0),
    (Boolean, 1),
    (Unsigned, 2),
    (Integer, 3),
    (Real, 4),
    (Double, 5),
    (OctetString, 6),
    (CharacterString, 7),
    (BitString, 8),
    (Enumerated, 9),
    (Date, 10),
    (Time, 11),
    (ObjectIdentifier, 12),
)


def base_type(ptype: Any) -> Optional[type]:
    """The primitive base data type of a property datatype, or None if constructed."""
    if not isinstance(ptype, type):
        return None
    for base, _tag in BASE_TYPES:
        if issubclass(ptype, base):
            return base
    return None


def value_tags(value: Any) -> List[Any]:
    """The tags of an Any, without the enclosing context tags bacpypes3 keeps for RPM results."""
    tags = list(getattr(value, "tagList", None) or [])
    if (
        len(tags) >= 2
        and tags[0].tag_class == TagClass.opening
        and tags[-1].tag_class == TagClass.closing
        and tags[0].tag_number == tags[-1].tag_number
    ):
        tags = tags[1:-1]
    return tags


def application_tag(value: Any) -> Optional[int]:
    """Application tag number of a single primitive value inside an Any, else None."""
    tags = value_tags(value)
    if len(tags) != 1 or tags[0].tag_class != TagClass.application:
        return None
    return int(tags[0].tag_number)
