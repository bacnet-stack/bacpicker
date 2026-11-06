# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 clause 5 EPICS Consistency Tests.

The "test database" is read from the IUT (as the bacnet-stack bacepics tool does), so these
checks compare the standard against live data. Sections that cannot be read from a device
(BIBBs, Initiate support, W/C markings, restrictions) come from the EPICS given with --epics.
"""

from __future__ import annotations

import re
from typing import Dict, Optional, Set, Tuple

from ..context import TestContext
from ..registry import conformance_test
from ..standard import (
    bibbs,
    canonical_object_type,
    defined_bits,
    object_spec,
    object_type_epics_name,
    revisions,
    service_epics_name,
)

NEEDS_BIBBS = "requires --epics with the BIBBs Supported section filled in"


def _declared_bibbs(ctx: TestContext):
    epics = ctx.epics
    if epics is None or not epics.bibbs:
        ctx.skip(NEEDS_BIBBS)
    known = bibbs()
    for acronym in epics.bibbs:
        ctx.check(acronym in known, f"EPICS lists unknown BIBB {acronym}", expected="an Annex K BIBB")
    return [known[a] for a in epics.bibbs if a in known]


async def _present_types(ctx: TestContext) -> Set[str]:
    database = await ctx.test_database()
    return {r.object_type for r in database.objects.values()}


def _epics_objid(text: str) -> Optional[Tuple[str, int]]:
    m = re.match(r"\(\s*(proprietary\s+\d+|[A-Za-z0-9 _\-]+?)\s*,\s*(\d+)\s*\)", text or "")
    if not m:
        return None
    kind = m.group(1)
    if kind.startswith("proprietary"):
        kind = re.sub(r"\s+", " ", kind)
    else:
        kind = canonical_object_type(kind) or kind
    return kind, int(m.group(2))


def _objid_key(objid) -> Tuple[str, int]:
    kind = int(objid[0])
    name = f"proprietary {kind}" if kind >= 128 else canonical_object_type(str(objid[0])) or str(objid[0])
    return name, objid[1]


# ---- BIBB consistency (a)-(e) ----------------------------------------------------


@conformance_test("5(a)", "BIBB-required object types are in Standard Object Types Supported")
async def epics_a(ctx: TestContext) -> None:
    for bibb in _declared_bibbs(ctx):
        for alternatives in bibb.object_types:
            ctx.step(f"{bibb.acronym} ({bibb.clause}) requires one of {', '.join(alternatives)}")
            ctx.check(
                any(t in ctx.epics.object_types for t in alternatives),
                f"{bibb.acronym} requires an object type missing from Standard Object Types Supported",
                expected=" | ".join(object_type_epics_name(t) for t in alternatives),
                actual=", ".join(object_type_epics_name(t) for t in sorted(ctx.epics.object_types)),
            )


@conformance_test("5(b)", "Test database has an instance of each BIBB-required object type")
async def epics_b(ctx: TestContext) -> None:
    declared = _declared_bibbs(ctx)
    present = await _present_types(ctx)
    for bibb in declared:
        for alternatives in bibb.object_types:
            ctx.step(f"{bibb.acronym}: an instance of {' | '.join(alternatives)}")
            ctx.check(
                any(t in present for t in alternatives),
                f"{bibb.acronym} requires an object that is not in the IUT's database",
                expected=" | ".join(alternatives),
                actual=", ".join(sorted(present)),
            )


@conformance_test("5(c)", "Protocol_Object_Types_Supported indicates each BIBB-required object type")
async def epics_c(ctx: TestContext) -> None:
    for bibb in _declared_bibbs(ctx):
        for alternatives in bibb.object_types:
            ctx.step(f"{bibb.acronym}: Protocol_Object_Types_Supported has {' | '.join(alternatives)}")
            ctx.check(
                any(ctx.iut.supports_object_type(t) for t in alternatives),
                f"{bibb.acronym} requires an object type not set in Protocol_Object_Types_Supported",
                expected=" | ".join(alternatives),
                actual=", ".join(sorted(ctx.iut.object_types_supported)) or "(none)",
            )


@conformance_test("5(d)", "BIBB-required services are in Application Services Supported")
async def epics_d(ctx: TestContext) -> None:
    for bibb in _declared_bibbs(ctx):
        for role, services in (("initiate", bibb.initiate), ("execute", bibb.execute)):
            for service in services:
                ctx.step(f"{bibb.acronym} ({bibb.clause}): {service_epics_name(service)} {role.capitalize()}")
                ctx.check(
                    role in ctx.epics.services.get(service, set()),
                    f"{bibb.acronym} requires {service_epics_name(service)} {role.capitalize()}",
                    expected=f"{service_epics_name(service)} {role.capitalize()}",
                    actual=" ".join(sorted(ctx.epics.services.get(service, set()))) or "not listed",
                )


@conformance_test("5(e)", "Protocol_Services_Supported indicates each BIBB-required executed service")
async def epics_e(ctx: TestContext) -> None:
    for bibb in _declared_bibbs(ctx):
        for service in bibb.execute:
            ctx.step(f"{bibb.acronym}: Protocol_Services_Supported has {service}")
            ctx.check(
                ctx.iut.supports_service(service),
                f"{bibb.acronym} requires execution of {service_epics_name(service)}, "
                "which is not set in Protocol_Services_Supported",
                expected=service,
                actual=", ".join(sorted(ctx.iut.services_supported)),
            )


# ---- object types and the object database (f)-(h) --------------------------------


@conformance_test("5(f)", "Standard Object Types Supported matches Protocol_Object_Types_Supported")
async def epics_f(ctx: TestContext) -> None:
    if ctx.epics is None:
        ctx.skip("requires --epics (without it the EPICS section is generated from the property)")
    epics_types = set(ctx.epics.object_types)
    supported = {canonical_object_type(t) or t for t in ctx.iut.object_types_supported}
    ctx.step("Compare the EPICS section with Protocol_Object_Types_Supported")
    ctx.check(
        not sorted(epics_types - supported),
        "Object types in the EPICS but not in Protocol_Object_Types_Supported",
        actual=", ".join(sorted(epics_types - supported)),
    )
    ctx.check(
        not sorted(supported - epics_types),
        "Object types in Protocol_Object_Types_Supported but not in the EPICS",
        actual=", ".join(sorted(supported - epics_types)),
    )
    for line in ctx.epics.unknown:
        ctx.defect("EPICS entry does not match a standard name", actual=line)


@conformance_test("5(g)", "At least one object of each supported object type")
async def epics_g(ctx: TestContext) -> None:
    present = await _present_types(ctx)
    if ctx.epics is not None:
        supported = dict(ctx.epics.object_types)
        ctx.step("Object types from the EPICS Standard Object Types Supported section")
    else:
        supported = {canonical_object_type(t) or t: set() for t in ctx.iut.object_types_supported}
        ctx.step("Object types from Protocol_Object_Types_Supported (no --epics)")
    for object_type, flags in sorted(supported.items()):
        if object_type == "file" and "createable" in flags and object_type not in present:
            ctx.note("no File object; permitted because File is Createable")
            continue
        ctx.check(
            object_type in present,
            f"No {object_type_epics_name(object_type)} object in the IUT's database",
            expected=f"at least one {object_type} object",
            actual="none",
        )


@conformance_test("5(h)", "Object_List corresponds one-to-one with the test database")
async def epics_h(ctx: TestContext) -> None:
    database = await ctx.test_database()
    object_list = ctx.iut.object_list
    ctx.step("Object_List has no duplicate entries")
    duplicates = sorted({str(o) for o in object_list if object_list.count(o) > 1})
    ctx.check(not duplicates, "Object_List contains duplicate entries", actual=", ".join(duplicates))
    ctx.step("Every Object_List entry exists and reports its own Object_Identifier")
    for objid, record in database.objects.items():
        prop = record.properties.get("object-identifier")
        ctx.check(
            record.read_error is None and prop is not None and prop.present and prop.value == objid,
            f"Object {objid} in Object_List cannot be read or has a different Object_Identifier",
            expected=objid,
            actual=record.read_error or (prop.value if prop else "Object_Identifier missing"),
        )
    if ctx.epics is not None:
        ctx.step("EPICS test database objects match Object_List")
        listed = {_objid_key(o) for o in object_list}
        in_epics = {_epics_objid(o.object_identifier) for o in ctx.epics.objects}
        ctx.check(not sorted(listed - in_epics, key=str), "Objects in Object_List missing from the EPICS",
                  actual=sorted(listed - in_epics, key=str))
        ctx.check(not sorted(in_epics - listed, key=str), "Objects in the EPICS missing from Object_List",
                  actual=sorted(in_epics - listed, key=str))


# ---- properties (i), (j), (m), (n), (p), (q), (r) --------------------------------


@conformance_test("5(i)", "Required and conditionally required properties are present")
async def epics_i(ctx: TestContext) -> None:
    database = await ctx.test_database()
    revision = ctx.iut.protocol_revision
    ctx.note("source: ASHRAE CSML bacnet-object-types.xml; revision-specific property "
             "additions are only applied where data/revisions.json lists them")
    for objid, record in database.objects.items():
        present = set(record.present())
        spec = object_spec(record.object_type)
        if spec is None:
            ctx.step(f"{objid}: proprietary object, check Object_Identifier/Object_Name/Object_Type")
            missing = {"object-identifier", "object-name", "object-type"} - present
            ctx.check(not missing, f"{objid}: required properties missing", actual=sorted(missing))
            continue
        ctx.step(f"{objid}: required properties ({record.source})")
        missing = sorted(spec.required(revision) - present)
        ctx.check(not missing, f"{objid}: required properties missing", actual=", ".join(missing))
        for pspec in spec.properties:
            if pspec.optional and pspec.name not in present:
                triggers = sorted(set(pspec.required_with) & present)
                ctx.check(
                    not triggers,
                    f"{objid}: {pspec.name} is required when {', '.join(triggers)} is present",
                    expected=pspec.name,
                    actual="absent",
                )
        undefined = sorted(n for n, p in record.present().items() if p.standard and n not in spec.names)
        ctx.check(
            not undefined,
            f"{objid}: standard properties not defined for {record.object_type}",
            actual=", ".join(undefined),
        )


def _writability_source(ctx: TestContext, database) -> str:
    if database.writes_probed:
        return "probe"
    if ctx.epics is not None:
        return "epics"
    ctx.skip("requires --allow-writes to probe writability, or --epics with W/C markings")


def _marked_writable(ctx: TestContext, source: str, record, name: str) -> Optional[bool]:
    if source == "probe":
        prop = record.properties.get(name)
        return prop.writable if prop else None
    key = _objid_key(record.objid)
    for obj in ctx.epics.objects:
        if _epics_objid(obj.object_identifier) == key and name in obj.properties:
            return obj.properties[name].flag in ("W", "C")
    return None


async def _writability(ctx: TestContext, required: bool) -> None:
    database = await ctx.test_database()
    source = _writability_source(ctx, database)
    ctx.note(f"writability from {'the EPICS W/C markings' if source == 'epics' else 'write-back probing'}")
    for objid, record in database.objects.items():
        spec = object_spec(record.object_type)
        if spec is None:
            continue
        ctx.step(f"{objid}: {'W' if required else 'read-only'} properties")
        for pspec in spec.properties:
            if pspec.writable is not required or pspec.name not in record.present():
                continue
            marked = _marked_writable(ctx, source, record, pspec.name)
            if marked is None:
                continue
            if required:
                ctx.check(marked, f"{objid}: {pspec.name} is required to be writable",
                          expected="W", actual="not writable")
            else:
                ctx.check(not marked, f"{objid}: {pspec.name} is required to be read-only",
                          expected="read-only", actual="writable")


@conformance_test("5(j)", "Properties required to be writable are marked writable")
async def epics_j(ctx: TestContext) -> None:
    await _writability(ctx, required=True)


@conformance_test("5(k)", "Protocol_Services_Supported length matches the Protocol_Revision")
async def epics_k(ctx: TestContext) -> None:
    await _bit_length(ctx, "services", ctx.iut.services_supported_length, "Protocol_Services_Supported")


@conformance_test("5(l)", "Protocol_Object_Types_Supported length matches the Protocol_Revision")
async def epics_l(ctx: TestContext) -> None:
    await _bit_length(
        ctx, "object_types", ctx.iut.object_types_supported_length, "Protocol_Object_Types_Supported"
    )


async def _bit_length(ctx: TestContext, kind: str, length: Optional[int], label: str) -> None:
    revision = ctx.iut.protocol_revision
    if revision is None:
        ctx.skip("Protocol_Revision is absent")
    if length is None:
        ctx.skip(f"{label} could not be read")
    expected, verified = defined_bits(kind, revision)
    ctx.step(f"{label} has {length} bits; Protocol_Revision {revision} defines {expected}")
    if not verified:
        ctx.note(f"expected length {expected} comes from an unverified data/revisions.json entry")
        if length != expected:
            ctx.note(f"{label} length {length} differs from {expected}; not reported as a defect")
        return
    ctx.check_equal(length, expected, f"{label} bit length is wrong for Protocol_Revision {revision}")


@conformance_test("5(m)", "Deprecated or removed properties are absent")
async def epics_m(ctx: TestContext) -> None:
    removed: Dict[str, dict] = revisions()["properties_removed"]
    if not removed:
        ctx.skip("data/revisions.json has no deprecated/removed property entries")
    database = await ctx.test_database()
    revision = ctx.iut.protocol_revision or 0
    for objid, record in database.objects.items():
        for name, entry in removed.items():
            if revision >= entry["revision"] and name in record.present():
                ctx.defect(f"{objid}: {name} was removed in Protocol_Revision {entry['revision']}",
                           actual=f"present at Protocol_Revision {revision}")


@conformance_test("5(n)", "Property_List lists every property present", min_protocol_revision=14)
async def epics_n(ctx: TestContext) -> None:
    database = await ctx.test_database()
    excluded = {"object-identifier", "object-name", "object-type", "property-list"}
    for objid, record in database.objects.items():
        ctx.step(f"{objid}: Property_List vs properties present ({record.source})")
        if not ctx.check(record.property_list is not None, f"{objid}: Property_List is missing",
                         expected="Property_List", actual="absent"):
            continue
        listed = set(record.property_list)
        present = set(record.present()) - excluded
        ctx.check(not sorted(present - listed), f"{objid}: properties present but not in Property_List",
                  actual=", ".join(sorted(present - listed)))
        ctx.check(not sorted(listed - excluded - present),
                  f"{objid}: Property_List entries that are not present",
                  actual=", ".join(sorted(listed - excluded - present)))
        ctx.check(not sorted(listed & excluded), f"{objid}: Property_List contains excluded properties",
                  actual=", ".join(sorted(listed & excluded)))


@conformance_test("5(o)", "Max_Segments_Accepted > 1 when segmented requests are accepted")
async def epics_o(ctx: TestContext) -> None:
    if ctx.iut.segmentation_supported not in ("segmented-both", "segmented-receive"):
        ctx.skip(f"Segmentation_Supported is {ctx.iut.segmentation_supported}")
    database = await ctx.test_database()
    device = database.objects.get(ctx.iut.device_id)
    prop = device.properties.get("max-segments-accepted") if device else None
    ctx.step("Max_Segments_Accepted of the Device object")
    value = prop.value if prop is not None and prop.present else None
    ctx.check(value is not None and int(value) > 1, "Max_Segments_Accepted must be greater than 1",
              expected="> 1", actual=value if value is not None else "absent")


@conformance_test("5(p)", "Properties required to be read-only are not marked writable")
async def epics_p(ctx: TestContext) -> None:
    await _writability(ctx, required=False)


@conformance_test("5(q)", "Property values are within the ranges defined by the standard")
async def epics_q(ctx: TestContext) -> None:
    database = await ctx.test_database()
    for objid, record in database.objects.items():
        spec = object_spec(record.object_type)
        if spec is None:
            continue
        for name, prop in record.present().items():
            pspec = spec.get(name)
            if pspec is None or prop.value is None:
                continue
            value = prop.value
            if pspec.minimum is not None and isinstance(value, (int, float)):
                ctx.check(value >= pspec.minimum, f"{objid}: {name} below the standard minimum",
                          expected=f">= {pspec.minimum:g}", actual=value)
            if pspec.maximum is not None and isinstance(value, (int, float)):
                ctx.check(value <= pspec.maximum, f"{objid}: {name} above the standard maximum",
                          expected=f"<= {pspec.maximum:g}", actual=value)
            if pspec.minimum_length is not None and isinstance(value, str):
                ctx.check(len(value) >= pspec.minimum_length, f"{objid}: {name} is too short",
                          expected=f"length >= {pspec.minimum_length}", actual=repr(str(value)))
            if isinstance(value, (list, tuple)) and pspec.datatype == "Array":
                if pspec.minimum_size is not None:
                    ctx.check(len(value) >= pspec.minimum_size, f"{objid}: {name} has too few elements",
                              expected=f">= {pspec.minimum_size}", actual=len(value))
                if pspec.maximum_size is not None:
                    ctx.check(len(value) <= pspec.maximum_size, f"{objid}: {name} has too many elements",
                              expected=f"<= {pspec.maximum_size}", actual=len(value))


@conformance_test("5(r)", "EPICS value restrictions are within the standard's ranges")
async def epics_r(ctx: TestContext) -> None:
    epics = ctx.epics
    restricted = [
        (obj, prop) for obj in (epics.objects if epics else []) for prop in obj.properties.values()
        if prop.restrictions
    ]
    if not restricted:
        ctx.skip("no property value restrictions in the EPICS")
    for obj, prop in restricted:
        key = _epics_objid(obj.object_identifier)
        spec = object_spec(key[0]) if key else None
        pspec = spec.get(prop.name) if spec else None
        if pspec is None:
            continue
        ctx.step(f"{obj.object_identifier} {prop.name} <{prop.restrictions}>")
        r = prop.restrictions
        try:
            if "minimum" in r and pspec.minimum is not None:
                ctx.check(float(r["minimum"]) >= pspec.minimum,
                          f"{prop.name}: restricted minimum below the standard minimum",
                          expected=f">= {pspec.minimum:g}", actual=r["minimum"])
            if "maximum" in r and pspec.maximum is not None:
                ctx.check(float(r["maximum"]) <= pspec.maximum,
                          f"{prop.name}: restricted maximum above the standard maximum",
                          expected=f"<= {pspec.maximum:g}", actual=r["maximum"])
            if "maximum length string" in r and pspec.minimum_length is not None:
                ctx.check(int(r["maximum length string"]) >= pspec.minimum_length,
                          f"{prop.name}: maximum length string excludes the standard's minimum length",
                          expected=f">= {pspec.minimum_length}", actual=r["maximum length string"])
            if "maximum length array" in r and pspec.minimum_size is not None:
                ctx.check(int(r["maximum length array"]) >= pspec.minimum_size,
                          f"{prop.name}: maximum length array is below the standard's minimum size",
                          expected=f">= {pspec.minimum_size}", actual=r["maximum length array"])
        except ValueError as err:
            ctx.defect(f"{prop.name}: malformed restriction", actual=f"{r} ({err})")
