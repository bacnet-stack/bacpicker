# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- BACnet/IP conformance test tool based on ANSI/ASHRAE 135.1-2023, built on BACpypes3.
- IUT discovery with Who-Is (broadcast, unicast, or as a foreign device via a BBMD)
  and capability profiling from the Device object.
- Test framework: `@conformance_test` registration, automatic selection by
  Protocol_Services_Supported, object types, Protocol_Revision and `--allow-writes`,
  test dependencies, and per-test defect recording with clause, step, expected and
  actual values, and the request/response.
- Conformance tests:
  - 5 EPICS Consistency Tests, 5(a)–5(r).
  - 9.18 ReadProperty Service Execution Tests.
  - 9.20 ReadPropertyMultiple Service Execution Tests.
  - 9.32 Who-Has Service Execution Tests.
  - 9.33 Who-Is Service Execution Tests.
- Procedures that cannot be automated are registered and reported as SKIP with the reason.
- EPICS generation from the IUT (`--generate-epics`) and EPICS parsing (`--epics`).
- Reporters: console, JSON, JUnit XML, Markdown, HTML and EPICS.
- Reference data: ASHRAE CSML object and data type models, Annex K BIBB tables, and
  Protocol_Revision history; `tools/extract_bibbs.py` to regenerate the BIBB tables.
- Self-test suite running the tool end to end against a simulated BACpypes3 device.
- GitHub Actions workflows for the self-tests, Ruff, Pyright and CodeQL.
- `CONTRIBUTING.md`.

### Changed

- Without a port in `--address`, the tester binds UDP 47823 (0xBACF) and sends
  broadcasts to 47808 (0xBAC0), so it can run on the same host as the IUT.

### Fixed

- HTML report showed each test step number twice.

[Unreleased]: https://github.com/bacnet-stack/bacpicker/commits/default
