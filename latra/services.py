from datetime import timedelta
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone

from accounts.services import filter_records_by_user_vehicle_permission
from audit.services import log_audit_event
from reminders.models import ReminderLog

from .models import LatraRecord, LatraRecordStatus


def calculate_expiry_status(record, today=None):
    if record.status == LatraRecordStatus.RENEWED:
        return "renewed"
    if record.status == LatraRecordStatus.CANCELLED:
        return "cancelled"

    today = today or timezone.localdate()
    days_left = (record.expiry_date - today).days
    if days_left < 0:
        return "expired"
    if days_left == 0:
        return "expires_today"
    if days_left <= 7:
        return "expiring_in_7_days"
    if days_left <= 30:
        return "expiring_in_30_days"
    return "active"


def get_contact_person(record):
    if record.customer.phone_number:
        return {
            "contact_name": record.customer.full_name,
            "contact_type": "Customer",
            "phone_number": record.customer.phone_number,
        }
    broker = record.broker or record.customer.broker
    if broker and broker.phone_number:
        return {
            "contact_name": broker.full_name,
            "contact_type": "Broker",
            "phone_number": broker.phone_number,
        }
    return {
        "contact_name": "",
        "contact_type": "Missing",
        "phone_number": "",
    }


def generate_whatsapp_message(record, contact):
    expiry_date = record.expiry_date.strftime("%d/%m/%Y")
    if contact["contact_type"] == "Broker":
        broker_name = contact["contact_name"] or "rafiki"
        return (
            f"Habari {broker_name}, tunakukumbusha kuhusu mteja "
            f"{record.customer.full_name}. Huduma ya LATRA kwa plate number "
            f"{record.vehicle.plate_number}, huduma ya {record.service_name}, "
            f"inaisha tarehe {expiry_date}. Tafadhali msaidie kuwasiliana nasi kwa renewal."
        )
    contact_name = contact["contact_name"] or "mteja"
    return (
        f"Habari {contact_name}, tunakukumbusha kuwa huduma ya LATRA kwa plate number "
        f"{record.vehicle.plate_number}, huduma ya {record.service_name}, inaisha tarehe "
        f"{expiry_date}. Tafadhali wasiliana nasi kwa ajili ya renewal."
    )


def build_whatsapp_url(phone, message):
    phone = "".join(char for char in phone if char.isdigit())
    return f"https://wa.me/{phone}?text={quote(message)}"


@transaction.atomic
def create_latra_record(*, user, **data):
    record = LatraRecord.objects.create(
        tenant=user.tenant,
        created_by=user,
        updated_by=user,
        **data,
    )
    log_audit_event(user, "latra.created", record, "LATRA record created.")
    return record


@transaction.atomic
def renew_latra_record(record, *, user, issue_date, expiry_date, notes=""):
    record.status = LatraRecordStatus.RENEWED
    record.updated_by = user
    record.save(update_fields=["status", "updated_by", "updated_at"])
    new_record = LatraRecord.objects.create(
        tenant=record.tenant,
        customer=record.customer,
        vehicle=record.vehicle,
        broker=record.broker,
        service_name=record.service_name,
        issue_date=issue_date,
        expiry_date=expiry_date,
        notes=notes,
        status=LatraRecordStatus.ACTIVE,
        previous_record=record,
        created_by=user,
        updated_by=user,
    )
    log_audit_event(user, "latra.renewed", new_record, "LATRA record renewed.")
    return new_record


def save_reminder_log(record, user, message):
    contact = get_contact_person(record)
    reminder = ReminderLog.objects.create(
        tenant=user.tenant,
        latra_record=record,
        contact_name=contact["contact_name"],
        contact_type=contact["contact_type"],
        phone_number=contact["phone_number"],
        message=message,
        generated_by=user,
    )
    log_audit_event(user, "message.generated", record, "WhatsApp reminder generated.")
    return reminder


def expiring_statuses():
    return {"expiring_in_30_days", "expiring_in_7_days", "expires_today"}


def apply_expiry_status_filter(queryset, status_name, today=None):
    today = today or timezone.localdate()
    if not status_name:
        return queryset
    if status_name == "active":
        return queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date__gt=today + timedelta(days=30))
    if status_name == "expiring_in_30_days":
        return queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date__gt=today + timedelta(days=7), expiry_date__lte=today + timedelta(days=30))
    if status_name == "expiring_in_7_days":
        return queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date__gt=today, expiry_date__lte=today + timedelta(days=7))
    if status_name == "expires_today":
        return queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date=today)
    if status_name == "expired":
        return queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date__lt=today)
    if status_name == "renewed":
        return queryset.filter(status=LatraRecordStatus.RENEWED)
    if status_name == "cancelled":
        return queryset.filter(status=LatraRecordStatus.CANCELLED)
    return queryset


def apply_expiring_followup_filter(queryset, today=None):
    today = today or timezone.localdate()
    return queryset.filter(
        status=LatraRecordStatus.ACTIVE,
        expiry_date__gte=today,
        expiry_date__lte=today + timedelta(days=30),
    )


def reminder_queryset_for_user(user):
    queryset = LatraRecord.objects.select_related("customer", "vehicle", "broker")
    return filter_records_by_user_vehicle_permission(queryset, user)
