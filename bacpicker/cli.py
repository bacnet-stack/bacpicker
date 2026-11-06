# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Command-line entry point: discover the IUT, run applicable 135.1 tests, write reports."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import STANDARD_EDITION, __version__
from .config import RunConfig
from .database import read_database
from .epics import Epics, parse_epics, write_epics
from .iut import DiscoveryError, build_application, build_profile, discover_iut
from .registry import all_tests, discover
from .reporting import FORMATS, make_reporters
from .runner import Runner, filter_tests, order_tests


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="bacpicker",
        description=f"BACnet/IP conformance tester based on {STANDARD_EDITION}",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    net = p.add_argument_group("network")
    net.add_argument(
        "-a", "--address", help="local BACnet/IP address, e.g. 192.168.1.10/24 or 192.168.1.10/24:47809"
    )
    net.add_argument("--tester-instance", type=int, default=4194301, help="tester's device instance")
    net.add_argument("--bbmd", help="register as a foreign device with this BBMD (host[:port])")
    net.add_argument("--bbmd-ttl", type=int, default=300, help="foreign device registration TTL")

    iut = p.add_argument_group("implementation under test")
    iut.add_argument("-d", "--device-instance", type=int, help="IUT device instance")
    iut.add_argument("-t", "--target", help="IUT address (sends Who-Is directly to it)")
    iut.add_argument(
        "--unicast",
        action="store_true",
        help="send Who-Is/Who-Has to the IUT address instead of broadcasting (requires --target)",
    )

    run = p.add_argument_group("test selection")
    run.add_argument("-i", "--include", action="append", default=[], metavar="CLAUSE",
                     help="run only matching clauses, e.g. '9.18.*' (repeatable)")
    run.add_argument("-x", "--exclude", action="append", default=[], metavar="CLAUSE",
                     help="skip matching clauses (repeatable)")
    run.add_argument("--allow-writes", action="store_true", help="enable tests that modify the IUT")
    run.add_argument("--epics", type=Path, metavar="FILE",
                     help="EPICS with the BIBBs Supported section filled in (see --generate-epics)")
    run.add_argument("--generate-epics", type=Path, metavar="FILE",
                     help="read the IUT's objects, write an EPICS with optional BIBBs commented out, "
                          "and exit")
    run.add_argument("--unconfirmed-response-fail-time", type=float, metavar="SEC",
                     help="135.1 Unconfirmed Response Fail Time (default: EPICS Fail Times, else 3)")
    run.add_argument("--internal-processing-fail-time", type=float, metavar="SEC",
                     help="135.1 Internal Processing Fail Time (default: EPICS Fail Times, else 3)")
    run.add_argument("--timeout", type=float, default=120.0, help="per-test timeout in seconds")
    run.add_argument("--max-objects", type=int, default=50,
                     help="max objects visited by tests that walk the Object_List")
    run.add_argument("--list-tests", action="store_true", help="list registered tests and exit")

    out = p.add_argument_group("reporting")
    out.add_argument("-r", "--report", action="append", choices=FORMATS + ("epics",), metavar="FORMAT",
                     help=f"report format, repeatable: {', '.join(FORMATS)}, epics (default console)")
    out.add_argument("-o", "--output-dir", type=Path, default=Path("reports"))
    out.add_argument("-v", "--verbose", action="store_true", help="show test steps")
    out.add_argument("--debug", action="store_true", help="log protocol traffic")

    args = p.parse_args(argv)
    if args.unicast and not args.target:
        p.error("--unicast requires --target")
    return args


def config_from_args(args: argparse.Namespace, epics: Optional[Epics] = None) -> RunConfig:
    fail_times = epics.fail_times if epics else {}
    return RunConfig(
        local_address=args.address,
        tester_instance=args.tester_instance,
        device_instance=args.device_instance,
        target_address=args.target,
        unicast=args.unicast,
        bbmd=args.bbmd,
        bbmd_ttl=args.bbmd_ttl,
        unconfirmed_response_fail_time=_first(
            args.unconfirmed_response_fail_time, fail_times.get("unconfirmed response fail time"), 3.0
        ),
        internal_processing_fail_time=_first(
            args.internal_processing_fail_time, fail_times.get("internal processing fail time"), 3.0
        ),
        test_timeout=args.timeout,
        max_objects=args.max_objects,
        allow_writes=args.allow_writes,
        epics_path=args.epics,
        include=args.include,
        exclude=args.exclude,
        report_formats=args.report or ["console"],
        output_dir=args.output_dir,
        verbose=args.verbose,
    )


def _first(*values: Optional[float]) -> float:
    return next(v for v in values if v is not None)


def list_tests(config: RunConfig) -> None:
    for test in order_tests(filter_tests(all_tests(), config)):
        flags = []
        if test.services:
            flags.append("services=" + ",".join(test.services))
        if test.object_types:
            flags.append("objects=" + ",".join(test.object_types))
        if test.writes:
            flags.append("writes")
        if test.min_protocol_revision is not None:
            flags.append(f"Protocol_Revision>={test.min_protocol_revision}")
        if test.manual:
            flags.append("manual")
        extra = f"  [{'; '.join(flags)}]" if flags else ""
        print(f"{test.clause:<12} {test.title}{extra}")


async def run(config: RunConfig, epics: Optional[Epics] = None, generate: Optional[Path] = None) -> int:
    reporters = make_reporters(
        [f for f in config.report_formats if f != "epics"], config.output_dir, config.verbose
    )
    app = build_application(config)
    try:
        await app.listen_for_broadcasts()
        try:
            address, i_am = await discover_iut(app, config)
        except DiscoveryError as err:
            print(f"discovery failed: {err}", file=sys.stderr)
            return 2
        profile = await build_profile(app, address, i_am)
        shared: Dict[str, Any] = {"epics": epics}
        if generate is not None:
            print(f"reading {len(profile.object_list)} objects from {profile.device_id} ...")
            database = await read_database(app, profile, probe_writes=config.allow_writes)
            write_epics(generate, profile, database, config)
            print(f"EPICS written to {generate}; uncomment the BIBBs the product supports, "
                  f"then run with --epics {generate}")
            return 0
        report = await Runner(app, profile, config, reporters, shared).run(all_tests())
        if "epics" in config.report_formats:
            if "database" not in shared:
                shared["database"] = await read_database(app, profile, probe_writes=config.allow_writes)
            write_epics(config.output_dir / "report.epics", profile, shared["database"], config)
    finally:
        app.close()
    for fmt in config.report_formats:
        if fmt != "console":
            print(f"{fmt} report written to {config.output_dir}")
    return 0 if report.passed else 1


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.debug:
        # bacpypes3 logs expected Error/Reject/Abort responses as warnings
        logging.getLogger("bacpypes3").setLevel(logging.ERROR)
    discover()
    try:
        epics = parse_epics(args.epics) if args.epics else None
    except (OSError, ValueError) as err:
        print(f"cannot read EPICS: {err}", file=sys.stderr)
        return 2
    config = config_from_args(args, epics)
    if args.list_tests:
        list_tests(config)
        return 0
    try:
        return asyncio.run(run(config, epics, args.generate_epics))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
