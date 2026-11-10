# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.2 ConfirmedCOVNotification Service Execution Tests.

The IUT is the subscriber. The procedures begin with RECEIVE SubscribeCOV from the IUT.
"""

from __future__ import annotations

from ._common import register_manual

_REASON = "the IUT must subscribe to the TD; the tester is not a COV source the IUT is configured to monitor"
_SERVICE = ["confirmed-cov-notification"]

for _clause, _title in (
    ("9.2.1.1", "Change of Value Notifications"),
    ("9.2.1.2", "Change of Value Notification from Loop Objects"),
    ("9.2.1.3", "Change of Value Notification from Pulse Converter Object"),
    ("9.2.1.4", "Change of Value Notification from Load Control Object"),
    ("9.2.1.5", "ConfirmedCOVNotification from Access Door Object"),
    ("9.2.1.6", "ConfirmedCOVNotification from Access Point Object"),
    ("9.2.1.7", "ConfirmedCOVNotification from Credential Data Input Object"),
    ("9.2.2.1", "Change of Value Notification Arrives after Subscription has Expired"),
    ("9.2.2.2", "Change of Value Notifications with Invalid Process Identifier"),
    ("9.2.2.3", "Change of Value Notifications with Invalid Initiating Device Identifier"),
    ("9.2.2.4", "Change of Value Notifications with Invalid Monitored Object Identifier"),
):
    register_manual(_clause, _title, _REASON, services=_SERVICE)
