from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import TenantAccessMixin
from audit.forms import ReasonForm
from audit.services import log_audit_event
from brokers.models import Broker
from brokers.services import find_possible_duplicate_brokers
from tenants.models import ActiveStatus

from .forms import CustomerForm, QuickBrokerForm
from .models import Customer
from .services import find_possible_duplicate_customers


class CustomerListView(TenantAccessMixin, ListView):
    model = Customer
    template_name = "customers/customer_list.html"
    context_object_name = "customers"
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE).strip()
        if status_filter not in ActiveStatus.values:
            status_filter = ActiveStatus.ACTIVE
        queryset = Customer.objects.filter(tenant=self.request.user.tenant).select_related("broker")
        queryset = queryset.filter(status=status_filter)
        if query:
            queryset = queryset.filter(
                Q(full_name__icontains=query)
                | Q(phone_number__icontains=query)
                | Q(alternative_phone__icontains=query)
                | Q(broker__full_name__icontains=query)
            )
        return queryset.order_by("full_name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE)
        context["status_filter"] = status_filter if status_filter in ActiveStatus.values else ActiveStatus.ACTIVE
        context["status_options"] = ActiveStatus.choices
        context["customer_columns"] = ["Customer", "Phone", "Broker", "Status", "Actions"]
        return context


def _add_customer_save_error(form):
    form.add_error(
        None,
        "We could not save this customer right now. Please review the details and try again.",
    )


def _add_quick_broker_save_error(form):
    form.add_error(
        None,
        "We could not save this broker right now. Please review the broker details and try again.",
    )


class CustomerCreateView(TenantAccessMixin, CreateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customers:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        broker_id = self.request.GET.get("broker")
        if broker_id:
            broker = Broker.objects.filter(tenant=self.request.user.tenant, pk=broker_id).first()
            if broker:
                initial["broker"] = broker
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault(
            "quick_broker_form",
            QuickBrokerForm(prefix="quick_broker", use_required_attribute=False),
        )
        context["is_customer_form"] = True
        context["form_title"] = "New Customer"
        context["form_subtitle"] = "Capture the minimum customer details needed for LATRA work."
        context.setdefault("duplicate_candidates", [])
        context.setdefault("quick_broker_duplicate_candidates", [])
        return context

    def post(self, request, *args, **kwargs):
        if "quick_broker_submit" in request.POST:
            self.object = None
            customer_form = self.get_form()
            quick_broker_form = QuickBrokerForm(
                request.POST,
                prefix="quick_broker",
                use_required_attribute=False,
            )
            if quick_broker_form.is_valid():
                duplicate_candidates = find_possible_duplicate_brokers(
                    request.user.tenant,
                    full_name=quick_broker_form.cleaned_data["full_name"],
                    phone_number=quick_broker_form.cleaned_data["phone_number"],
                )
                if duplicate_candidates and "quick_broker_save_anyway" not in request.POST:
                    return self.render_to_response(
                        self.get_context_data(
                            form=customer_form,
                            quick_broker_form=quick_broker_form,
                            quick_broker_duplicate_candidates=duplicate_candidates,
                        )
                    )
                broker = quick_broker_form.save(commit=False)
                broker.tenant = request.user.tenant
                broker.created_by = request.user
                broker.updated_by = request.user
                try:
                    broker.save()
                except (DatabaseError, IntegrityError):
                    _add_quick_broker_save_error(quick_broker_form)
                    return self.render_to_response(
                        self.get_context_data(
                            form=customer_form,
                            quick_broker_form=quick_broker_form,
                        )
                    )
                try:
                    log_audit_event(request.user, "broker.created", broker, "Broker quick-created from customer form.")
                    if duplicate_candidates:
                        log_audit_event(
                            request.user,
                            "broker.duplicate_override",
                            broker,
                            "Broker quick-created after duplicate warning override.",
                        )
                except DatabaseError:
                    messages.warning(request, "Broker saved, but the audit log could not be recorded.")
                mutable_data = request.POST.copy()
                mutable_data["broker"] = str(broker.pk)
                customer_form = self.form_class(mutable_data, tenant=request.user.tenant)
                messages.success(request, "Broker added. Continue saving the customer.")
                return self.render_to_response(
                    self.get_context_data(
                        form=customer_form,
                        quick_broker_form=QuickBrokerForm(
                            prefix="quick_broker",
                            use_required_attribute=False,
                        ),
                    )
                )
            return self.render_to_response(
                self.get_context_data(
                    form=customer_form,
                    quick_broker_form=quick_broker_form,
                )
            )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        duplicate_candidates = find_possible_duplicate_customers(
            self.request.user.tenant,
            full_name=form.cleaned_data["full_name"],
            phone_number=form.cleaned_data["phone_number"],
            broker=form.cleaned_data.get("broker"),
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
            _add_customer_save_error(form)
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "customer.created", self.object, "Customer created.")
        except DatabaseError:
            messages.warning(self.request, "Customer saved, but the audit log could not be recorded.")
        if duplicate_candidates:
            try:
                log_audit_event(
                    self.request.user,
                    "customer.duplicate_override",
                    self.object,
                    "Customer saved after duplicate warning override.",
                )
            except DatabaseError:
                messages.warning(self.request, "Duplicate override was saved, but audit logging failed.")
        messages.success(self.request, "Customer saved successfully.")
        return response


class CustomerUpdateView(TenantAccessMixin, UpdateView):
    model = Customer
    form_class = CustomerForm
    template_name = "customers/customer_form.html"
    success_url = reverse_lazy("customers:list")

    def get_queryset(self):
        return Customer.objects.filter(tenant=self.request.user.tenant)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault(
            "quick_broker_form",
            QuickBrokerForm(prefix="quick_broker", use_required_attribute=False),
        )
        context["is_customer_form"] = True
        context["form_title"] = "Edit Customer"
        context["form_subtitle"] = "Update customer contact details, broker relationship, or status."
        context.setdefault("duplicate_candidates", [])
        context.setdefault("quick_broker_duplicate_candidates", [])
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if "quick_broker_submit" in request.POST:
            customer_form = self.get_form()
            quick_broker_form = QuickBrokerForm(
                request.POST,
                prefix="quick_broker",
                use_required_attribute=False,
            )
            if quick_broker_form.is_valid():
                duplicate_candidates = find_possible_duplicate_brokers(
                    request.user.tenant,
                    full_name=quick_broker_form.cleaned_data["full_name"],
                    phone_number=quick_broker_form.cleaned_data["phone_number"],
                )
                if duplicate_candidates and "quick_broker_save_anyway" not in request.POST:
                    return self.render_to_response(
                        self.get_context_data(
                            form=customer_form,
                            quick_broker_form=quick_broker_form,
                            quick_broker_duplicate_candidates=duplicate_candidates,
                        )
                    )
                broker = quick_broker_form.save(commit=False)
                broker.tenant = request.user.tenant
                broker.created_by = request.user
                broker.updated_by = request.user
                try:
                    broker.save()
                except (DatabaseError, IntegrityError):
                    _add_quick_broker_save_error(quick_broker_form)
                    return self.render_to_response(
                        self.get_context_data(
                            form=customer_form,
                            quick_broker_form=quick_broker_form,
                        )
                    )
                try:
                    log_audit_event(request.user, "broker.created", broker, "Broker quick-created from customer form.")
                    if duplicate_candidates:
                        log_audit_event(
                            request.user,
                            "broker.duplicate_override",
                            broker,
                            "Broker quick-created after duplicate warning override.",
                        )
                except DatabaseError:
                    messages.warning(request, "Broker saved, but the audit log could not be recorded.")
                mutable_data = request.POST.copy()
                mutable_data["broker"] = str(broker.pk)
                customer_form = self.form_class(
                    mutable_data,
                    instance=self.object,
                    tenant=request.user.tenant,
                )
                messages.success(request, "Broker added. Continue saving the customer.")
                return self.render_to_response(
                    self.get_context_data(
                        form=customer_form,
                        quick_broker_form=QuickBrokerForm(
                            prefix="quick_broker",
                            use_required_attribute=False,
                        ),
                    )
                )
            return self.render_to_response(
                self.get_context_data(
                    form=customer_form,
                    quick_broker_form=quick_broker_form,
                )
            )
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        duplicate_candidates = find_possible_duplicate_customers(
            self.request.user.tenant,
            full_name=form.cleaned_data["full_name"],
            phone_number=form.cleaned_data["phone_number"],
            broker=form.cleaned_data.get("broker"),
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
            _add_customer_save_error(form)
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "customer.updated", self.object, "Customer updated.")
        except DatabaseError:
            messages.warning(self.request, "Customer updated, but the audit log could not be recorded.")
        if duplicate_candidates:
            try:
                log_audit_event(
                    self.request.user,
                    "customer.duplicate_override",
                    self.object,
                    "Customer updated after duplicate warning override.",
                )
            except DatabaseError:
                messages.warning(self.request, "Duplicate override was saved, but audit logging failed.")
        messages.success(self.request, "Customer updated successfully.")
        return response


@login_required
def archive_customer(request, pk):
    customer = Customer.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not customer:
        messages.error(request, "Customer was not found.")
        return redirect("customers:list")
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            customer.status = ActiveStatus.INACTIVE
            customer.updated_by = request.user
            customer.save(update_fields=["status", "updated_by", "updated_at"])
            log_audit_event(
                request.user,
                "customer.archived",
                customer,
                "Customer archived.",
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "Customer archived. History is preserved.")
            return redirect("customers:list")
    else:
        form = ReasonForm()
    return render(
        request,
        "shared/reason_confirm.html",
        {
            "form": form,
            "action_label": "Archive Customer",
            "object_label": customer.full_name,
            "help_text": "This hides the customer from daily lists but preserves linked history and audit records.",
            "warning_text": "Vehicles and LATRA records linked to this customer remain preserved for reporting and audit.",
            "cancel_url": reverse_lazy("customers:list"),
        },
    )


@login_required
@require_POST
def restore_customer(request, pk):
    customer = Customer.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not customer:
        messages.error(request, "Customer was not found.")
        return redirect("customers:list")
    customer.status = ActiveStatus.ACTIVE
    customer.updated_by = request.user
    customer.save(update_fields=["status", "updated_by", "updated_at"])
    log_audit_event(request.user, "customer.restored", customer, "Customer restored.")
    messages.success(request, "Customer restored.")
    return redirect("customers:list")
