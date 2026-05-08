from datetime import date, timedelta

from django.db.models import Count
from django.utils import timezone

from accounts.models import VehicleCategoryChoices
from accounts.services import filter_records_by_user_vehicle_permission
from audit.models import AuditLog
from brokers.models import Broker
from customers.models import Customer
from latra.models import LatraRecord, LatraRecordStatus
from tenants.models import ActiveStatus
from vehicles.models import Vehicle


FOLLOWUP_STATUSES = {"expiring_in_30_days", "expiring_in_7_days", "expires_today"}


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def get_allowed_categories(user):
    choices = [
        choice
        for choice in VehicleCategoryChoices.choices
        if choice[0] != VehicleCategoryChoices.ALL
    ]
    if user.is_superuser or user.has_all_vehicle_access():
        return choices
    assigned = set(user.assigned_vehicle_categories())
    return [choice for choice in choices if choice[0] in assigned]


def apply_report_filters(user, params):
    date_from = parse_date(params.get("date_from"))
    date_to = parse_date(params.get("date_to"))
    category = params.get("vehicle_category", "").strip()
    allowed_categories = get_allowed_categories(user)
    allowed_values = {value for value, _label in allowed_categories}

    if category and category not in allowed_values:
        category = ""

    records = filter_records_by_user_vehicle_permission(
        LatraRecord.objects.select_related("customer", "vehicle", "broker", "created_by"),
        user,
    )
    if category:
        records = records.filter(vehicle__vehicle_category=category)
    if date_from:
        records = records.filter(expiry_date__gte=date_from)
    if date_to:
        records = records.filter(expiry_date__lte=date_to)

    vehicles = Vehicle.objects.filter(tenant=user.tenant)
    if not user.is_superuser and not user.has_all_vehicle_access():
        vehicles = vehicles.filter(vehicle_category__in=allowed_values)
    if category:
        vehicles = vehicles.filter(vehicle_category=category)

    return records, vehicles, allowed_categories, {
        "date_from": params.get("date_from", ""),
        "date_to": params.get("date_to", ""),
        "vehicle_category": category,
    }


def count_expiry_buckets(records, today=None):
    today = today or timezone.localdate()
    active_records = records.filter(status=LatraRecordStatus.ACTIVE)
    return {
        "active": active_records.filter(expiry_date__gt=today + timedelta(days=30)).count(),
        "expiring_in_30_days": active_records.filter(
            expiry_date__gt=today + timedelta(days=7),
            expiry_date__lte=today + timedelta(days=30),
        ).count(),
        "expiring_in_7_days": active_records.filter(
            expiry_date__gt=today,
            expiry_date__lte=today + timedelta(days=7),
        ).count(),
        "expires_today": active_records.filter(expiry_date=today).count(),
        "expired": active_records.filter(expiry_date__lt=today).count(),
        "renewed": records.filter(status=LatraRecordStatus.RENEWED).count(),
        "cancelled": records.filter(status=LatraRecordStatus.CANCELLED).count(),
    }


def values_count_map(queryset, value_field):
    return {
        row[value_field]: row["count"]
        for row in queryset.values(value_field).annotate(count=Count("id"))
    }


def get_reports_context(user, params):
    records, vehicles, available_categories, filters = apply_report_filters(user, params)
    tenant = user.tenant
    operational_records = records.exclude(status=LatraRecordStatus.CANCELLED)
    expiry_counter = count_expiry_buckets(records)

    category_counts = values_count_map(operational_records, "vehicle__vehicle_category")
    status_counts = values_count_map(records, "status")
    service_breakdown = list(
        operational_records.values("service_name")
        .annotate(count=Count("id"))
        .order_by("-count", "service_name")[:8]
    )
    staff_activity = list(
        operational_records.filter(created_by__isnull=False)
        .values("created_by__username", "created_by__first_name", "created_by__last_name")
        .annotate(count=Count("id"))
        .order_by("-count", "created_by__username")[:8]
    )

    customer_counts = values_count_map(Customer.objects.filter(tenant=tenant), "broker_id")
    active_customer_counts = values_count_map(
        Customer.objects.filter(tenant=tenant, status=ActiveStatus.ACTIVE),
        "broker_id",
    )
    broker_record_counts = values_count_map(operational_records, "broker_id")
    today = timezone.localdate()
    broker_expiring_counts = values_count_map(
        operational_records.filter(
            status=LatraRecordStatus.ACTIVE,
            expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=30),
        ),
        "broker_id",
    )
    broker_expired_counts = values_count_map(
        operational_records.filter(
            status=LatraRecordStatus.ACTIVE,
            expiry_date__lt=today,
        ),
        "broker_id",
    )

    broker_stats = []
    for broker in Broker.objects.filter(tenant=tenant).order_by("full_name"):
        broker_stats.append(
            {
                "broker": broker,
                "customers": customer_counts.get(broker.pk, 0),
                "active_customers": active_customer_counts.get(broker.pk, 0),
                "records": broker_record_counts.get(broker.pk, 0),
                "expiring": broker_expiring_counts.get(broker.pk, 0),
                "expired": broker_expired_counts.get(broker.pk, 0),
            }
        )
    broker_stats.sort(key=lambda item: (item["expiring"], item["expired"], item["records"]), reverse=True)

    return {
        "filters": filters,
        "vehicle_categories": available_categories,
        "headline": {
            "customers": Customer.objects.filter(tenant=tenant, status=ActiveStatus.ACTIVE).count(),
            "brokers": Broker.objects.filter(tenant=tenant, status=ActiveStatus.ACTIVE).count(),
            "vehicles": vehicles.filter(status=ActiveStatus.ACTIVE).count(),
            "latra_records": operational_records.count(),
            "expiring": sum(expiry_counter[key] for key in FOLLOWUP_STATUSES),
            "expired": expiry_counter["expired"],
        },
        "expiry_breakdown": [
            ("Active", expiry_counter["active"]),
            ("Expiring in 30 days", expiry_counter["expiring_in_30_days"]),
            ("Expiring in 7 days", expiry_counter["expiring_in_7_days"]),
            ("Expires today", expiry_counter["expires_today"]),
            ("Expired", expiry_counter["expired"]),
            ("Renewed", expiry_counter["renewed"]),
            ("Cancelled", expiry_counter["cancelled"]),
        ],
        "category_breakdown": [
            (label, category_counts.get(value, 0)) for value, label in available_categories
        ],
        "service_breakdown": [
            (row["service_name"], row["count"]) for row in service_breakdown
        ],
        "record_status_breakdown": [
            ("Active", status_counts.get(LatraRecordStatus.ACTIVE, 0)),
            ("Renewed", status_counts.get(LatraRecordStatus.RENEWED, 0)),
            ("Cancelled", status_counts.get(LatraRecordStatus.CANCELLED, 0)),
        ],
        "broker_stats": broker_stats[:10],
        "staff_activity": [
            (
                " ".join(
                    part
                    for part in [row["created_by__first_name"], row["created_by__last_name"]]
                    if part
                )
                or row["created_by__username"],
                row["count"],
            )
            for row in staff_activity
        ],
        "recent_audit_logs": AuditLog.objects.filter(tenant=tenant)
        .select_related("actor")
        .order_by("-created_at")[:10],
    }


def get_dashboard_context(user):
    tenant = user.tenant
    records = filter_records_by_user_vehicle_permission(
        LatraRecord.objects.select_related("customer", "vehicle", "broker"),
        user,
    )
    operational_records = records.exclude(status=LatraRecordStatus.CANCELLED)
    expiry_counter = count_expiry_buckets(records)

    vehicles = Vehicle.objects.filter(tenant=tenant, status=ActiveStatus.ACTIVE)
    if not user.is_superuser and not user.has_all_vehicle_access():
        vehicles = vehicles.filter(vehicle_category__in=user.assigned_vehicle_categories())

    recent_records = list(operational_records.order_by("expiry_date", "-created_at")[:8])
    followup_records = list(operational_records.filter(
        status=LatraRecordStatus.ACTIVE,
        expiry_date__lte=timezone.localdate() + timedelta(days=30),
    ).order_by("expiry_date", "-created_at")[:8])
    active_customer_count = Customer.objects.filter(
        tenant=tenant,
        status=ActiveStatus.ACTIVE,
    ).count()
    active_broker_count = Broker.objects.filter(
        tenant=tenant,
        status=ActiveStatus.ACTIVE,
    ).count()
    active_vehicle_count = vehicles.count()

    return {
        "table_columns": ["Plate", "Customer", "Service", "Expiry"],
        "total_customers": active_customer_count,
        "total_brokers": active_broker_count,
        "total_vehicles": active_vehicle_count,
        "active_records": expiry_counter["active"],
        "expiring_30_records": expiry_counter["expiring_in_30_days"],
        "expiring_7_records": expiry_counter["expiring_in_7_days"],
        "today_records": expiry_counter["expires_today"],
        "expired_records": expiry_counter["expired"],
        "recent_records": recent_records,
        "followup_records": followup_records,
        "dashboard_cards": [
            {
                "label": "Customers",
                "value": active_customer_count,
                "href": "customers:list",
                "tone": "neutral",
                "hint": "Active customer records",
            },
            {
                "label": "Brokers",
                "value": active_broker_count,
                "href": "brokers:list",
                "tone": "neutral",
                "hint": "Active broker records",
            },
            {
                "label": "Vehicles",
                "value": active_vehicle_count,
                "href": "vehicles:list",
                "tone": "neutral",
                "hint": "Vehicles within your category access",
            },
            {
                "label": "Active LATRA",
                "value": expiry_counter["active"],
                "href": "latra:list",
                "query": "expiry_status=active",
                "tone": "success",
                "hint": "Valid beyond 30 days",
            },
            {
                "label": "Expiring in 30 Days",
                "value": expiry_counter["expiring_in_30_days"],
                "href": "latra:list",
                "query": "expiry_status=expiring_in_30_days",
                "tone": "warning",
                "hint": "Follow up before the final week",
            },
            {
                "label": "Expiring in 7 Days",
                "value": expiry_counter["expiring_in_7_days"],
                "href": "latra:list",
                "query": "expiry_status=expiring_in_7_days",
                "tone": "danger",
                "hint": "High-priority renewal follow-up",
            },
            {
                "label": "Expires Today",
                "value": expiry_counter["expires_today"],
                "href": "latra:list",
                "query": "expiry_status=expires_today",
                "tone": "danger",
                "hint": "Contact today",
            },
            {
                "label": "Expired",
                "value": expiry_counter["expired"],
                "href": "latra:list",
                "query": "expiry_status=expired",
                "tone": "expired",
                "hint": "Already past expiry date",
            },
        ],
    }
