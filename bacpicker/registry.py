# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Registry of conformance tests, populated by the @conformance_test decorator."""

from __future__ import annotations

import importlib
import pkgutil
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

TestFunc = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class TestCase:
    clause: str
    title: str
    func: TestFunc
    module: str
    services: Tuple[str, ...] = ()
    object_types: Tuple[str, ...] = ()
    writes: bool = False
    depends_on: Tuple[str, ...] = ()
    min_protocol_revision: Optional[int] = None
    manual: Optional[str] = None

    __test__ = False  # keep pytest from collecting this class

    @property
    def sort_key(self) -> Tuple:
        return clause_sort_key(self.clause)


_REGISTRY: Dict[str, TestCase] = {}


def clause_sort_key(clause: str) -> Tuple:
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part)
        for part in re.split(r"[.\-()]", clause)
        if part
    )


def conformance_test(
    clause: str,
    title: str,
    *,
    services: Iterable[str] = (),
    object_types: Iterable[str] = (),
    writes: bool = False,
    depends_on: Iterable[str] = (),
    min_protocol_revision: Optional[int] = None,
    manual: Optional[str] = None,
) -> Callable[[TestFunc], TestFunc]:
    """Register an async test function under a 135.1 clause.

    clause and title must match the 135.1 edition in STANDARD_EDITION.
    services / object_types use the BACnet bit names from
    Protocol_Services_Supported / Protocol_Object_Types_Supported,
    e.g. "read-property-multiple" or "analog-input".
    min_protocol_revision: the procedure only applies if the IUT's
    Protocol_Revision is present and at least this value.
    manual: reason the procedure cannot be automated; it is reported as SKIP.
    """

    def decorator(func: TestFunc) -> TestFunc:
        if clause in _REGISTRY and _REGISTRY[clause].func is not func:
            raise ValueError(f"duplicate conformance test clause {clause!r}")
        _REGISTRY[clause] = TestCase(
            clause=clause,
            title=title,
            func=func,
            module=func.__module__,
            services=tuple(services),
            object_types=tuple(object_types),
            writes=writes,
            depends_on=tuple(depends_on),
            min_protocol_revision=min_protocol_revision,
            manual=manual,
        )
        return func

    return decorator


def discover(package: str = "bacpicker.tests") -> None:
    """Import every module in the test package so their decorators run."""
    pkg = importlib.import_module(package)
    for info in pkgutil.walk_packages(pkg.__path__, prefix=f"{package}."):
        importlib.import_module(info.name)


def all_tests() -> List[TestCase]:
    return sorted(_REGISTRY.values(), key=lambda t: t.sort_key)


def get_test(clause: str) -> TestCase:
    return _REGISTRY[clause]
