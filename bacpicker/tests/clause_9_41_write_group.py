# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.41 WriteGroup Tests.

WriteGroup changes channel members by group number. The tester does not know which
groups are configured or how to observe each member, so the procedures are registered
and reported as not automated.
"""

from __future__ import annotations

from ._common import register_manual

_REASON = "requires Channel objects configured in a known group whose member values the tester can observe"
_SERVICE = ["write-group"]

for _clause, _title in (
    ("9.41.1.1", "Channel and Group Number Test"),
    ("9.41.1.2", "Write Priority and Overriding Priority Test"),
    ("9.41.1.3", "Relinquish Control Test"),
    ("9.41.1.4", "Inhibit Delay Test with WriteGroup"),
):
    register_manual(_clause, _title, _REASON, services=_SERVICE)
