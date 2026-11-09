# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.registry import all_tests
from bacpicker.reporting import make_reporters
from bacpicker.result import Status
from bacpicker.runner import Runner


async def run_suite(config, tmp_path=None, include=None, epics=None):
    if include:
        config.include = include
    if tmp_path is not None:
        config.report_formats = ["json", "junit", "markdown", "html"]
        config.output_dir = tmp_path
    app = build_application(config)
    try:
        address, i_am = await discover_iut(app, config)
        profile = await build_profile(app, address, i_am)
        reporters = make_reporters(config.report_formats, config.output_dir)
        runner = Runner(app, profile, config, reporters, {"epics": epics})
        return profile, await runner.run(all_tests())
    finally:
        app.close()


async def test_discovery_and_profile(loopback_config):
    loopback_config.include = ["none"]
    profile, report = await run_suite(loopback_config)
    assert profile.device_instance == 1234
    assert profile.object_name == "simulated-iut"
    assert profile.supports_service("read-property-multiple")
    assert {str(o) for o in profile.object_list} >= {"analog-value,1", "binary-value,1"}
    assert report.results == []


async def test_full_suite_against_simulated_device(loopback_config, tmp_path):
    _profile, report = await run_suite(loopback_config, tmp_path)
    by_clause = {r.clause: r for r in report.results}

    assert len(report.results) == len(all_tests())
    errors = [(r.clause, r.reason) for r in report.results if r.status is Status.ERROR]
    assert not errors, errors

    unexpected = [
        (r.clause, [d.message for d in r.defects])
        for r in report.results
        if r.status is Status.FAIL and r.clause not in KNOWN_SIMULATOR_DEFECTS
    ]
    assert not unexpected, unexpected
    for clause in KNOWN_SIMULATOR_DEFECTS:
        assert by_clause[clause].status is Status.FAIL, f"{clause} no longer fails; update the list"
    for clause in ("9.18.1.1", "9.18.2.3", "9.20.1.1", "9.32.1.1", "9.33.1.1", "9.33.1.3"):
        assert by_clause[clause].status is Status.PASS, by_clause[clause]
    for clause in ("9.18.1.9", "9.32.2.1", "9.33.2.3"):
        assert by_clause[clause].status is Status.SKIP
        assert (by_clause[clause].reason or "").startswith("not automated")

    data = json.loads((tmp_path / "report.json").read_text())
    assert data["summary"]["TOTAL"] == len(report.results)
    suite = ET.parse(tmp_path / "report.junit.xml").getroot().find("testsuite")
    assert suite is not None
    assert suite.get("tests") == str(len(report.results))
    assert "9.18.1.1" in (tmp_path / "report.md").read_text()
    assert "<html>" in (tmp_path / "report.html").read_text()


async def test_write_tests_restore_iut(loopback_config, simulated_iut):
    sim, _address = simulated_iut
    loopback_config.allow_writes = True
    _profile, report = await run_suite(loopback_config, include=["9.32.1.12", "9.32.1.13"])
    assert [r.status for r in report.results] == [Status.PASS, Status.PASS], report.results
    av1 = next(o for o in sim.objectIdentifier.values() if str(o.objectIdentifier) == "analog-value,1")
    assert av1.objectName == "Zone Temperature"


async def test_unsupported_service_probes_need_allow_writes(loopback_config):
    loopback_config.allow_writes = True
    _profile, report = await run_suite(loopback_config, include=["9.39.1", "9.39.2"])
    by_clause = {r.clause: r for r in report.results}
    # the simulator's handlers run for services its Protocol_Services_Supported clears
    assert by_clause["9.39.1"].status is Status.FAIL, by_clause["9.39.1"]
    assert by_clause["9.39.2"].status is Status.PASS, by_clause["9.39.2"]


async def test_detects_defect(loopback_config, simulated_iut):
    sim, _address = simulated_iut
    # make the simulator answer a Who-Is that excludes it
    original = sim.do_WhoIsRequest

    async def respond_always(apdu):
        apdu.deviceInstanceRangeLowLimit = None
        apdu.deviceInstanceRangeHighLimit = None
        await original(apdu)

    sim.do_WhoIsRequest = respond_always
    _profile, report = await run_suite(loopback_config, include=["9.33.1.3"])
    (result,) = report.results
    assert result.status is Status.FAIL
    assert result.defects[0].clause == "9.33.1.3"
    assert "excludes" in result.defects[0].message


# defects in the bacpypes3 simulator itself, which the tester correctly reports
KNOWN_SIMULATOR_DEFECTS = {
    "5(n)": "Property_List includes Object_Identifier, Object_Name, Object_Type and Property_List",
    "9.18.1.3": "no support for the Device 4194303 wildcard instance",
    "9.18.1.6": "aborts with APDU_TOO_LONG instead of BUFFER_OVERFLOW",
    "9.18.1.8": "no support for the Network Port 4194303 wildcard instance",
    "9.20.1.8": "Network Port Link_Speed (optional in 135-2024) is not returned for OPTIONAL",
    "9.20.1.9": "Network Port Link_Speed (optional in 135-2024) is returned for REQUIRED",
    "9.20.1.11": "no support for the Device 4194303 wildcard instance",
    "9.20.1.14": "no support for the Network Port 4194303 wildcard instance",
    "9.22.2.6": "WriteProperty of an unknown property returns DEVICE / OPERATIONAL_PROBLEM",
    "9.22.2.7": "accepts WriteProperty of read-only Object_Type",
}
