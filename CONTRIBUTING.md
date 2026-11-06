# Contributing to BACpicker

Thank you for your interest in improving BACpicker. Bug reports, new 135.1 tests,
corrections to existing tests, and reference data fixes are all welcome.

## Getting started

Requires Python 3.9 or later.

```sh
git clone https://github.com/bacnet-stack/bacpicker.git
cd bacpicker
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

The self-tests run the tool end to end against a simulated BACpypes3 device on the
loopback interface, so no BACnet hardware is needed.

## Reporting issues

Report issues at https://github.com/bacnet-stack/bacpicker/issues. When reporting a problem, please include:

- the BACpicker version and Python version;
- the command line used;
- the 135.1 clause and test step involved, if any;
- the relevant report output (`-r json` or `-r markdown`) and, for protocol issues,
  the `--debug` log or a packet capture.

If you believe a test does not match the standard, cite the 135.1 edition, clause and
step, and quote the relevant procedure text.

## Adding or changing a conformance test

Tests live in `bacpicker/tests/`, one module per 135.1 clause group
(for example `clause_9_18_read_property.py`). Modules are discovered automatically.

- Use the exact 135.1 clause number and title in `@conformance_test`.
- Mirror the procedure's step numbers and wording in `ctx.step()`.
- Declare prerequisites with the decorator options (`services`, `object_types`,
  `writes`, `depends_on`, `min_protocol_revision`) rather than checking them inside
  the test, so selection and skipping stay consistent.
- Tests that modify the IUT must set `writes=True`.
- Procedures that cannot be automated must still be registered, with
  `manual="reason"`, so reports show complete clause coverage.
- Record failures through the context checks (`ctx.check`, `ctx.expect_ack`,
  `ctx.expect_error`, ...) with expected and actual values and the request/response,
  so every defect is traceable.
- Put helpers shared across clauses in `bacpicker/tests/_common.py`.
- Update the coverage table in `README.md` when adding clauses.

See "Writing a test" in [README.md](README.md) for an example.

## Reference data

Files in `bacpicker/data/` are derived from ASHRAE sources (see "Reference data" in
[README.md](README.md)).

- Regenerate `bibbs.json` with `tools/extract_bibbs.py` rather than editing it by hand.
- Entries added to `revisions.json` should cite the History of Revisions; mark them
  `"verified": false` until confirmed, so they produce notes rather than defects.
- Do not commit copyrighted text of the standards.

## Self-tests

Every change should keep `.venv/bin/pytest -q` passing. Add self-tests in `selftests/`
for new framework behaviour and new conformance tests.

If the simulated device deviates from the standard for a new test, add the test to
`KNOWN_SIMULATOR_DEFECTS` in `selftests/test_end_to_end.py`. The suite fails when a
listed defect stops failing, so keep the list accurate.

## Coding style

Ruff and Pyright run in CI with the settings in `pyproject.toml`; run them before
submitting:

```sh
.venv/bin/python -m ruff check .
.venv/bin/python -m pyright --pythonpath .venv/bin/python
```

- Follow the style of the surrounding code (PEP 8, type annotations,
  `from __future__ import annotations`).
- Keep compatibility with Python 3.9 (for example use `Optional[...]` and
  `Tuple[...]` from `typing`, not `X | None` at runtime).
- Start new source files with the copyright and SPDX header:

  ```python
  # Copyright 2026 Your Name <you@example.com>
  # SPDX-License-Identifier: Apache-2.0
  ```

## Submitting changes

1. Create a branch for your change.
2. Keep commits focused, with messages that reference the 135.1 clause where relevant.
3. Run the self-tests.
4. Add an entry under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
5. Open a pull request describing the change and, for test changes, the standard
   text it implements.

## License

By contributing, you agree that your contributions are licensed under the
Apache License, Version 2.0, as described in [LICENSE](LICENSE).
