# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Assertion helpers that record 135.1 defects instead of stopping at the first failure."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple, Type

from bacpypes3.apdu import (
    APDU,
    AbortPDU,
    ErrorPDU,
    ErrorRejectAbortNack,
    RejectPDU,
)
from bacpypes3.basetypes import ErrorClass, ErrorCode


class SkipTest(Exception):
    """Raised by a test when it does not apply to the IUT."""


class TestAborted(Exception):
    """Raised after a defect that prevents the rest of the test from running."""

    __test__ = False


def format_pdu(pdu: Any) -> str:
    """Render a request or response in a compact, human-readable form."""
    if pdu is None:
        return "<none>"
    if isinstance(pdu, ErrorPDU):
        return (
            f"{type(pdu).__name__}: error-class={getattr(pdu, 'errorClass', None)}, "
            f"error-code={getattr(pdu, 'errorCode', None)}"
        )
    if isinstance(pdu, RejectPDU):
        return f"Reject: reason={pdu.apduAbortRejectReason}"
    if isinstance(pdu, AbortPDU):
        return f"Abort: reason={pdu.apduAbortRejectReason}"
    if hasattr(pdu, "dict_contents"):
        try:
            contents = pdu.dict_contents()
            name = contents.pop("function", type(pdu).__name__)
            fields = ", ".join(f"{k}={_brief(v)}" for k, v in contents.items())
            source = getattr(pdu, "pduSource", None)
            suffix = f" from {source}" if source else ""
            return f"{name}({fields}){suffix}"
        except Exception:
            pass
    return repr(pdu)


def _brief(value: Any, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


class AssertionsMixin:
    """Mixed into TestContext; relies on its send() and defect() methods."""

    def check(
        self,
        condition: bool,
        message: str,
        *,
        expected: Any = None,
        actual: Any = None,
        request: Any = None,
        response: Any = None,
    ) -> bool:
        if not condition:
            self.defect(  # type: ignore[attr-defined]
                message,
                expected=expected,
                actual=actual,
                request=request,
                response=response,
            )
        return bool(condition)

    def check_equal(self, actual: Any, expected: Any, message: str) -> bool:
        return self.check(
            actual == expected, message, expected=expected, actual=actual
        )

    def require(self, condition: bool, message: str, **kwargs: Any) -> None:
        if not self.check(condition, message, **kwargs):
            raise TestAborted(message)

    async def expect_ack(
        self, request: APDU, ack_type: Optional[Type[APDU]] = None
    ) -> Optional[APDU]:
        """Send a confirmed request; record a defect unless an ACK arrives."""
        try:
            ack = await self.send(request)  # type: ignore[attr-defined]
        except ErrorRejectAbortNack as err:
            self.defect(  # type: ignore[attr-defined]
                "Expected an acknowledgement but the IUT responded with an error",
                expected=ack_type.__name__ if ack_type else "ACK",
                actual=format_pdu(err),
                request=request,
                response=err,
            )
            return None
        if ack_type is not None and not isinstance(ack, ack_type):
            self.defect(  # type: ignore[attr-defined]
                "Unexpected acknowledgement type",
                expected=ack_type.__name__,
                actual=type(ack).__name__,
                request=request,
                response=ack,
            )
            return None
        return ack

    async def expect_error(
        self,
        request: APDU,
        *alternatives: Tuple[str, str],
    ) -> bool:
        """Send a confirmed request; record a defect unless an Error PDU with one of the
        (error-class, error-code) alternatives arrives."""
        expected_pairs = [(ErrorClass(c), ErrorCode(e)) for c, e in alternatives]
        expected_text = " | ".join(
            f"Error: error-class={c}, error-code={e}" for c, e in expected_pairs
        )
        try:
            ack = await self.send(request)  # type: ignore[attr-defined]
        except ErrorPDU as err:
            ok = (err.errorClass, err.errorCode) in expected_pairs
            return self.check(
                ok,
                "Wrong error class or error code returned",
                expected=expected_text,
                actual=format_pdu(err),
                request=request,
                response=err,
            )
        except ErrorRejectAbortNack as err:
            return self.check(
                False,
                "Expected an Error PDU but received a Reject or Abort",
                expected=expected_text,
                actual=format_pdu(err),
                request=request,
                response=err,
            )
        return self.check(
            False,
            "Expected an Error PDU but the request was acknowledged",
            expected=expected_text,
            actual=format_pdu(ack),
            request=request,
            response=ack,
        )

    def check_access_error(
        self,
        error: Any,
        alternatives: Iterable[Tuple[str, Optional[str]]],
        message: str,
    ) -> bool:
        """Check an embedded error (e.g. a ReadPropertyMultiple propertyAccessError).

        alternatives are (error-class, error-code) pairs; a code of None accepts any code.
        """
        pairs = [(ErrorClass(c), ErrorCode(e) if e else None) for c, e in alternatives]
        expected = " | ".join(f"error-class={c}, error-code={e or 'any'}" for c, e in pairs)
        if error is None:
            return self.check(False, message, expected=expected, actual="<no error>")
        actual = f"error-class={error.errorClass}, error-code={error.errorCode}"
        return self.check(
            any(error.errorClass == c and (e is None or error.errorCode == e) for c, e in pairs),
            message,
            expected=expected,
            actual=actual,
        )
