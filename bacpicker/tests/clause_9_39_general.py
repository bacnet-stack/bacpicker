# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.39 General Testing of Service Execution."""

from __future__ import annotations

from typing import Optional, Tuple

from bacpypes3.apdu import (
    APDU,
    AbortPDU,
    AcknowledgeAlarmRequest,
    AddListElementRequest,
    APCISequence,
    AtomicReadFileRequest,
    AtomicWriteFileRequest,
    ConfirmedCOVNotificationRequest,
    ConfirmedEventNotificationRequest,
    ConfirmedPrivateTransferRequest,
    ConfirmedRequestPDU,
    ConfirmedTextMessageRequest,
    CreateObjectRequest,
    DeleteObjectRequest,
    DeviceCommunicationControlRequest,
    ErrorPDU,
    ErrorRejectAbortNack,
    GetAlarmSummaryRequest,
    GetEnrollmentSummaryRequest,
    GetEventInformationRequest,
    LifeSafetyOperationRequest,
    ReadRangeRequest,
    ReinitializeDeviceRequest,
    RejectPDU,
    RemoveListElementRequest,
    SubscribeCOVPropertyRequest,
    SubscribeCOVRequest,
    UnconfirmedEventNotificationRequest,
    UnconfirmedPrivateTransferRequest,
    UnconfirmedRequestPDU,
    UnconfirmedTextMessageRequest,
    VTCloseRequest,
    VTDataRequest,
    VTOpenRequest,
    WritePropertyMultipleRequest,
)
from bacpypes3.basetypes import (
    NotificationParameters,
    NotificationParametersChangeOfState,
    PropertyStates,
    PropertyValue,
    TimeStamp,
    WriteAccessSpecification,
)
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, OctetString, Unsigned

from ..assertions import format_pdu
from ..context import TestContext
from ..registry import conformance_test
from ._common import rpm_request

# Confirmed service choice and the Protocol_Services_Supported bit. Choices with no
# typed APDU in bacpypes3 are sent as a bare confirmed request.
CONFIRMED: Tuple[Tuple[int, str], ...] = (
    (0, "acknowledge-alarm"),
    (1, "confirmed-cov-notification"),
    (2, "confirmed-event-notification"),
    (3, "get-alarm-summary"),
    (4, "get-enrollment-summary"),
    (5, "subscribe-cov"),
    (6, "atomic-read-file"),
    (7, "atomic-write-file"),
    (8, "add-list-element"),
    (9, "remove-list-element"),
    (10, "create-object"),
    (11, "delete-object"),
    (12, "read-property"),
    (14, "read-property-multiple"),
    (15, "write-property"),
    (16, "write-property-multiple"),
    (17, "device-communication-control"),
    (18, "confirmed-private-transfer"),
    (19, "confirmed-text-message"),
    (20, "reinitialize-device"),
    (21, "vt-open"),
    (22, "vt-close"),
    (23, "vt-data"),
    (26, "read-range"),
    (27, "life-safety-operation"),
    (28, "subscribe-cov-property"),
    (29, "get-event-information"),
    (30, "subscribe-cov-property-multiple"),
    (31, "confirmed-cov-notification-multiple"),
    (32, "confirmed-audit-notification"),
    (33, "audit-log-query"),
)

UNCONFIRMED: Tuple[Tuple[int, str], ...] = (
    (0, "i-am"),
    (1, "i-have"),
    (2, "unconfirmed-cov-notification"),
    (3, "unconfirmed-event-notification"),
    (4, "unconfirmed-private-transfer"),
    (5, "unconfirmed-text-message"),
    (6, "time-synchronization"),
    (7, "who-has"),
    (8, "who-is"),
    (9, "utc-time-synchronization"),
    (10, "write-group"),
    (11, "unconfirmed-cov-notification-multiple"),
    (12, "unconfirmed-audit-notification"),
    (13, "who-am-i"),
    (14, "you-are"),
)

UNDEFINED_CONFIRMED = 34
UNDEFINED_UNCONFIRMED = 15


def _stamp() -> TimeStamp:
    from bacpypes3.primitivedata import Time

    return TimeStamp(time=Time((0, 0, 0, 0)))


def _event(ctx: TestContext, confirmed: bool):
    cls = ConfirmedEventNotificationRequest if confirmed else UnconfirmedEventNotificationRequest
    values = NotificationParameters(
        changeOfState=NotificationParametersChangeOfState(
            newState=PropertyStates(binaryValue="inactive"),
            statusFlags=[0, 0, 0, 0],
        )
    )
    return cls(
        processIdentifier=1,
        initiatingDeviceIdentifier=ctx.app.device_object.objectIdentifier,
        eventObjectIdentifier=ObjectIdentifier("event-enrollment,1"),
        timeStamp=_stamp(),
        notificationClass=1,
        priority=100,
        eventType="change-of-state",
        notifyType="alarm",
        ackRequired=False,
        fromState="normal",
        toState="offnormal",
        eventValues=values,
        destination=ctx.iut.address,
    )


def _file_read(ctx: TestContext) -> AtomicReadFileRequest:
    from bacpypes3.basetypes import AtomicReadFileRequestAccessMethodChoice

    return AtomicReadFileRequest(
        fileIdentifier=ObjectIdentifier("file,1"),
        accessMethod=AtomicReadFileRequestAccessMethodChoice(streamAccess={"fileStartPosition": 0,
            "requestedOctetCount": 1}),
        destination=ctx.iut.address,
    )


def _file_write(ctx: TestContext) -> AtomicWriteFileRequest:
    from bacpypes3.basetypes import AtomicWriteFileRequestAccessMethodChoice

    return AtomicWriteFileRequest(
        fileIdentifier=ObjectIdentifier("file,1"),
        accessMethod=AtomicWriteFileRequestAccessMethodChoice(streamAccess={"fileStartPosition": 0,
            "fileData": b"\x00"}),
        destination=ctx.iut.address,
    )


def _minimal_confirmed(ctx: TestContext, choice: int, object_name: str) -> APDU:
    """A decodable request for a confirmed service, or a bare request when bacpypes3 has no type."""
    device = ctx.iut.device_id
    td = ctx.app.device_object.objectIdentifier
    address = ctx.iut.address
    built: Optional[APDU] = None
    if choice == 0:
        built = AcknowledgeAlarmRequest(
            acknowledgingProcessIdentifier=1,
            eventObjectIdentifier=device,
            eventStateAcknowledged="normal",
            timeStamp=_stamp(),
            acknowledgmentSource=CharacterString("TD"),
            timeOfAcknowledgment=_stamp(),
        )
    elif choice == 1:
        built = ConfirmedCOVNotificationRequest(
            subscriberProcessIdentifier=1,
            initiatingDeviceIdentifier=td,
            monitoredObjectIdentifier=device,
            timeRemaining=0,
            listOfValues=[PropertyValue(propertyIdentifier="present-value", value=Unsigned(0))],
        )
    elif choice == 2:
        return _event(ctx, True)
    elif choice == 3:
        built = GetAlarmSummaryRequest()
    elif choice == 4:
        built = GetEnrollmentSummaryRequest(acknowledgmentFilter="all")
    elif choice == 5:
        built = SubscribeCOVRequest(subscriberProcessIdentifier=1, monitoredObjectIdentifier=device)
    elif choice == 6:
        return _file_read(ctx)
    elif choice == 7:
        return _file_write(ctx)
    elif choice == 8:
        built = AddListElementRequest(
            objectIdentifier=device, propertyIdentifier="object-name", listOfElements=CharacterString("x")
        )
    elif choice == 9:
        built = RemoveListElementRequest(
            objectIdentifier=device, propertyIdentifier="object-name", listOfElements=CharacterString("x")
        )
    elif choice == 10:
        from bacpypes3.basetypes import CreateObjectRequestObjectSpecifier

        built = CreateObjectRequest(objectSpecifier=CreateObjectRequestObjectSpecifier(objectType="device"))
    elif choice == 11:
        built = DeleteObjectRequest(objectIdentifier=device)
    elif choice == 14:
        return rpm_request(ctx, [(device, ["object-name"])])
    elif choice == 16:
        built = WritePropertyMultipleRequest(
            listOfWriteAccessSpecs=[
                WriteAccessSpecification(
                    objectIdentifier=device,
                    listOfProperties=[PropertyValue(propertyIdentifier="object-name",
                        value=CharacterString(object_name))],
                )
            ]
        )
    elif choice == 17:
        built = DeviceCommunicationControlRequest(enableDisable="disable-initiation")
    elif choice == 18:
        built = ConfirmedPrivateTransferRequest(vendorID=0, serviceNumber=0)
    elif choice == 19:
        built = ConfirmedTextMessageRequest(
            textMessageSourceDevice=td, messagePriority="normal", message=CharacterString("x")
        )
    elif choice == 20:
        built = ReinitializeDeviceRequest(reinitializedStateOfDevice="warmstart")
    elif choice == 21:
        built = VTOpenRequest(vtClass="default-terminal", localVTSessionIdentifier=1)
    elif choice == 22:
        built = VTCloseRequest(listOfRemoteVTSessionIdentifiers=[1])
    elif choice == 23:
        built = VTDataRequest(vtSessionIdentifier=1, vtNewData=OctetString(b"\x00"), vtDataFlag=0)
    elif choice == 26:
        built = ReadRangeRequest(objectIdentifier=device, propertyIdentifier="object-list")
    elif choice == 27:
        built = LifeSafetyOperationRequest(
            requestingProcessIdentifier=1, requestingSource=CharacterString("td"), request="reset"
        )
    elif choice == 28:
        built = SubscribeCOVPropertyRequest(
            subscriberProcessIdentifier=1,
            monitoredObjectIdentifier=device,
            monitoredPropertyIdentifier="object-name",
        )
    elif choice == 29:
        built = GetEventInformationRequest()
    request = built if built is not None else ConfirmedRequestPDU(choice)
    request.pduDestination = address
    return request


def _minimal_unconfirmed(ctx: TestContext, choice: int, name: str) -> APDU:
    address = ctx.iut.address
    td = ctx.app.device_object.objectIdentifier
    if name == "unconfirmed-private-transfer":
        request = UnconfirmedPrivateTransferRequest(vendorID=0, serviceNumber=0, destination=address)
        return request
    if name == "unconfirmed-text-message":
        return UnconfirmedTextMessageRequest(
            textMessageSourceDevice=td,
            messagePriority="normal",
            message=CharacterString("x"),
            destination=address,
        )
    if name == "unconfirmed-event-notification":
        return _event(ctx, False)
    if name == "time-synchronization":
        from bacpypes3.apdu import TimeSynchronizationRequest
        from bacpypes3.basetypes import DateTime
        from bacpypes3.primitivedata import Date, Time

        return TimeSynchronizationRequest(
            time=DateTime(date=Date((90, 1, 1, 1)), time=Time((0, 0, 0, 0))), destination=address
        )
    if name == "utc-time-synchronization":
        from bacpypes3.apdu import UTCTimeSynchronizationRequest
        from bacpypes3.basetypes import DateTime
        from bacpypes3.primitivedata import Date, Time

        return UTCTimeSynchronizationRequest(
            time=DateTime(date=Date((90, 1, 1, 1)), time=Time((0, 0, 0, 0))), destination=address
        )
    if name == "write-group":
        from bacpypes3.apdu import WriteGroupRequest

        return WriteGroupRequest(groupNumber=1, writePriority=16, changeList=[], destination=address)
    request = UnconfirmedRequestPDU(choice, destination=address)
    return request


# Probes for unsupported services can change the IUT if a handler runs anyway (write a file,
# disable initiation, reinitialize, reset life-safety objects, set the clock), so both tests
# need --allow-writes.
@conformance_test("9.39.1", "Unsupported Confirmed Services Test", writes=True)
async def unsupported_confirmed_services(ctx: TestContext) -> None:
    if ctx.iut.services_supported_length is None:
        ctx.skip("Protocol_Services_Supported was not read; unsupported services are unknown")
    tester = ctx.app.device_object
    saved = (tester.apduTimeout, tester.numberOfApduRetries)
    tester.apduTimeout, tester.numberOfApduRetries = 500, 0
    try:
        object_name = str(await ctx.read(ctx.iut.device_id, "object-name"))
        for choice, name in CONFIRMED:
            if ctx.iut.supports_service(name):
                continue
            ctx.step(f"1. TRANSMIT {name}; RECEIVE Reject UNRECOGNIZED_SERVICE")
            await _expect_unrecognized(ctx, _minimal_confirmed(ctx, choice, object_name), name)
        ctx.step("2. TRANSMIT an undefined confirmed service choice")
        ctx.step("3. RECEIVE Reject UNRECOGNIZED_SERVICE")
        raw = ConfirmedRequestPDU(UNDEFINED_CONFIRMED, destination=ctx.iut.address)
        await _expect_unrecognized(ctx, raw, f"confirmed service {UNDEFINED_CONFIRMED}")
    finally:
        tester.apduTimeout, tester.numberOfApduRetries = saved


@conformance_test("9.39.2", "Unsupported Unconfirmed Services Test", writes=True)
async def unsupported_unconfirmed_services(ctx: TestContext) -> None:
    device = ctx.iut.device_id
    ctx.step("1. VERIFY System_Status = OPERATIONAL or OPERATIONAL_READ_ONLY")
    status = str(await ctx.read(device, "system-status"))
    ctx.check(
        status in ("operational", "operational-read-only"),
        "System_Status is not OPERATIONAL or OPERATIONAL_READ_ONLY",
        expected="operational | operational-read-only",
        actual=status,
    )
    services = [
        item for item in UNCONFIRMED
        if item[1] == "unconfirmed-private-transfer" or not ctx.iut.supports_service(item[1])
    ]
    for choice, name in services:
        ctx.step(f"2. TRANSMIT {name}")
        request = _minimal_unconfirmed(ctx, choice, name)
        ctx.step("BEFORE Internal Processing Fail Time, the IUT sends nothing and does not reset")
        packets = await ctx.collect(
            request,
            lambda apdu: getattr(apdu, "pduSource", None) == ctx.iut.address,
            ctx.config.internal_processing_fail_time,
        )
        ctx.check(
            not packets,
            f"IUT sent a PDU in response to unsupported {name}",
            expected="no PDU",
            actual=format_pdu(packets[0]) if packets else "",
        )
        again = str(await ctx.read(device, "system-status"))
        ctx.check(again == status, "System_Status changed", expected=status, actual=again)


async def _expect_unrecognized(ctx: TestContext, request: APDU, name: str) -> None:
    if isinstance(request, APCISequence):
        try:
            request.encode()
        except Exception as err:
            ctx.defect(
                f"tester could not encode {name}",
                expected="a confirmed request",
                actual=f"{type(err).__name__}: {err}",
            )
            return
    try:
        ack = await ctx.send(request)
    except RejectPDU as err:
        ctx.check(
            str(err.apduAbortRejectReason) == "unrecognized-service",
            f"{name} was not rejected as unrecognized-service",
            expected="Reject: unrecognized-service",
            actual=format_pdu(err),
            request=request,
            response=err,
        )
        return
    except (ErrorPDU, AbortPDU, ErrorRejectAbortNack) as err:
        ctx.defect(
            f"{name} was not rejected as unrecognized-service",
            expected="Reject: unrecognized-service",
            actual=format_pdu(err),
            request=request,
            response=err,
        )
        return
    ctx.defect(
        f"{name} was acknowledged",
        expected="Reject: unrecognized-service",
        actual=format_pdu(ack),
        request=request,
    )

