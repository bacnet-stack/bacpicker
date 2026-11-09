# BACpicker

BACpicker is a BACnet/IP conformance test tool based on **ANSI/ASHRAE 135.1-2023** (Method of Test for
Conformance to BACnet), built on [BACpypes3](https://github.com/JoelBender/BACpypes3).
It picks at a device the way a conformance tester should, and builds and checks its EPICS.

It discovers a BACnet server (the IUT, Implementation Under Test), reads its capabilities,
runs the applicable 135.1 tests, and reports every test by its 135.1 clause as PASS, FAIL,
SKIP or ERROR. Each failure is recorded as a defect with the clause, test step, expected
and actual values, and the request/response that exposed it.

## Coverage

| 135.1 clause | Tests |
|---|---|
| 5 EPICS Consistency Tests | 5(a)–5(r) |
| 9.18 ReadProperty Service Execution Tests | 9.18.1.1–9.18.1.9, 9.18.2.1–9.18.2.4 |
| 9.20 ReadPropertyMultiple Service Execution Tests | 9.20.1.1–9.20.1.15, 9.20.2.1–9.20.2.3 |
| 9.32 Who-Has Service Execution Tests | 9.32.1.1–9.32.1.13, 9.32.2.1–9.32.2.4 |
| 9.33 Who-Is Service Execution Tests | 9.33.1.1–9.33.1.6, 9.33.2.1–9.33.2.3 |

Test titles and step numbers follow the 135.1 procedures. Procedures that cannot be
automated (for example requests originating from a simulated remote network) are listed
and reported as SKIP with the reason, so reports show complete clause coverage.

Tests are selected automatically: a test is skipped when the IUT's
Protocol_Services_Supported lacks a required service, when its Protocol_Revision is below
the procedure's minimum, or when it would modify the IUT and `--allow-writes` is not given.

## Installation

Requires Python 3.9 or later.

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Usage

List the registered tests:

```sh
bacpicker --list-tests
```

Run all applicable tests against device instance 1234:

```sh
bacpicker -a 192.168.1.10/24 -d 1234 -r console -r html -r junit -o reports
```

Options:

| Option | Purpose |
|---|---|
| `-a, --address` | Local BACnet/IP address, e.g. `192.168.1.10/24` or `192.168.1.10/24:47809`. Without a port, BACpicker binds UDP 47823 (0xBACF) and sends broadcasts to 47808 (0xBAC0), so it can run on the same host as a device. With an explicit port, broadcasts go to that port. |
| `--tester-instance` | Tester's own device instance (default 4194301) |
| `--bbmd HOST[:PORT]` | Register as a foreign device with a BBMD |
| `--bbmd-ttl` | Foreign device registration TTL in seconds (default 300) |
| `-d, --device-instance` | IUT device instance |
| `-t, --target` | IUT address; Who-Is is sent directly to it |
| `--unicast` | Send Who-Is/Who-Has to `--target` instead of broadcasting |
| `-i, --include` / `-x, --exclude` | Clause patterns, e.g. `-i '9.18.*' -x '9.18.1.6'` (repeatable) |
| `--allow-writes` | Enable tests and probes that write to the IUT |
| `--epics FILE` | EPICS with the user-declared sections (see below) |
| `--generate-epics FILE` | Read the IUT, write an EPICS, and exit |
| `--unconfirmed-response-fail-time` / `--internal-processing-fail-time` | 135.1 timers in seconds (default: from the EPICS, else 3 s) |
| `--timeout` | Per-test timeout in seconds (default 120) |
| `--max-objects` | Maximum objects visited by tests that walk the Object_List (default 50) |
| `--list-tests` | List the registered tests and exit |
| `-r, --report` | `console`, `json`, `junit`, `markdown`, `html`, `epics` (repeatable; default `console`) |
| `-o, --output-dir` | Directory for report files (default `reports`): `report.json`, `report.junit.xml`, `report.md`, `report.html`, `report.epics` |
| `-v, --verbose` / `--debug` | Show test steps / log protocol traffic |
| `--version` | Print the version and exit |

Exit status is 0 when every test passes or is skipped, 1 if any test fails or errors, and
2 if the IUT cannot be discovered.

## EPICS consistency workflow (clause 5)

The test database is read from the IUT, as the bacnet-stack `bacepics` tool does, so the
clause 5 checks compare the standard against live data. Information a device cannot
report (BIBBs, Initiate support, W/C markings, value restrictions) comes from an EPICS:

1. Generate an EPICS from the device. Annex K BIBBs the device appears to support are
   listed uncommented, with a hint of why each was included. DS-RP-B, required of all
   devices, is always listed uncommented. The remaining BIBBs are commented out:

   ```sh
   bacpicker -d 1234 --generate-epics iut.tpi
   ```

2. Edit `iut.tpi`: comment out any listed BIBBs the product does not claim, uncomment any
   that were missed, add `Initiate` to services the product initiates, and adjust the
   Fail Times.

3. Run the tests with the EPICS:

   ```sh
   bacpicker -d 1234 --epics iut.tpi -r console -r epics
   ```

Without `--epics`, the BIBB-dependent items 5(a)–5(f) are skipped. Items 5(j) and 5(p)
(writability) use write-back probing when `--allow-writes` is given, otherwise the EPICS
W/C markings.

## Reference data

`bacpicker/data/` holds the data the tests check against:

| File | Source |
|---|---|
| `bacnet-object-types.xml`, `bacnet-data-types.xml` | ASHRAE CSML data model (data.ashrae.org, Apache-2.0): object types, properties, required/optional/writable, ranges, bitstring definitions |
| `bibbs.json` | Annex K BIBB service tables, generated from 135-2024 by `tools/extract_bibbs.py` |
| `revisions.json` | Protocol_Revision in which object types and services were introduced, curated from the 135-2024 History of Revisions; entries marked `"verified": false` produce notes, never defects |

Object types required by each BIBB are curated from the Annex K text in
`BIBB_OBJECT_TYPES` in `bacpicker/standard.py`.

To regenerate the BIBB tables from a new edition of the standard:

```sh
.venv/bin/python tools/extract_bibbs.py /path/to/ASHRAE-135.md
```

## Project layout

```
bacpicker/
  cli.py              command-line entry point
  iut.py              tester application, IUT discovery and profile
  database.py         reads the IUT's objects and properties (the test database)
  epics.py            EPICS writer and parser (135.1 clause 4)
  standard.py         loaders for the reference data
  registry.py         @conformance_test decorator and test discovery
  runner.py           test selection, ordering and execution
  context.py          TestContext handed to every test
  assertions.py       defect-recording checks (expect_ack, expect_error, ...)
  reporting/          console, JSON, JUnit XML, Markdown and HTML reporters
  tests/              one module per 135.1 clause group
selftests/            pytest suite, including a simulated BACpypes3 device
tools/                maintenance scripts
```

## Writing a test

Add a module to `bacpicker/tests/`; it is discovered automatically. Use the exact
135.1 clause number and title, and mirror the procedure's step numbers in `ctx.step()`:

```python
from ..context import TestContext
from ..registry import conformance_test
from ._common import rp_request


@conformance_test("9.18.2.3", "Reading an Unknown Object", services=["read-property"])
async def reading_an_unknown_object(ctx: TestContext) -> None:
    objid = ctx.unknown_object_id()
    ctx.step(f"1. TRANSMIT ReadProperty-Request ({objid}), Object_Name")
    ctx.step("2. RECEIVE BACnet-Error-PDU OBJECT / UNKNOWN_OBJECT")
    await ctx.expect_error(rp_request(ctx, objid, "object-name"), ("object", "unknown-object"))
```

Decorator options: `services`, `object_types`, `writes`, `depends_on`,
`min_protocol_revision`, and `manual="reason"` for procedures that cannot be automated.

## Self-tests

```sh
.venv/bin/pytest -q
```

The suite runs the tool end to end against a BACpypes3 simulated device on the loopback
interface. Deviations of the simulator itself from the standard are listed in
`KNOWN_SIMULATOR_DEFECTS` in `selftests/test_end_to_end.py`; the suite fails if one of them
stops failing, so the list stays accurate.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text.

ASHRAE® and BACnet® are registered trademarks of the
American Society of Heating, Refrigerating and Air-Conditioning Engineers, Inc.
180 Technology Parkway NW, Peachtree Corners, Georgia 30092 US.
