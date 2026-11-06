# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures: a simulated BACnet/IP device (bacpypes3) on the loopback interface."""

from __future__ import annotations

import argparse
import socket

import pytest
from bacpypes3.app import Application
from bacpypes3.basetypes import ServicesSupported
from bacpypes3.local.analog import AnalogValueObject
from bacpypes3.local.binary import BinaryValueObject

from bacpicker.config import RunConfig
from bacpicker.registry import discover

IUT_INSTANCE = 1234
SIM_SERVICES = (
    "read-property", "write-property", "read-property-multiple", "who-has", "who-is", "i-am", "i-have",
)


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_simulated_device(port: int, instance: int = IUT_INSTANCE) -> Application:
    args = argparse.Namespace(
        name="simulated-iut",
        instance=instance,
        network=None,
        address=f"127.0.0.1/8:{port}",
        vendoridentifier=999,
        foreign=None,
        ttl=30,
        bbmd=None,
    )
    app = Application.from_args(args)
    bits = [0] * len(ServicesSupported._bitstring_names)
    for name in SIM_SERVICES:
        bits[ServicesSupported._bitstring_names[name]] = 1
    # bacpypes3 derives this property from the application and ignores the setter
    app.get_services_supported = lambda: ServicesSupported(bits)
    app.add_object(
        AnalogValueObject(
            objectIdentifier="analog-value,1",
            objectName="Zone Temperature",
            presentValue=21.5,
            statusFlags=[0, 0, 0, 0],
            eventState="normal",
            outOfService=False,
            units="degrees-celsius",
        )
    )
    app.add_object(
        BinaryValueObject(
            objectIdentifier="binary-value,1",
            objectName="Fan Enable",
            presentValue="inactive",
            statusFlags=[0, 0, 0, 0],
            eventState="normal",
            outOfService=False,
        )
    )
    return app


@pytest.fixture(scope="session", autouse=True)
def _register_tests():
    discover()


@pytest.fixture
async def simulated_iut():
    port = free_udp_port()
    app = make_simulated_device(port)
    yield app, f"127.0.0.1:{port}"
    app.close()


@pytest.fixture
def loopback_config(simulated_iut) -> RunConfig:
    _app, address = simulated_iut
    return RunConfig(
        local_address=f"127.0.0.1/8:{free_udp_port()}",
        device_instance=IUT_INSTANCE,
        target_address=address,
        unicast=True,
        unconfirmed_response_fail_time=0.5,
        internal_processing_fail_time=0.5,
        test_timeout=30,
        report_formats=[],
    )
