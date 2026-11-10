# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
from unittest.mock import AsyncMock, Mock

import pytest
from bacpypes3.apdu import IAmRequest
from bacpypes3.app import Application
from bacpypes3.pdu import Address, GlobalBroadcast
from conftest import free_udp_port

from bacpicker import cli
from bacpicker.config import RunConfig


def i_am(instance, address):
    return IAmRequest(
        iAmDeviceIdentifier=("device", instance),
        maxAPDULengthAccepted=1476,
        segmentationSupported="no-segmentation",
        vendorID=999,
        source=Address(address),
    )


@pytest.mark.parametrize("bbmd", [None, "192.0.2.10:47808"])
def test_list_devices_command(monkeypatch, capsys, tmp_path, bbmd):
    app = Mock()
    app.listen_for_broadcasts = AsyncMock()
    app.who_is = AsyncMock(return_value=[
        i_am(200, "192.0.2.20"), i_am(100, "192.0.2.30"), i_am(100, "192.0.2.10"),
    ])
    build = Mock(return_value=app)
    monkeypatch.setattr(cli, "build_application", build)
    run = AsyncMock()
    monkeypatch.setattr(cli, "run", run)
    profile = AsyncMock()
    monkeypatch.setattr(cli, "build_profile", profile)
    reports = Mock()
    monkeypatch.setattr(cli, "make_reporters", reports)
    argv = [
        "--list-devices", "-a", "192.0.2.1/24:47809", "--tester-instance", "42",
        "-d", "200", "-t", "192.0.2.20", "--unicast",
        "--unconfirmed-response-fail-time", "5", "--bbmd-ttl", "60",
        "--generate-epics", str(tmp_path / "device.tpi"),
        "-r", "json", "-o", str(tmp_path / "reports"),
    ]
    if bbmd:
        argv += ["--bbmd", bbmd]
    assert cli.main(argv) == 0
    config = build.call_args.args[0]
    assert config.local_address == "192.0.2.1/24:47809"
    assert config.tester_instance == 42
    assert config.bbmd == bbmd
    assert config.bbmd_ttl == 60
    app.listen_for_broadcasts.assert_awaited_once_with()
    app.who_is.assert_awaited_once()
    assert app.who_is.call_args.args == ()
    assert isinstance(app.who_is.call_args.kwargs["address"], GlobalBroadcast)
    assert app.who_is.call_args.kwargs["timeout"] == 5
    app.close.assert_called_once_with()
    run.assert_not_called()
    profile.assert_not_called()
    reports.assert_not_called()
    assert not list(tmp_path.iterdir())
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["Instance", "Address", "Vendor", "ID", "Max", "APDU", "Segmentation"]
    assert [line.split() for line in lines[1:]] == [
        ["100", "192.0.2.10", "999", "1476", "no-segmentation"],
        ["100", "192.0.2.30", "999", "1476", "no-segmentation"],
        ["200", "192.0.2.20", "999", "1476", "no-segmentation"],
    ]


async def test_list_devices_empty(monkeypatch, capsys):
    app = Mock()
    app.listen_for_broadcasts = AsyncMock()
    app.who_is = AsyncMock(return_value=[])
    monkeypatch.setattr(cli, "build_application", Mock(return_value=app))
    assert await cli.list_devices(RunConfig()) == 0
    assert app.who_is.call_args.kwargs["timeout"] == 3
    assert capsys.readouterr().out == "No devices discovered.\n"
    app.close.assert_called_once_with()


@pytest.mark.parametrize("stage", ["listen_for_broadcasts", "who_is"])
async def test_list_devices_closes_on_error(monkeypatch, stage):
    app = Mock()
    app.listen_for_broadcasts = AsyncMock()
    app.who_is = AsyncMock()
    getattr(app, stage).side_effect = OSError("network unavailable")
    monkeypatch.setattr(cli, "build_application", Mock(return_value=app))
    with pytest.raises(OSError, match="network unavailable"):
        await cli.list_devices(RunConfig())
    app.close.assert_called_once_with()


async def test_list_devices_through_bbmd(capsys):
    port = free_udp_port()
    bbmd = Application.from_args(argparse.Namespace(
        name="simulated-bbmd",
        instance=1234,
        network=None,
        address=f"127.0.0.1/8:{port}",
        vendoridentifier=999,
        foreign=None,
        ttl=30,
        bbmd=[],
    ))
    config = RunConfig(
        local_address=f"127.0.0.1/8:{free_udp_port()}",
        bbmd=f"127.0.0.1:{port}",
        unconfirmed_response_fail_time=1,
        device_instance=5678,
        target_address="192.0.2.1",
        unicast=True,
    )
    try:
        assert await cli.list_devices(config) == 0
    finally:
        bbmd.close()
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[1].split()[:3] == ["1234", f"127.0.0.1:{port}", "999"]
