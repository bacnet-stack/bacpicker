# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from test_end_to_end import run_suite

from bacpicker.database import read_database
from bacpicker.epics import parse_epics, write_epics
from bacpicker.iut import build_application, build_profile, discover_iut
from bacpicker.result import Status


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
        text = text.replace(f"\r\n-- {bibb} ", f"\r\n{bibb} ", 1)
    path.write_bytes(text.encode("utf-8"))


async def test_generated_epics_round_trip(loopback_config, tmp_path):
    path = tmp_path / "iut.tpi"
    await generate(loopback_config, path)
    assert path.read_bytes().startswith(b"PICS 0\r\nBACnet Protocol Implementation Conformance Statement\r\n")

    epics = parse_epics(path)
    assert epics.bibbs == ["DS-RP-B"]
    assert epics.general["vendor name"] == "BACpypes"
    assert epics.services["read-property"] == {"execute"}
    assert epics.services["i-am"] == {"initiate"}
    assert set(epics.object_types) == {"device", "network-port", "analog-value", "binary-value"}
    assert epics.fail_times["unconfirmed response fail time"] == 0.5
    assert {o.object_identifier for o in epics.objects} >= {"(device, 1234)", "(analog-value, 1)"}
    av1 = next(o for o in epics.objects if o.object_identifier == "(analog-value, 1)")
    assert av1.properties["object-name"].value == '"Zone Temperature"'
    assert not epics.unknown

    uncomment(path, "DM-DDB-B")
    assert parse_epics(path).bibbs == ["DM-DDB-B", "DS-RP-B"]


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
