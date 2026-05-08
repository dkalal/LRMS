from django.db.models import Q
from django.urls import reverse

from tenants.utils import normalize_phone_number

from .models import Customer


def find_possible_duplicate_customers(tenant, full_name="", phone_number="", broker=None, exclude_pk=None, limit=5):
    queryset = Customer.objects.filter(tenant=tenant).select_related("broker")
    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)

    normalized_phone = normalize_phone_number(phone_number)
    name = (full_name or "").strip()

    filters = Q()
    if normalized_phone:
        filters |= Q(phone_normalized=normalized_phone)
    if name:
        filters |= Q(full_name__iexact=name)
        if broker:
            filters |= Q(full_name__icontains=name, broker=broker)

    if not filters:
        return []

    duplicates = []
    for customer in queryset.filter(filters).order_by("full_name")[:limit]:
        reasons = []
        if normalized_phone and customer.phone_normalized == normalized_phone:
            reasons.append("same phone")
        if name and customer.full_name.lower() == name.lower():
            reasons.append("same name")
        if broker and customer.broker_id == broker.pk and name and customer.full_name.lower() == name.lower():
            reasons.append("same broker")
        duplicates.append(
            {
                "label": customer.full_name,
                "meta": f"{customer.phone_number or 'No phone'} · {customer.broker.full_name if customer.broker else 'No broker'}",
                "reasons": ", ".join(reasons) or "similar record",
                "url": reverse("customers:update", args=[customer.pk]),
            }
        )
    return duplicates
