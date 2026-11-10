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
  - Remaining clause 9 application service execution tests for the services BACpypes3
    can encode, other than VT and the removed RequestKey and Authenticate services.
    Procedures that need an alarm, a subscription from the IUT, a vendor password, a
    known file image, or a reboot are registered and reported as not automated.
    The 9.39 unsupported-service tests require `--allow-writes`, since an IUT that
    executes a service it does not claim could be changed by the probe.
- Procedures that cannot be automated are registered and reported as SKIP with the reason.
- EPICS generation from the IUT (`--generate-epics`) and EPICS parsing (`--epics`).
- Reporters: console, JSON, JUnit XML, Markdown, HTML and EPICS.
- Reference data: ASHRAE CSML object and data type models, Annex K BIBB tables, and
  Protocol_Revision history; `tools/extract_bibbs.py` to regenerate the BIBB tables.
- Self-test suite running the tool end to end against a simulated BACpypes3 device.
- Color and Color Temperature object support (types 63 and 64, and the Lighting Output
  color properties) added at import for BACpypes3 releases that lack it.
- GitHub Actions workflows for the self-tests, Ruff, Pyright and CodeQL.
- `CONTRIBUTING.md`.

### Changed

- `--generate-epics` lists every Annex K BIBB the device appears to support uncommented,
  with the reason it was included. DS-RP-B stays uncommented even when ReadProperty
  cannot be inferred, because every device must support it. The remaining BIBBs stay
  commented out.
- Without a port in `--address`, the tester binds UDP 47823 (0xBACF) and sends
  broadcasts to 47808 (0xBAC0), so it can run on the same host as the IUT.

### Fixed

- HTML report showed each test step number twice.
- On Windows, listening for broadcasts on port 47808 failed with "reuse_port not
  supported by socket module".
- The test database now decodes Object_Identifier, Object_Name and Object_Type of
  proprietary objects whose types the tester has no class for, so the generated EPICS
  lists them as `(proprietary N, i)` and clause 5(h) no longer reports them as missing.

[Unreleased]: https://github.com/bacnet-stack/bacpicker/commits/default
