from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from django.views.generic import CreateView, FormView, ListView, UpdateView

from accounts.mixins import TenantAccessMixin
from accounts.services import filter_records_by_user_vehicle_permission
from audit.forms import ReasonForm
from audit.services import log_audit_event
from brokers.models import Broker
from customers.models import Customer
from vehicles.models import Vehicle

from .forms import LatraRecordForm, WhatsAppMessageForm
from .models import LatraRecord, LatraRecordStatus
from .services import (
    build_whatsapp_url,
    calculate_expiry_status,
    create_latra_record,
    apply_expiring_followup_filter,
    apply_expiry_status_filter,
    expiring_statuses,
    generate_whatsapp_message,
    get_contact_person,
    reminder_queryset_for_user,
    renew_latra_record,
    save_reminder_log,
)


class LatraRecordListView(TenantAccessMixin, ListView):
    model = LatraRecord
    template_name = "latra/record_list.html"
    context_object_name = "records"
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        queryset = reminder_queryset_for_user(self.request.user)
        status_filter = self.request.GET.get("expiry_status", "").strip()
        record_state = self.request.GET.get("record_state", "operational").strip()
        if record_state == LatraRecordStatus.CANCELLED:
            queryset = queryset.filter(status=LatraRecordStatus.CANCELLED)
        elif record_state in {LatraRecordStatus.ACTIVE, LatraRecordStatus.RENEWED}:
            queryset = queryset.filter(status=record_state)
        elif record_state == "operational":
            queryset = queryset.exclude(status=LatraRecordStatus.CANCELLED)
        if query:
            queryset = queryset.filter(
                Q(customer__full_name__icontains=query)
                | Q(vehicle__plate_number__icontains=query)
                | Q(service_name__icontains=query)
                | Q(broker__full_name__icontains=query)
            )
        if status_filter:
            queryset = apply_expiry_status_filter(queryset, status_filter)
        return queryset.select_related("customer", "vehicle", "broker").order_by("expiry_date", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["expiry_statuses"] = [
            "active",
            "expiring_in_30_days",
            "expiring_in_7_days",
            "expires_today",
            "expired",
            "renewed",
            "cancelled",
        ]
        context["record_state"] = self.request.GET.get("record_state", "operational")
        context["record_state_options"] = [
            ("operational", "Operational"),
            (LatraRecordStatus.ACTIVE, "Active Records"),
            (LatraRecordStatus.RENEWED, "Renewed History"),
            (LatraRecordStatus.CANCELLED, "Cancelled"),
            ("all", "All Records"),
        ]
        context["record_status"] = {record.pk: calculate_expiry_status(record) for record in context["records"]}
        context["latra_columns"] = ["Plate", "Customer", "Service", "Issue", "Expiry", "Status", "Actions"]
        today = timezone.localdate()
        base_queryset = reminder_queryset_for_user(self.request.user)
        context["latra_stats"] = {
            "total": base_queryset.count(),
            "active": base_queryset.filter(status=LatraRecordStatus.ACTIVE, expiry_date__gt=today + timedelta(days=30)).count(),
            "expiring": apply_expiring_followup_filter(base_queryset).count(),
            "expired": apply_expiry_status_filter(base_queryset, "expired").count(),
            "cancelled": base_queryset.filter(status=LatraRecordStatus.CANCELLED).count(),
        }
        return context


def _lookup_customer_label(customer):
    if not customer:
        return ""
    phone = customer.phone_number or "No phone"
    return f"{customer.full_name} · {phone}"


def _lookup_vehicle_label(vehicle):
    if not vehicle:
        return ""
    return f"{vehicle.plate_number} · {vehicle.customer.full_name} · {vehicle.get_vehicle_category_display()}"


def _lookup_broker_label(broker):
    if not broker:
        return ""
    return f"{broker.full_name} · {broker.phone_number}"


def _selected_lookup_context(form, user):
    data = {}
    for field_name, model, label_func in (
        ("customer", Customer, _lookup_customer_label),
        ("vehicle", Vehicle, _lookup_vehicle_label),
        ("broker", Broker, _lookup_broker_label),
    ):
        pk = form.data.get(field_name) if form.is_bound else form.initial.get(field_name)
        if not pk and getattr(form.instance, f"{field_name}_id", None):
            pk = getattr(form.instance, f"{field_name}_id")
        if not pk:
            data[f"selected_{field_name}_label"] = ""
            continue
        queryset = model.objects.filter(tenant=user.tenant)
        if field_name == "vehicle":
            vehicle_queryset = Vehicle.objects.filter(tenant=user.tenant)
            if not (user.is_superuser or user.has_all_vehicle_access()):
                vehicle_queryset = vehicle_queryset.filter(vehicle_category__in=user.assigned_vehicle_categories())
            item = vehicle_queryset.select_related("customer").filter(pk=pk).first()
        else:
            item = queryset.filter(pk=pk).first()
        data[f"selected_{field_name}_label"] = label_func(item)
    return data


def _vehicle_queryset_for_latra_user(user):
    queryset = Vehicle.objects.filter(tenant=user.tenant).select_related("customer", "customer__broker")
    if user.is_superuser or user.has_all_vehicle_access():
        return queryset
    return queryset.filter(vehicle_category__in=user.assigned_vehicle_categories())


@login_required
@require_GET
def customer_lookup(request):
    query = request.GET.get("q", "").strip()
    broker_id = request.GET.get("broker", "").strip()
    queryset = Customer.objects.filter(tenant=request.user.tenant).select_related("broker")
    if broker_id.isdigit():
        queryset = queryset.filter(broker_id=broker_id)
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(broker__full_name__icontains=query)
        )
    results = []
    for customer in queryset.order_by("full_name")[:20]:
        broker = customer.broker
        results.append(
            {
                "id": customer.pk,
                "label": _lookup_customer_label(customer),
                "name": customer.full_name,
                "phone": customer.phone_number,
                "broker": (
                    {
                        "id": broker.pk,
                        "label": _lookup_broker_label(broker),
                        "name": broker.full_name,
                        "phone": broker.phone_number,
                    }
                    if broker
                    else None
                ),
            }
        )
    return JsonResponse({"results": results})


@login_required
@require_GET
def vehicle_lookup(request):
    query = request.GET.get("q", "").strip()
    customer_id = request.GET.get("customer", "").strip()
    queryset = _vehicle_queryset_for_latra_user(request.user)
    if customer_id.isdigit():
        queryset = queryset.filter(customer_id=customer_id)
    if query:
        queryset = queryset.filter(
            Q(plate_number__icontains=query)
            | Q(customer__full_name__icontains=query)
            | Q(vehicle_category__icontains=query)
        )
    results = []
    for vehicle in queryset.order_by("plate_number")[:20]:
        customer = vehicle.customer
        broker = customer.broker
        results.append(
            {
                "id": vehicle.pk,
                "label": _lookup_vehicle_label(vehicle),
                "plate": vehicle.plate_number,
                "category": vehicle.get_vehicle_category_display(),
                "customer": {
                    "id": customer.pk,
                    "label": _lookup_customer_label(customer),
                    "name": customer.full_name,
                    "phone": customer.phone_number,
                },
                "broker": (
                    {
                        "id": broker.pk,
                        "label": _lookup_broker_label(broker),
                        "name": broker.full_name,
                        "phone": broker.phone_number,
                    }
                    if broker
                    else None
                ),
            }
        )
    return JsonResponse({"results": results})


@login_required
@require_GET
def broker_lookup(request):
    query = request.GET.get("q", "").strip()
    queryset = Broker.objects.filter(tenant=request.user.tenant)
    if query:
        queryset = queryset.filter(
            Q(full_name__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(location__icontains=query)
        )
    results = [
        {
            "id": broker.pk,
            "label": _lookup_broker_label(broker),
            "name": broker.full_name,
            "phone": broker.phone_number,
        }
        for broker in queryset.order_by("full_name")[:20]
    ]
    return JsonResponse({"results": results})


class LatraRecordCreateView(TenantAccessMixin, CreateView):
    model = LatraRecord
    form_class = LatraRecordForm
    template_name = "latra/latra_form.html"
    success_url = reverse_lazy("latra:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "New LATRA Record"
        context["form_subtitle"] = "Capture the customer, vehicle, service name, and renewal dates."
        context["customer_count"] = context["form"].fields["customer"].queryset.count()
        context["vehicle_count"] = context["form"].fields["vehicle"].queryset.count()
        context.update(_selected_lookup_context(context["form"], self.request.user))
        return context

    def form_valid(self, form):
        self.object = create_latra_record(user=self.request.user, **form.cleaned_data)
        messages.success(self.request, "LATRA record created successfully.")
        return redirect(self.get_success_url())


class LatraRecordUpdateView(TenantAccessMixin, UpdateView):
    model = LatraRecord
    form_class = LatraRecordForm
    template_name = "latra/latra_form.html"
    success_url = reverse_lazy("latra:list")

    def get_queryset(self):
        return filter_records_by_user_vehicle_permission(
            LatraRecord.objects.select_related("vehicle"),
            self.request.user,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Edit LATRA Record"
        context["form_subtitle"] = "Update service, dates, broker fallback, notes, or record status."
        context["customer_count"] = context["form"].fields["customer"].queryset.count()
        context["vehicle_count"] = context["form"].fields["vehicle"].queryset.count()
        context.update(_selected_lookup_context(context["form"], self.request.user))
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "LATRA record updated successfully.")
        return super().form_valid(form)


class LatraRenewView(TenantAccessMixin, FormView):
    form_class = LatraRecordForm
    template_name = "latra/renew_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.record = filter_records_by_user_vehicle_permission(
            LatraRecord.objects.select_related("vehicle", "customer", "broker"),
            request.user,
        ).filter(pk=kwargs["pk"]).first()
        if not self.record:
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["customer"].initial = self.record.customer
        form.fields["vehicle"].initial = self.record.vehicle
        form.fields["broker"].initial = self.record.broker
        form.fields["service_name"].initial = self.record.service_name
        form.fields["status"].initial = LatraRecordStatus.ACTIVE
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        renew_latra_record(
            self.record,
            user=self.request.user,
            issue_date=form.cleaned_data["issue_date"],
            expiry_date=form.cleaned_data["expiry_date"],
            notes=form.cleaned_data["notes"],
        )
        messages.success(self.request, "LATRA record renewed successfully.")
        return redirect("latra:list")


class WhatsAppPreviewView(TenantAccessMixin, FormView):
    form_class = WhatsAppMessageForm
    template_name = "latra/whatsapp_preview.html"

    def dispatch(self, request, *args, **kwargs):
        self.record = filter_records_by_user_vehicle_permission(
            LatraRecord.objects.select_related("customer", "vehicle", "broker"),
            request.user,
        ).filter(pk=kwargs["pk"]).first()
        if not self.record:
            raise Http404
        self.contact = get_contact_person(self.record)
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return {"message": generate_whatsapp_message(self.record, self.contact)}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["record"] = self.record
        context["contact"] = self.contact
        context["missing_contact"] = not self.contact["phone_number"]
        return context

    def form_valid(self, form):
        message = form.cleaned_data["message"]
        save_reminder_log(self.record, self.request.user, message)
        if not self.contact["phone_number"]:
            messages.warning(self.request, "No contact phone number is available for this record.")
            return redirect("latra:list")
        return redirect(build_whatsapp_url(self.contact["phone_number"], message))


class ReminderStatusListView(LoginRequiredMixin, ListView):
    model = LatraRecord
    template_name = "reminders/reminder_list.html"
    context_object_name = "records"
    paginate_by = 10

    def get_queryset(self):
        status_name = self.kwargs["status_name"]
        query = self.request.GET.get("q", "").strip()
        if status_name == "expiring":
            queryset = apply_expiring_followup_filter(
                reminder_queryset_for_user(self.request.user)
            )
        elif status_name == "expired":
            queryset = apply_expiry_status_filter(
                reminder_queryset_for_user(self.request.user),
                "expired",
            )
        else:
            queryset = reminder_queryset_for_user(self.request.user)
        if query:
            queryset = queryset.filter(
                Q(customer__full_name__icontains=query)
                | Q(vehicle__plate_number__icontains=query)
                | Q(service_name__icontains=query)
                | Q(broker__full_name__icontains=query)
            )
        return queryset.order_by("expiry_date", "-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_name"] = self.kwargs["status_name"]
        context["record_status"] = {record.pk: calculate_expiry_status(record) for record in context["records"]}
        context["contact_info"] = {record.pk: get_contact_person(record) for record in context["records"]}
        context["reminder_columns"] = ["Plate", "Customer", "Contact", "Service", "Expiry", "Status", "Action"]
        return context


@login_required
def cancel_latra_record(request, pk):
    record = filter_records_by_user_vehicle_permission(
        LatraRecord.objects.select_related("vehicle"),
        request.user,
    ).filter(pk=pk).first()
    if not record:
        messages.error(request, "LATRA record was not found.")
        return redirect("latra:list")
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            record.status = LatraRecordStatus.CANCELLED
            record.updated_by = request.user
            record.save(update_fields=["status", "updated_by", "updated_at"])
            log_audit_event(
                request.user,
                "latra.cancelled",
                record,
                "LATRA record cancelled.",
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "LATRA record cancelled. History is preserved.")
            return redirect("latra:list")
    else:
        form = ReasonForm()
    return render(
        request,
        "shared/reason_confirm.html",
        {
            "form": form,
            "action_label": "Cancel LATRA Record",
            "object_label": str(record),
            "help_text": "This removes the record from operational lists while preserving renewal and audit history.",
            "cancel_url": reverse_lazy("latra:list"),
        },
    )


@login_required
@require_POST
def restore_latra_record(request, pk):
    record = filter_records_by_user_vehicle_permission(
        LatraRecord.objects.select_related("vehicle"),
        request.user,
    ).filter(pk=pk).first()
    if not record:
        messages.error(request, "LATRA record was not found.")
        return redirect("latra:list")
    record.status = LatraRecordStatus.ACTIVE
    record.updated_by = request.user
    record.save(update_fields=["status", "updated_by", "updated_at"])
    log_audit_event(request.user, "latra.restored", record, "LATRA record restored.")
    messages.success(request, "LATRA record restored as active.")
    return redirect("latra:list")
from datetime import timedelta
