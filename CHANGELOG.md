# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--list-devices` sends a global Who-Is using the configured local address and BBMD,
  lists the responding devices, and exits without running tests.
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

- The property-identifier map includes 135-2024 Clause 21 identifiers 4194338–4194349,
  which ASHRAE CSML dataRev 24 does not yet publish. Device, Network Port, and
  Lighting Output include the properties Clause 12 assigns to them, so a live read
  of Device_Address_Proxy_Table is named `device-address-proxy-table`.
- `--generate-epics` infers the Initiate services Annex K requires of each suggested
  BIBB, because Protocol_Services_Supported has only execute bits. A device that
  executes SubscribeCOV is listed as initiating ConfirmedCOVNotification and
  UnconfirmedCOVNotification. `time-synchronization-recipients` lists
  TimeSynchronization Initiate and leaves DM-TS-A commented as a possible inclusion.
  `utc-time-synchronization-recipients` does the same for UTCTimeSynchronization and
  DM-UTC-A. Both lists together with `time-synchronization-interval` also leave
  DM-ATS-A as a possible inclusion. `restart-notification-recipients` uncomments DM-R-B,
  and a Notification Class object uncomments AE-N-I-B.
- Lighting Output `last-on-value` and `default-on-value` are required starting at
  Protocol_Revision 28 (Addendum cj to 135-2020). Clause 5(i) does not require them
  on an earlier revision.
- `--generate-epics` lists every Annex K BIBB the device appears to support uncommented,
  with the reason it was included. DS-RP-B stays uncommented even when ReadProperty
  cannot be inferred, because every device must support it. The remaining BIBBs stay
  commented out.
- Without a port in `--address`, the tester binds UDP 47823 (0xBACF) and sends
  broadcasts to 47808 (0xBAC0), so it can run on the same host as the IUT.

### Fixed

- Clause 5(d) accepts a BIBB Initiate role that the device evidence implies when the
  EPICS omits it, and notes that inference. DS-COV-B no longer fails for
  ConfirmedCOVNotification Initiate solely because the execute bit string cannot say
  Initiate.
- HTML report showed each test step number twice.
- On Windows, listening for broadcasts on port 47808 failed with "reuse_port not
  supported by socket module".
- The test database now decodes Object_Identifier, Object_Name and Object_Type of
  proprietary objects whose types the tester has no class for, so the generated EPICS
  lists them as `(proprietary N, i)` and clause 5(h) no longer reports them as missing.
- The test database also decodes Property_List of proprietary objects, so clause 5(n)
  no longer reports it as missing when the IUT returned it, including when
  ReadPropertyMultiple is unavailable or its ALL request fails.

[Unreleased]: https://github.com/bacnet-stack/bacpicker/commits/default
