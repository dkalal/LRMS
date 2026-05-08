from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import ReportAccessMixin, TenantAccessMixin
from audit.forms import ReasonForm
from audit.services import log_audit_event
from tenants.models import ActiveStatus

from .forms import BrokerForm
from .models import Broker
from .services import find_possible_duplicate_brokers, get_broker_statistics


class BrokerListView(TenantAccessMixin, ListView):
    model = Broker
    template_name = "brokers/broker_list.html"
    context_object_name = "brokers"
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE).strip()
        if status_filter not in ActiveStatus.values:
            status_filter = ActiveStatus.ACTIVE
        queryset = Broker.objects.filter(tenant=self.request.user.tenant).annotate(customer_count=Count("customer")).order_by("full_name")
        queryset = queryset.filter(status=status_filter)
        if query:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(location__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE)
        context["status_filter"] = status_filter if status_filter in ActiveStatus.values else ActiveStatus.ACTIVE
        context["status_options"] = ActiveStatus.choices
        context["broker_columns"] = ["Broker", "Phone", "Location", "Customers", "Status", "Actions"]
        stats = Broker.objects.filter(tenant=self.request.user.tenant).aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(status=ActiveStatus.ACTIVE)),
            inactive=Count("id", filter=Q(status=ActiveStatus.INACTIVE)),
        )
        context["broker_stats"] = stats
        return context


class BrokerCreateView(TenantAccessMixin, CreateView):
    model = Broker
    form_class = BrokerForm
    template_name = "brokers/broker_form.html"
    success_url = reverse_lazy("brokers:list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("duplicate_candidates", [])
        context["form_title"] = "New Broker"
        context["form_subtitle"] = "Add a broker once, then reuse them from customer and LATRA records."
        return context

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        duplicate_candidates = find_possible_duplicate_brokers(
            self.request.user.tenant,
            full_name=form.cleaned_data["full_name"],
            phone_number=form.cleaned_data["phone_number"],
        )
        if duplicate_candidates and "save_anyway" not in self.request.POST:
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    duplicate_candidates=duplicate_candidates,
                )
            )
        try:
            response = super().form_valid(form)
        except (DatabaseError, IntegrityError):
            form.add_error(None, "We could not save this broker right now. Please review the details and try again.")
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "broker.created", self.object, "Broker created.")
            if duplicate_candidates:
                log_audit_event(
                    self.request.user,
                    "broker.duplicate_override",
                    self.object,
                    "Broker saved after duplicate warning override.",
                )
        except DatabaseError:
            messages.warning(self.request, "Broker saved, but the audit log could not be recorded.")
        messages.success(self.request, "Broker saved successfully.")
        return response


class BrokerUpdateView(TenantAccessMixin, UpdateView):
    model = Broker
    form_class = BrokerForm
    template_name = "brokers/broker_form.html"
    success_url = reverse_lazy("brokers:list")

    def get_queryset(self):
        return Broker.objects.filter(tenant=self.request.user.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("duplicate_candidates", [])
        context["form_title"] = "Edit Broker"
        context["form_subtitle"] = "Update broker contact details without losing linked customer history."
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        duplicate_candidates = find_possible_duplicate_brokers(
            self.request.user.tenant,
            full_name=form.cleaned_data["full_name"],
            phone_number=form.cleaned_data["phone_number"],
            exclude_pk=self.object.pk,
        )
        if duplicate_candidates and "save_anyway" not in self.request.POST:
            return self.render_to_response(
                self.get_context_data(
                    form=form,
                    duplicate_candidates=duplicate_candidates,
                )
            )
        try:
            response = super().form_valid(form)
        except (DatabaseError, IntegrityError):
            form.add_error(None, "We could not save this broker right now. Please review the details and try again.")
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "broker.updated", self.object, "Broker updated.")
            if duplicate_candidates:
                log_audit_event(
                    self.request.user,
                    "broker.duplicate_override",
                    self.object,
                    "Broker updated after duplicate warning override.",
                )
        except DatabaseError:
            messages.warning(self.request, "Broker updated, but the audit log could not be recorded.")
        messages.success(self.request, "Broker updated successfully.")
        return response


class BrokerReportListView(ReportAccessMixin, ListView):
    model = Broker
    template_name = "brokers/broker_reports.html"
    context_object_name = "brokers"

    def get_queryset(self):
        return Broker.objects.filter(tenant=self.request.user.tenant).order_by("full_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["broker_stats"] = [
            (broker, get_broker_statistics(broker, self.request.user))
            for broker in context["brokers"]
        ]
        return context


@login_required
def archive_broker(request, pk):
    broker = Broker.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not broker:
        messages.error(request, "Broker was not found.")
        return redirect("brokers:list")
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            broker.status = ActiveStatus.INACTIVE
            broker.updated_by = request.user
            broker.save(update_fields=["status", "updated_by", "updated_at"])
            log_audit_event(
                request.user,
                "broker.archived",
                broker,
                "Broker archived.",
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "Broker archived. Linked customer history is preserved.")
            return redirect("brokers:list")
    else:
        form = ReasonForm()
    return render(
        request,
        "shared/reason_confirm.html",
        {
            "form": form,
            "action_label": "Archive Broker",
            "object_label": broker.full_name,
            "help_text": "This hides the broker from daily lists but preserves customer and LATRA history.",
            "cancel_url": reverse_lazy("brokers:list"),
        },
    )


@login_required
@require_POST
def restore_broker(request, pk):
    broker = Broker.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not broker:
        messages.error(request, "Broker was not found.")
        return redirect("brokers:list")
    broker.status = ActiveStatus.ACTIVE
    broker.updated_by = request.user
    broker.save(update_fields=["status", "updated_by", "updated_at"])
    log_audit_event(request.user, "broker.restored", broker, "Broker restored.")
    messages.success(request, "Broker restored.")
    return redirect("brokers:list")
