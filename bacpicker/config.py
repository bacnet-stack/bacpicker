# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Run configuration shared by the CLI, runner and tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunConfig:
    # local BACnet/IP binding, e.g. "192.168.1.10/24" or "192.168.1.10/24:47809"; None = "host"
    local_address: Optional[str] = None
    # tester's own device instance; must not collide with the IUT
    tester_instance: int = 4194301
    # IUT selection
    device_instance: Optional[int] = None
    target_address: Optional[str] = None
    # send Who-Is / Who-Has directly to the IUT address instead of broadcasting
    unicast: bool = False
    bbmd: Optional[str] = None
    bbmd_ttl: int = 300
    # 135.1 timers (EPICS "Fail Times"), seconds
    unconfirmed_response_fail_time: float = 3.0
    internal_processing_fail_time: float = 3.0
    # per-test timeout, seconds
    test_timeout: float = 120.0
    # cap on objects visited by tests that iterate the Object_List
    max_objects: int = 50
    allow_writes: bool = False
    # EPICS with the user-declared sections (BIBBs, Initiate support, W/C marks, Fail Times)
    epics_path: Optional[Path] = None
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)
    report_formats: List[str] = field(default_factory=lambda: ["console"])
    output_dir: Path = Path("reports")
    verbose: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["output_dir"] = str(self.output_dir)
        data["epics_path"] = str(self.epics_path) if self.epics_path else None
        return data
