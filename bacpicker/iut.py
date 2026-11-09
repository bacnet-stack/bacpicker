# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Tester application, IUT discovery and capability profiling."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
from typing import Any, Callable, List, Optional, Tuple

from bacpypes3.apdu import APDU, ErrorRejectAbortNack, IAmRequest, ReadPropertyRequest
from bacpypes3.app import Application
from bacpypes3.ipv4 import IPv4DatagramProtocol
from bacpypes3.ipv4.link import NormalLinkLayer
from bacpypes3.pdu import Address, GlobalBroadcast, LocalBroadcast
from bacpypes3.primitivedata import BitString

from .config import RunConfig
from .context import DeviceProfile
from .standard import object_type_bits, service_bits

log = logging.getLogger(__name__)

BACNET_PORT = 0xBAC0  # destination port for broadcasts
DEFAULT_LOCAL_PORT = 0xBACF  # lets the tester run beside a device that owns 0xBAC0


class DiscoveryError(Exception):
    pass


class TesterApplication(Application):
    """Application that also lets tests observe every incoming request (e.g. I-Am, I-Have)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._listeners: List[Callable[[APDU], None]] = []
        self._extra_transports: List[asyncio.BaseTransport] = []
        self.broadcast_port_redirected = False

    def close(self) -> None:
        for transport in self._extra_transports:
            transport.close()
        super().close()

    async def listen_for_broadcasts(self) -> None:
        """Also receive broadcasts sent to BACNET_PORT; skipped with a warning if another process owns it."""
        loop = asyncio.get_running_loop()
        if not self.broadcast_port_redirected:
            return
        for server in self.broadcast_servers():

            def factory(server: Any = server) -> IPv4DatagramProtocol:
                protocol = IPv4DatagramProtocol()
                protocol.server = server
                return protocol

            local_addr, reuse_port = broadcast_listen_address(server)
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    factory, local_addr=local_addr, allow_broadcast=True, reuse_port=reuse_port
                )
            except OSError as err:
                log.warning(
                    "cannot listen for broadcasts on %s:%d (%s); broadcast replies from the IUT will "
                    "not be seen, use --target or --bbmd", *local_addr, err,
                )
                continue
            protocol.destination = LocalBroadcast()
            self._extra_transports.append(transport)

    def broadcast_servers(self) -> List[Any]:
        # a foreign device gets broadcasts forwarded by its BBMD
        return [
            ll.server for ll in self.link_layers.values()
            if isinstance(ll, NormalLinkLayer) and ll.server.broadcast_address is not None
        ]

    def add_listener(self, fn: Callable[[APDU], None]) -> None:
        self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[APDU], None]) -> None:
        self._listeners.remove(fn)

    async def indication(self, apdu: APDU) -> None:
        for fn in list(self._listeners):
            try:
                fn(apdu)
            except Exception:
                log.exception("listener failed")
        await super().indication(apdu)


def broadcast_listen_address(server: Any, windows: Optional[bool] = None) -> Tuple[Tuple[str, int], bool]:
    """Return the bind address and reuse_port flag for the extra broadcast listener.

    Windows has no SO_REUSEPORT and cannot bind a broadcast address; like BACpypes3, it binds the
    unicast address, which also receives broadcasts sent to that port.
    """
    if windows is None:
        windows = os.name == "nt"
    if windows:
        return (server.local_address[0], server.broadcast_address[1]), False
    return server.broadcast_address, True


def build_application(config: RunConfig) -> TesterApplication:
    address = config.local_address or "host"
    default_port = not re.search(r":\d+$", address)
    if default_port:
        address += f":{DEFAULT_LOCAL_PORT}"
    args = argparse.Namespace(
        name="bacpicker-tester",
        instance=config.tester_instance,
        network=None,
        address=address,
        vendoridentifier=999,
        foreign=config.bbmd,
        ttl=config.bbmd_ttl,
        bbmd=None,
    )
    app = TesterApplication.from_args(args)
    if default_port:
        app.broadcast_port_redirected = True
        for server in app.broadcast_servers():
            server.broadcast_address = (server.broadcast_address[0], BACNET_PORT)
    # the TD accepts the largest BACnet/IP APDU so responses are never limited by the tester
    app.device_object.maxApduLengthAccepted = 1476
    app.device_object.maxSegmentsAccepted = 64
    return app


async def discover_iut(app: Application, config: RunConfig) -> Tuple[Address, IAmRequest]:
    """Locate the IUT with Who-Is and return its address and I-Am."""
    destination = Address(config.target_address) if config.target_address else GlobalBroadcast()
    timeout = max(1, int(round(config.unconfirmed_response_fail_time)))
    instance = config.device_instance
    if instance is not None:
        i_ams = await app.who_is(instance, instance, destination, timeout=timeout)
    else:
        i_ams = await app.who_is(address=destination, timeout=timeout)

    if config.target_address:
        target = Address(config.target_address)
        i_ams = [i for i in i_ams if i.pduSource == target] or i_ams

    if not i_ams:
        where = config.target_address or "global broadcast"
        which = f"device {instance}" if instance is not None else "any device"
        raise DiscoveryError(f"no I-Am received from {which} via {where}")
    if len(i_ams) > 1:
        found = ", ".join(f"{i.iAmDeviceIdentifier[1]}@{i.pduSource}" for i in i_ams)
        raise DiscoveryError(
            f"multiple devices responded ({found}); select one with --device-instance"
        )
    i_am = i_ams[0]
    return i_am.pduSource, i_am


def _bit_names(bits: Any, names: dict) -> set:
    values = list(bits)
    return {name for name, bit in names.items() if bit < len(values) and values[bit]}


async def _read_bitstring(
    app: Application, address: Address, device_id: Any, prop: str, profile: DeviceProfile
) -> Optional[List[int]]:
    """Read a bitstring property keeping its encoded length (the typed decode pads it)."""
    request = ReadPropertyRequest(
        objectIdentifier=device_id, propertyIdentifier=prop, destination=address
    )
    try:
        ack = await app.request(request)
    except ErrorRejectAbortNack as err:
        profile.warnings.append(f"Device {prop} could not be read: {err}")
        return None
    return list(ack.propertyValue.cast_out(BitString))


async def _read_object_list(app: Application, address: Address, device_id: Any) -> list:
    try:
        return list(await app.read_property(address, device_id, "object-list"))
    except ErrorRejectAbortNack as err:
        log.info("Object_List read failed (%s); reading element by element", err)
    count = await app.read_property(address, device_id, "object-list", 0)
    return [
        await app.read_property(address, device_id, "object-list", index)
        for index in range(1, int(count) + 1)
    ]


async def build_profile(app: Application, address: Address, i_am: IAmRequest) -> DeviceProfile:
    device_id = i_am.iAmDeviceIdentifier
    profile = DeviceProfile(
        address=address,
        device_id=device_id,
        vendor_id=int(i_am.vendorID),
        max_apdu_length_accepted=int(i_am.maxAPDULengthAccepted),
        segmentation_supported=str(i_am.segmentationSupported),
    )

    async def read(prop: str) -> Optional[Any]:
        try:
            return await app.read_property(address, device_id, prop)
        except ErrorRejectAbortNack as err:
            profile.warnings.append(f"Device {prop} could not be read: {err}")
            return None

    for prop, attr, conv in (
        ("object-name", "object_name", str),
        ("vendor-name", "vendor_name", str),
        ("model-name", "model_name", str),
        ("firmware-revision", "firmware_revision", str),
        ("application-software-version", "application_software_version", str),
        ("protocol-version", "protocol_version", int),
        ("protocol-revision", "protocol_revision", int),
    ):
        value = await read(prop)
        if value is not None:
            setattr(profile, attr, conv(value))

    for prop, names, attr in (
        ("protocol-services-supported", service_bits(), "services"),
        ("protocol-object-types-supported", object_type_bits(), "object_types"),
    ):
        bits = await _read_bitstring(app, address, device_id, prop, profile)
        if bits is not None:
            setattr(profile, f"{attr}_supported", _bit_names(bits, names))
            setattr(profile, f"{attr}_supported_length", len(bits))

    try:
        profile.object_list = await _read_object_list(app, address, device_id)
    except ErrorRejectAbortNack as err:
        profile.warnings.append(f"Device object-list could not be read: {err}")

    return profile
