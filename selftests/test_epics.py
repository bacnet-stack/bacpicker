# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from bacpypes3.basetypes import PropertyIdentifier
from bacpypes3.constructeddata import ArrayOf
from bacpypes3.local.object import Object as LocalObject
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, ObjectType
from test_end_to_end import run_suite
from test_framework import make_profile

from bacpicker.config import RunConfig
from bacpicker.database import ObjectRecord, TestDatabase, read_database, read_object
from bacpicker.epics import parse_epics, write_epics
from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.registry import get_test
from bacpicker.result import Status
from bacpicker.runner import Runner


async def generate(config, path):
    app = build_application(config)
    try:
        address, i_am = await discover_iut(app, config)
        profile = await build_profile(app, address, i_am)
        write_epics(path, profile, await read_database(app, profile), config)
    finally:
        app.close()


def uncomment(path, *bibbs):
    text = path.read_bytes().decode("utf-8")
    for bibb in bibbs:
        text = text.replace(f"\r\n-- {bibb}\r\n", f"\r\n{bibb}\r\n", 1)
    path.write_bytes(text.encode("utf-8"))


async def test_generated_epics_round_trip(loopback_config, tmp_path):
    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    assert path.read_bytes().startswith(b"PICS 0\r\nBACnet Protocol Implementation Conformance Statement\r\n")

    text = path.read_bytes().decode("utf-8")
    assert "DS-RP-B            -- executes ReadProperty" in text
    assert "\r\n-- SCHED-I-B\r\n" in text

    epics = parse_epics(path)
    assert epics.bibbs == [
        "DM-DDB-B",
        "DM-DOB-B",
        "DS-ACSC-B",
        "DS-ACUC-B",
        "DS-RP-B",
        "DS-RPM-B",
        "DS-WP-B",
        "NM-RC-B",
    ]
    assert epics.general["vendor name"] == "BACpypes"
    assert epics.services["read-property"] == {"execute"}
    assert epics.services["i-am"] == {"initiate"}
    assert set(epics.object_types) == {"device", "network-port", "analog-value", "binary-value"}
    assert epics.fail_times["unconfirmed response fail time"] == 0.5
    assert {o.object_identifier for o in epics.objects} >= {"(device, 1234)", "(analog-value, 1)"}
    av1 = next(o for o in epics.objects if o.object_identifier == "(analog-value, 1)")
    assert av1.properties["object-name"].value == '"Zone Temperature"'
    assert not epics.unknown

    uncomment(path, "SCHED-I-B")
    assert parse_epics(path).bibbs == [
        "DM-DDB-B",
        "DM-DOB-B",
        "DS-ACSC-B",
        "DS-ACUC-B",
        "DS-RP-B",
        "DS-RPM-B",
        "DS-WP-B",
        "NM-RC-B",
        "SCHED-I-B",
    ]


def test_ds_rp_b_stays_uncommented_when_read_property_is_not_inferred(tmp_path):
    path = tmp_path / "empty.tpi"
    write_epics(path, make_profile(services_supported=set()), TestDatabase(), RunConfig())
    assert "DS-RP-B            -- required of all BACnet devices" in path.read_text(encoding="utf-8")
    assert parse_epics(path).bibbs == ["DS-RP-B"]

    path = tmp_path / "who-is.tpi"
    write_epics(path, make_profile(services_supported={"who-is"}), TestDatabase(), RunConfig())
    text = path.read_text(encoding="utf-8")
    assert "DS-RP-B            -- required of all BACnet devices" in text
    assert "DM-DDB-B           -- executes Who-Is" in text
    assert parse_epics(path).bibbs == ["DM-DDB-B", "DS-RP-B"]


def test_internal_bibb_preferred_over_external_variant(tmp_path):
    path = tmp_path / "write-group.tpi"
    database = TestDatabase()
    objid = ObjectIdentifier("channel,1")
    database.objects[objid] = ObjectRecord(objid=objid, object_type="channel", source="rpm-all")
    write_epics(path, make_profile(services_supported={"write-group"}), database, RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "-- DS-WG-E-B" in lines
    assert any(line.startswith("DS-WG-I-B ") for line in lines)
    assert "DS-WG-E-B" not in parse_epics(path).bibbs


def test_you_are_implies_who_am_i_initiate_and_who_is_execute(tmp_path):
    path = tmp_path / "you-are.tpi"
    write_epics(path, make_profile(services_supported={"you-are"}), TestDatabase(), RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "Who-Am-I Initiate" in lines
    assert "Who-Is Execute" in lines
    assert "You-Are Execute" in lines
    assert parse_epics(path).services["who-am-i"] == {"initiate"}


async def test_missing_read_property_fails_clause_5e(tmp_path):
    path = tmp_path / "iut.tpi"
    profile = make_profile(services_supported=set())
    write_epics(path, profile, TestDatabase(), RunConfig())
    result = await Runner(None, profile, RunConfig(), shared={"epics": parse_epics(path)}).run_one(
        get_test("5(e)"), {}
    )
    assert result.status is Status.FAIL
    assert any("DS-RP-B" in defect.message and "ReadProperty" in defect.message for defect in result.defects)


async def test_bibb_consistency(loopback_config, tmp_path):
    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    uncomment(path, "DM-DDB-B", "SCHED-I-B")
    _profile, report = await run_suite(
        loopback_config, include=["5(a)", "5(b)", "5(c)", "5(d)", "5(e)"], epics=parse_epics(path)
    )
    status = {r.clause: r.status for r in report.results}
    # the simulator has no Calendar/Schedule objects, which SCHED-I-B requires
    assert status == {
        "5(a)": Status.FAIL,
        "5(b)": Status.FAIL,
        "5(c)": Status.FAIL,
        "5(d)": Status.PASS,
        "5(e)": Status.PASS,
    }, report.results
    messages = [d.message for r in report.results for d in r.defects]
    assert any("SCHED-I-B" in m for m in messages)


class ProprietaryObject(LocalObject):
    """Not registered with any VendorInfo, so the tester has no class for its type."""

    objectType = ObjectType(861)
    # bacpypes3's local Object._post_init reads notificationClass
    notificationClass = None
    _elements = {
        "objectIdentifier": ObjectIdentifier,
        "objectName": CharacterString,
        "objectType": ObjectType,
        "propertyList": ArrayOf(PropertyIdentifier),
    }


async def test_proprietary_object_matches_object_list(simulated_iut, loopback_config, tmp_path):
    app, _address = simulated_iut
    app.add_object(ProprietaryObject(objectIdentifier=(861, 1), objectName="Vendor Thing"))
    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    epics = parse_epics(path)
    assert "(proprietary 861, 1)" in {o.object_identifier for o in epics.objects}
    _profile, report = await run_suite(loopback_config, include=["5(h)"], epics=epics)
    (result,) = report.results
    assert result.status is Status.PASS, [d.message for d in result.defects]


async def test_proprietary_object_property_list_is_decoded(simulated_iut, loopback_config):
    app, _address = simulated_iut
    app.add_object(
        ProprietaryObject(
            objectIdentifier=(861, 1),
            objectName="Vendor Thing",
            propertyList=["object-identifier", "object-name", "object-type"],
        )
    )
    _profile, report = await run_suite(loopback_config, include=["5(n)"])
    (result,) = report.results
    messages = [d.message for d in result.defects]
    assert not any("861" in m and "Property_List is missing" in m for m in messages), messages


class ConformingPropertyListObject(ProprietaryObject):
    """Its Property_List excludes the identity properties and itself, as 135 requires."""

    _elements = {**ProprietaryObject._elements, "description": CharacterString}

    @property
    def propertyList(self):  # type: ignore[override]
        return ArrayOf(PropertyIdentifier)([PropertyIdentifier("description")])

    @propertyList.setter
    def propertyList(self, value):
        pass


async def test_property_list_kept_without_read_property_multiple(simulated_iut, loopback_config):
    app, _address = simulated_iut
    app.add_object(
        ConformingPropertyListObject(
            objectIdentifier=(861, 1), objectName="Vendor Thing", description="thing"
        )
    )
    tester = build_application(loopback_config)
    try:
        address, i_am = await discover_iut(tester, loopback_config)
        profile = await build_profile(tester, address, i_am)
        profile.services_supported.discard("read-property-multiple")
        record = await read_object(tester, profile, ObjectIdentifier((861, 1)))
    finally:
        tester.close()
    assert record.source == "property-list"
    assert record.property_list == ["description"]
    assert "property-list" in record.properties


async def test_restriction_outside_standard_range(loopback_config, tmp_path):
    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    text = path.read_bytes().decode("utf-8").replace(
        'object-name: "Zone Temperature"', 'object-name: "Zone Temperature" <maximum length string: 0>'
    )
    path.write_bytes(text.encode("utf-8"))
    _profile, report = await run_suite(loopback_config, include=["5(r)"], epics=parse_epics(path))
    (result,) = report.results
    assert result.status is Status.FAIL
    assert "maximum length string" in result.defects[0].message


async def test_clause5_without_epics_skips_bibb_items(loopback_config):
    _profile, report = await run_suite(loopback_config, include=["5(*"])
    status = {r.clause: r.status for r in report.results}
    for clause in ("5(a)", "5(b)", "5(c)", "5(d)", "5(e)", "5(f)", "5(j)", "5(p)", "5(r)"):
        assert status[clause] is Status.SKIP, clause
    for clause in ("5(g)", "5(h)", "5(i)", "5(k)", "5(l)", "5(o)", "5(q)"):
        assert status[clause] is Status.PASS, clause
