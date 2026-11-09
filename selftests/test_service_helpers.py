# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

import pytest
from bacpypes3.basetypes import BinaryPV, EventState, PriorityValue
from bacpypes3.pdu import Address
from bacpypes3.primitivedata import Boolean, Null, ObjectIdentifier, Real, Unsigned

from bacpicker.assertions import SkipTest
from bacpicker.config import RunConfig
from bacpicker.context import DeviceProfile
from bacpicker.tests import clause_9_11_subscribe_cov_property as cov_property
from bacpicker.tests import clause_9_16_create_object as create_object
from bacpicker.tests import clause_9_31_utc_time_synchronization as utc_sync
from bacpicker.tests._common import (
    all_objects,
    different_value,
    priority_slot_value,
    restore_priority_slot,
)


def make_profile(**kwargs):
    return DeviceProfile(
        address=Address("192.0.2.1"),
        device_id=ObjectIdentifier("device,7"),
        vendor_id=999,
        max_apdu_length_accepted=1476,
        segmentation_supported="no-segmentation",
        **kwargs,
    )


def test_different_value_handles_enumerations_before_integers():
    assert different_value(BinaryPV("active")) == "inactive"
    assert different_value(BinaryPV("inactive")) == "active"
    assert different_value(EventState("offnormal")) is None
    assert different_value(Boolean(True)) is False
    assert different_value(Unsigned(4)) == 5
    assert different_value(Real(1.5)) == 2.5


def test_priority_slot_is_restored_to_its_original_value():
    av = ObjectIdentifier("analog-value,1")
    empty = restore_priority_slot(av, PriorityValue(null=()))
    assert isinstance(empty.previous, Null) and empty.priority == 16
    assert restore_priority_slot(av, PriorityValue(real=21.5)).previous == 21.5
    assert priority_slot_value(PriorityValue(real=21.5)) == 21.5
    commanded = restore_priority_slot(av, PriorityValue(enumerated=1))
    assert commanded.previous == 1 and type(commanded.previous) is int


def test_utc_restore_converts_local_time_back_to_utc():
    local = datetime.datetime(2026, 11, 9, 23, 30)
    # UTC_Offset is positive west of Greenwich: UTC = local standard time + offset
    utc = utc_sync._bacnet_utc(local, 360, dst=False)
    assert tuple(utc.date) == (126, 11, 10, 2) and tuple(utc.time)[:2] == (5, 30)
    utc = utc_sync._bacnet_utc(local, 360, dst=True)
    assert tuple(utc.time)[:2] == (4, 30)
    assert utc_sync._local((126, 11, 9, 1), (23, 30, 0, 255)) == local
    assert utc_sync._local((255, 11, 9, 255), (23, 30, 0, 0)) is None


def _ctx(max_objects=50, **profile) -> Any:
    return SimpleNamespace(iut=make_profile(**profile), config=RunConfig(max_objects=max_objects),
        skip=lambda reason: (_ for _ in ()).throw(SkipTest(reason)))


def test_device_wide_summaries_need_every_object():
    objects = [ObjectIdentifier(f"analog-value,{i}") for i in range(3)]
    assert len(all_objects(_ctx(max_objects=4, object_list=objects))) == 4
    with pytest.raises(SkipTest):
        all_objects(_ctx(max_objects=3, object_list=objects))


def test_create_object_uses_a_type_the_iut_reports_unsupported():
    ctx = _ctx(object_types_supported={"analog-input", "device"}, object_types_supported_length=64)
    assert create_object._unsupported_type(ctx) == "analog-output"
    with pytest.raises(SkipTest):
        create_object._unsupported_type(_ctx())


def test_subscribe_cov_property_encodes_the_monitored_property():
    ctx: Any = SimpleNamespace(iut=make_profile())
    request = cov_property._request(ctx, ObjectIdentifier("analog-value,1"), "present-value")
    # 'Monitored Property' [4] BACnetPropertyReference { propertyIdentifier [0] present-value (85) }
    assert request.encode().pduData.endswith(bytes.fromhex("4e09554f"))
