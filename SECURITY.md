# Security Policy

## Supported versions

BACpicker has not yet made a release. Security fixes are made on the `default` branch
and will be included in the next release. Once releases are made, only the latest
release is supported.

## Reporting a vulnerability

Please do not report security vulnerabilities through public GitHub issues,
discussions or pull requests.

Report them privately through GitHub's
[private vulnerability reporting](https://github.com/bacnet-stack/bacpicker/security/advisories/new).

Please include:

- a description of the vulnerability and its impact;
- the BACpicker version or commit, Python version and BACpypes3 version;
- steps to reproduce, such as a command line, an EPICS file, or a capture of the
  BACnet traffic that triggers the problem;
- any suggested fix.

You can expect an acknowledgement within 7 days. We will keep you informed while
the issue is investigated and fixed, and credit you in the advisory unless you
prefer otherwise.

## Scope

BACpicker is a test tool that processes data from sources that may not be trusted.
Examples of issues in scope:

- crashes, hangs or excessive resource use caused by responses from a BACnet device;
- unsafe handling of EPICS files passed with `--epics`;
- content from a device or EPICS file that is not escaped in HTML, Markdown or
  JUnit XML reports;
- writes to the IUT when `--allow-writes` was not given.

Out of scope:

- vulnerabilities in BACpypes3 or other dependencies; report those to their
  projects;
- the effects of tests run with `--allow-writes`, which by design modify the IUT;
- weaknesses of the BACnet/IP protocol itself, which has no authentication.

Run BACpicker only against devices you are authorized to test, preferably on an
isolated network.
