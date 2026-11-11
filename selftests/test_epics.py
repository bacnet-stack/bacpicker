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
from bacpicker.database import ObjectRecord, PropertyRecord, TestDatabase, read_database, read_object
from bacpicker.epics import parse_epics, write_epics
from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.registry import get_test
from bacpicker.result import Status
from bacpicker.runner import Runner
from bacpicker.standard import object_spec, property_identifiers


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


def _device(database, profile, **properties):
    record = ObjectRecord(objid=profile.device_id, object_type="device", source="rpm-all")
    for name, value in properties.items():
        record.properties[name] = PropertyRecord(name=name, identifier=0, value=value)
    database.objects[profile.device_id] = record
    return record


def _object(database, object_type, instance=1):
    objid = ObjectIdentifier(f"{object_type},{instance}")
    database.objects[objid] = ObjectRecord(objid=objid, object_type=object_type, source="rpm-all")
    return objid


def _drop_service_lines(path, *services):
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line not in services]
    path.write_bytes(("\r\n".join(kept) + "\r\n").encode("utf-8"))


async def _run_5d(profile, path, database):
    return await Runner(
        None,
        profile,
        RunConfig(),
        shared={"epics": parse_epics(path), "database": database},
    ).run_one(get_test("5(d)"), {})


def test_subscribe_cov_infers_notification_initiate(tmp_path):
    path = tmp_path / "cov.tpi"
    profile = make_profile(services_supported={"read-property", "subscribe-cov"})
    write_epics(path, profile, TestDatabase(), RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "ConfirmedCOVNotification Initiate" in lines
    assert "UnconfirmedCOVNotification Initiate" in lines
    assert any(line.startswith("DS-COV-B ") for line in lines)


async def test_clause_5d_infers_cov_initiate_missing_from_epics(tmp_path):
    path = tmp_path / "cov.tpi"
    profile = make_profile(services_supported={"read-property", "subscribe-cov"})
    database = TestDatabase()
    write_epics(path, profile, database, RunConfig())
    _drop_service_lines(path, "ConfirmedCOVNotification Initiate", "UnconfirmedCOVNotification Initiate")
    result = await _run_5d(profile, path, database)
    assert result.status is Status.PASS, [d.message for d in result.defects]
    assert any("DS-COV-B" in step and "SubscribeCOV" in step for step in result.steps)


async def test_clause_5d_fails_cov_initiate_without_subscribe_cov(tmp_path):
    path = tmp_path / "cov.tpi"
    # The file lists SubscribeCOV Execute and DS-COV-B, but the device does not execute it,
    # so the Initiate roles are not inferred.
    profile = make_profile(services_supported={"read-property", "subscribe-cov"})
    write_epics(path, profile, TestDatabase(), RunConfig())
    _drop_service_lines(path, "ConfirmedCOVNotification Initiate", "UnconfirmedCOVNotification Initiate")
    checked = make_profile(services_supported={"read-property"})
    result = await _run_5d(checked, path, TestDatabase())
    assert result.status is Status.FAIL
    assert any("ConfirmedCOVNotification" in defect.message for defect in result.defects)


async def test_clause_5d_infers_event_notification_from_notification_class(tmp_path):
    path = tmp_path / "event.tpi"
    profile = make_profile(services_supported={"read-property"})
    database = TestDatabase()
    _object(database, "notification-class")
    write_epics(path, profile, database, RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("AE-N-I-B ") for line in lines)
    assert "UnconfirmedEventNotification Initiate" in lines
    assert "ConfirmedEventNotification Initiate" not in lines
    _drop_service_lines(path, "UnconfirmedEventNotification Initiate")
    result = await _run_5d(profile, path, database)
    assert result.status is Status.PASS, [d.message for d in result.defects]
    assert any("AE-N-I-B" in step for step in result.steps)


async def test_clause_5d_infers_vt_initiate(tmp_path):
    path = tmp_path / "vt.tpi"
    profile = make_profile(services_supported={"read-property", "vt-open", "vt-close", "vt-data"})
    database = TestDatabase()
    write_epics(path, profile, database, RunConfig())
    text = path.read_text(encoding="utf-8")
    text = text.replace("VT-Close Initiate Execute", "VT-Close Execute")
    text = text.replace("VT-Data Initiate Execute", "VT-Data Execute")
    path.write_bytes(text.encode("utf-8"))
    result = await _run_5d(profile, path, database)
    assert result.status is Status.PASS, [d.message for d in result.defects]
    assert any("DM-VT-B" in step for step in result.steps)


def _possible(acronym, evidence):
    return f"-- {acronym:<16}-- possible inclusion: {evidence}"


def test_time_sync_properties_are_a_possible_inclusion(tmp_path):
    profile = make_profile(services_supported={"read-property", "time-synchronization"})

    local = tmp_path / "local.tpi"
    local_db = TestDatabase()
    _device(local_db, profile, **{"time-synchronization-recipients": []})
    write_epics(local, profile, local_db, RunConfig())
    local_text = local.read_text(encoding="utf-8")
    assert _possible("DM-TS-A", "time-synchronization-recipients") in local_text
    assert "TimeSynchronization Initiate Execute" in local_text
    assert "UTCTimeSynchronization" not in local_text
    assert "-- DM-UTC-A" in local_text.splitlines()
    assert "-- DM-ATS-A" in local_text.splitlines()

    utc = tmp_path / "utc.tpi"
    utc_db = TestDatabase()
    _device(utc_db, profile, **{"utc-time-synchronization-recipients": []})
    write_epics(utc, profile, utc_db, RunConfig())
    utc_lines = utc.read_text(encoding="utf-8").splitlines()
    assert _possible("DM-UTC-A", "utc-time-synchronization-recipients") in "\n".join(utc_lines)
    assert "UTCTimeSynchronization Initiate" in utc_lines
    assert "TimeSynchronization Execute" in utc_lines
    assert "TimeSynchronization Initiate Execute" not in utc_lines
    assert "-- DM-TS-A" in utc_lines
    assert "-- DM-ATS-A" in utc_lines

    both = tmp_path / "both.tpi"
    both_db = TestDatabase()
    _device(
        both_db,
        profile,
        **{
            "time-synchronization-interval": 0,
            "time-synchronization-recipients": [],
            "utc-time-synchronization-recipients": [],
        },
    )
    write_epics(both, profile, both_db, RunConfig())
    both_text = both.read_text(encoding="utf-8")
    assert _possible("DM-TS-A", "time-synchronization-recipients") in both_text
    assert _possible("DM-UTC-A", "utc-time-synchronization-recipients") in both_text
    assert _possible("DM-ATS-A", "time-synchronization-interval and both recipient lists") in both_text
    assert "TimeSynchronization Initiate Execute" in both_text
    assert "UTCTimeSynchronization Initiate" in both_text
    claimed = parse_epics(both).bibbs
    assert "DM-ATS-A" not in claimed and "DM-TS-A" not in claimed and "DM-UTC-A" not in claimed

    only_interval = tmp_path / "interval.tpi"
    interval_db = TestDatabase()
    _device(interval_db, profile, **{"time-synchronization-interval": 30})
    write_epics(only_interval, profile, interval_db, RunConfig())
    interval_lines = only_interval.read_text(encoding="utf-8").splitlines()
    assert "-- DM-ATS-A" in interval_lines
    assert "-- DM-TS-A" in interval_lines
    assert "-- DM-UTC-A" in interval_lines
    assert "UTCTimeSynchronization" not in interval_lines


def test_restart_recipients_uncomment_dm_r_b(tmp_path):
    path = tmp_path / "restart.tpi"
    profile = make_profile(services_supported={"read-property"})
    database = TestDatabase()
    _device(database, profile, **{"restart-notification-recipients": []})
    write_epics(path, profile, database, RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("DM-R-B ") for line in lines)
    assert "UnconfirmedCOVNotification Initiate" in lines
    assert "DM-R-B" in parse_epics(path).bibbs
    assert "-- DS-COVU-B" in lines


def test_proxy_bibbs_stay_commented_without_proxy_properties(tmp_path):
    path = tmp_path / "proxy.tpi"
    profile = make_profile(
        services_supported={
            "add-list-element",
            "read-property",
            "read-range",
            "remove-list-element",
            "who-is",
            "write-property",
        }
    )
    write_epics(path, profile, TestDatabase(), RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert "-- DM-SP-B" in lines
    assert "-- DM-DAP-B" in lines
    assert not any(line.startswith("DM-SP-B ") or line.startswith("DM-DAP-B ") for line in lines)
    assert "ReadProperty Execute" in lines
    assert "ReadProperty Initiate" not in lines


def test_device_address_proxy_table_suggests_dm_dap_b(tmp_path):
    assert property_identifiers()[4194339] == "device-address-proxy-table"
    path = tmp_path / "dap.tpi"
    profile = make_profile(
        services_supported={
            "add-list-element",
            "read-property",
            "read-range",
            "remove-list-element",
            "who-is",
            "write-property",
        }
    )
    database = TestDatabase()
    _device(database, profile, **{"device-address-proxy-table": []})
    write_epics(path, profile, database, RunConfig())
    lines = path.read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("DM-DAP-B ") for line in lines)
    assert "ReadProperty Initiate Execute" in lines
    assert "-- DM-SP-B" in lines
    device = object_spec("device")
    assert device is not None
    proxy_table = device.get("device-address-proxy-table")
    assert proxy_table is not None and proxy_table.writable is False
    port = object_spec("network-port")
    assert port is not None
    proxy_enable = port.get("device-address-proxy-enable")
    proxy_timeout = port.get("device-address-proxy-timeout")
    assert proxy_enable is not None and proxy_enable.writable is True
    assert proxy_timeout is not None and proxy_timeout.maximum == 300
    lighting = object_spec("lighting-output")
    assert lighting is not None
    last_on = lighting.get("last-on-value")
    default_on = lighting.get("default-on-value")
    assert last_on is not None and last_on.writable is False
    assert default_on is not None and default_on.optional is False and default_on.minimum == 1


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
    # FAIL is expected: the fixture's generated Property_List lists excluded properties
    assert result.status in (Status.PASS, Status.FAIL), (result.status, result.reason)
    messages = [d.message for d in result.defects]
    assert not any("861" in m and "Property_List is missing" in m for m in messages), messages


class ConformingPropertyListObject(LocalObject):
    """Its Property_List excludes the identity properties and itself, as 135 requires.

    Derived from LocalObject, not ProprietaryObject: bacpypes3 registers a subclass of a class
    in this module under the simulator's vendor, which would give the tester a class for 861.
    """

    objectType = ObjectType(861)
    notificationClass = None
    _elements = {
        "objectIdentifier": ObjectIdentifier,
        "objectName": CharacterString,
        "objectType": ObjectType,
        "description": CharacterString,
        "propertyList": ArrayOf(PropertyIdentifier),
    }

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
