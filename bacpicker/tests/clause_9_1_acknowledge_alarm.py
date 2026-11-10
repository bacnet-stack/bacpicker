# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.1 AcknowledgeAlarm Service Execution Tests.

Each procedure starts from an alarm the IUT sends to the TD. This tester does not
configure notification recipients or trigger event transitions, so the procedures
are registered and reported as not automated.
"""

from __future__ import annotations

from ._common import register_manual

_ALARM = (
    "the IUT must generate an alarm notification to the TD before AcknowledgeAlarm can be sent"
)
_SERVICE = ["acknowledge-alarm"]

for _clause, _title in (
    ("9.1.1.1", "Successful Alarm Acknowledgment of Confirmed Event Notifications Using the Time "
        "Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.2", "Successful Alarm Acknowledgment of Confirmed Event Notifications using the Sequence "
        "Number Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.3", "Successful Alarm Acknowledgment of Confirmed Event Notifications Using the Date "
        "Time Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.4", "Successful Alarm Acknowledgment of Unconfirmed Event Notifications Using the Time "
        "Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.5", "Successful Alarm Acknowledgment of Unconfirmed Event Notifications Using the "
        "Sequence Number Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.6", "Successful Alarm Acknowledgment of Unconfirmed Event Notifications Using the Date "
        "Time Form of the 'Time of Acknowledgment' Parameter"),
    ("9.1.1.7", 'Successful Alarm Acknowledgment of any "Offnormal" Transitions Using an '
        '"Offnormal" \'To State\''),
    ("9.1.1.8", "Successful Alarm Acknowledgment of Confirmed Event Notifications Using an Unknown "
        "'Acknowledging Process Identifier' Parameter"),
    ("9.1.1.9", "Successful Alarm Acknowledgment of Unconfirmed Event Notifications Using an Unknown "
        "'Acknowledging Process Identifier' Parameter"),
    ("9.1.1.10", "Successful Alarm Re-Acknowledgment of Confirmed Event Notifications"),
    ("9.1.1.11", "Successful Alarm Re-Acknowledgment of Unconfirmed Event Notifications"),
    ("9.1.1.12", "Successful Alarm Acknowledgment of Confirmed Event Notifications when 'To State' "
        "is an Offnormal State other than OFFNORMAL"),
    ("9.1.1.13", "Successful Alarm Acknowledgment of Unconfirmed Event Notifications when 'To State' "
        "is an Offnormal State other than OFFNORMAL"),
    ("9.1.1.14", "Successful Alarm Acknowledgment of Confirmed Event Notifications when 'To State' "
        "is either High-Limit or Low-Limit, Revision 5 and higher only"),
    ("9.1.1.15", "Unsupported Message Text Character Set AcknowledgeAlarm Test"),
    ("9.1.2.1", "Unsuccessful Alarm Acknowledgment of Confirmed Event Notifications Because the"
        "'Time Stamp' is Too Old"),
    ("9.1.2.3", "Unsuccessful Alarm Acknowledgment of Confirmed Event Notifications Because the"
        "'Event Object Identifier' is Invalid"),
    ("9.1.2.4", "Unsuccessful Alarm Acknowledgment of Confirmed Event Notifications Because the"
        "'Event State Acknowledged' is Invalid"),
    ("9.1.2.5", "Unsuccessful Alarm Acknowledgment of Unconfirmed Event Notifications Because the"
        "'Time Stamp' is Too Old"),
    ("9.1.2.6", "Unsuccessful Alarm Acknowledgment of Unconfirmed Event Notifications Because the"
        "'Event Object Identifier' is Invalid"),
    ("9.1.2.7", "Unsuccessful Alarm Acknowledgment of Unconfirmed Event Notifications Because the"
        "'Event State Acknowledged' is Invalid"),
):
    register_manual(_clause, _title, _ALARM, services=_SERVICE)
