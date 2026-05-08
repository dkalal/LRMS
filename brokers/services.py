from django.db.models import Q
from django.urls import reverse

from latra.services import calculate_expiry_status
from tenants.utils import normalize_phone_number

from .models import Broker


def find_possible_duplicate_brokers(tenant, full_name="", phone_number="", exclude_pk=None, limit=5):
    queryset = Broker.objects.filter(tenant=tenant)
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)

    normalized_phone = normalize_phone_number(phone_number)
    name = (full_name or "").strip()

    filters = Q()
    if normalized_phone:
        filters |= Q(phone_normalized=normalized_phone)
    if name:
        filters |= Q(full_name__iexact=name)

    if not filters:
        return []

    duplicates = []
    for broker in queryset.filter(filters).order_by("full_name")[:limit]:
        reasons = []
        if normalized_phone and broker.phone_normalized == normalized_phone:
            reasons.append("same phone")
        if name and broker.full_name.lower() == name.lower():
            reasons.append("same name")
        duplicates.append(
            {
                "label": broker.full_name,
                "meta": f"{broker.phone_number} · {broker.location or 'No location'}",
                "reasons": ", ".join(reasons) or "similar record",
                "url": reverse("brokers:update", args=[broker.pk]),
            }
        )
    return duplicates


def get_broker_statistics(broker, user=None):
    customers = broker.customer_set.all()
    records = broker.latrarecord_set.select_related("vehicle", "customer")

    expiring = 0
    expired = 0
    for record in records:
        status = calculate_expiry_status(record)
        if status in {"expiring_in_30_days", "expiring_in_7_days", "expires_today"}:
            expiring += 1
        if status == "expired":
            expired += 1

    return {
        "total_customers": customers.count(),
        "active_customers": customers.filter(status="active").count(),
        "customers_with_expiring_records": expiring,
        "customers_with_expired_records": expired,
    }
