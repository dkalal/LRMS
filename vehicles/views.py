from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import TenantAccessMixin
from accounts.models import RoleChoices, VehicleCategoryChoices
from accounts.services import enforce_vehicle_category_access
from audit.forms import ReasonForm
from audit.services import log_audit_event
from tenants.models import ActiveStatus

from .forms import VehicleForm
from .models import Vehicle


class VehicleListView(TenantAccessMixin, ListView):
    model = Vehicle
    template_name = "vehicles/vehicle_list.html"
    context_object_name = "vehicles"
    paginate_by = 10

    def get_queryset(self):
        query = self.request.GET.get("q", "").strip()
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE).strip()
        category_filter = self.request.GET.get("category", "").strip()
        if status_filter not in ActiveStatus.values:
            status_filter = ActiveStatus.ACTIVE
        queryset = Vehicle.objects.filter(tenant=self.request.user.tenant).select_related("customer")
        queryset = queryset.filter(status=status_filter)
        if not self.request.user.has_all_vehicle_access() and not self.request.user.is_superuser:
            categories = self.request.user.assigned_vehicle_categories()
            queryset = queryset.filter(vehicle_category__in=categories)
        if category_filter and category_filter != VehicleCategoryChoices.ALL:
            queryset = queryset.filter(vehicle_category=category_filter)
        if query:
            queryset = queryset.filter(
                Q(plate_number__icontains=query)
                | Q(customer__full_name__icontains=query)
                | Q(vehicle_category__icontains=query)
            )
        return queryset.order_by("plate_number")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get("status", ActiveStatus.ACTIVE)
        category_filter = self.request.GET.get("category", "")
        allowed_categories = [
            choice
            for choice in VehicleCategoryChoices.choices
            if choice[0] != VehicleCategoryChoices.ALL
        ]
        if not self.request.user.is_superuser and not self.request.user.has_all_vehicle_access() and self.request.user.role != RoleChoices.ADMIN:
            assigned = set(self.request.user.assigned_vehicle_categories())
            allowed_categories = [choice for choice in allowed_categories if choice[0] in assigned]
        context["status_filter"] = status_filter if status_filter in ActiveStatus.values else ActiveStatus.ACTIVE
        context["category_filter"] = category_filter if category_filter in [value for value, _label in allowed_categories] else ""
        context["status_options"] = ActiveStatus.choices
        context["category_options"] = allowed_categories
        context["vehicle_columns"] = ["Plate", "Customer", "Category", "Status", "Actions"]
        permitted_queryset = Vehicle.objects.filter(tenant=self.request.user.tenant)
        if not self.request.user.is_superuser and not self.request.user.has_all_vehicle_access() and self.request.user.role != RoleChoices.ADMIN:
            permitted_queryset = permitted_queryset.filter(vehicle_category__in=self.request.user.assigned_vehicle_categories())
        context["vehicle_stats"] = {
            "total": permitted_queryset.count(),
            "active": permitted_queryset.filter(status=ActiveStatus.ACTIVE).count(),
            "inactive": permitted_queryset.filter(status=ActiveStatus.INACTIVE).count(),
        }
        return context


class VehicleCreateView(TenantAccessMixin, CreateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "vehicles/vehicle_form.html"
    success_url = reverse_lazy("vehicles:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "New Vehicle"
        context["form_subtitle"] = "Register the plate and category before creating LATRA records."
        context["customer_count"] = context["form"].fields["customer"].queryset.count()
        return context

    def form_valid(self, form):
        try:
            enforce_vehicle_category_access(None, self.request.user, form.cleaned_data["vehicle_category"])
        except PermissionDenied:
            form.add_error("vehicle_category", "You do not have permission for this vehicle category.")
            return self.form_invalid(form)
        if Vehicle.objects.filter(
            tenant=self.request.user.tenant,
            plate_number=form.cleaned_data["plate_number"],
        ).exists():
            form.add_error("plate_number", "This plate already exists for this tenant.")
            return self.form_invalid(form)
        form.instance.tenant = self.request.user.tenant
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        try:
            response = super().form_valid(form)
        except (DatabaseError, IntegrityError):
            form.add_error("plate_number", "This plate already exists for this tenant.")
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "vehicle.created", self.object, "Vehicle created.")
        except DatabaseError:
            messages.warning(self.request, "Vehicle saved, but the audit log could not be recorded.")
        messages.success(self.request, "Vehicle saved successfully.")
        return response


class VehicleUpdateView(TenantAccessMixin, UpdateView):
    model = Vehicle
    form_class = VehicleForm
    template_name = "vehicles/vehicle_form.html"
    success_url = reverse_lazy("vehicles:list")

    def get_queryset(self):
        queryset = Vehicle.objects.filter(tenant=self.request.user.tenant)
        if self.request.user.is_superuser or self.request.user.has_all_vehicle_access():
            return queryset
        return queryset.filter(vehicle_category__in=self.request.user.assigned_vehicle_categories())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tenant"] = self.request.user.tenant
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Edit Vehicle"
        context["form_subtitle"] = "Update vehicle ownership, plate details, category, or archive status."
        context["customer_count"] = context["form"].fields["customer"].queryset.count()
        return context

    def form_valid(self, form):
        try:
            enforce_vehicle_category_access(None, self.request.user, form.cleaned_data["vehicle_category"])
        except PermissionDenied:
            form.add_error("vehicle_category", "You do not have permission for this vehicle category.")
            return self.form_invalid(form)
        if Vehicle.objects.filter(
            tenant=self.request.user.tenant,
            plate_number=form.cleaned_data["plate_number"],
        ).exclude(pk=self.object.pk).exists():
            form.add_error("plate_number", "This plate already exists for this tenant.")
            return self.form_invalid(form)
        form.instance.updated_by = self.request.user
        try:
            response = super().form_valid(form)
        except (DatabaseError, IntegrityError):
            form.add_error("plate_number", "This plate already exists for this tenant.")
            return self.form_invalid(form)
        try:
            log_audit_event(self.request.user, "vehicle.updated", self.object, "Vehicle updated.")
        except DatabaseError:
            messages.warning(self.request, "Vehicle updated, but the audit log could not be recorded.")
        messages.success(self.request, "Vehicle updated successfully.")
        return response


def vehicle_queryset_for_user(user):
    queryset = Vehicle.objects.filter(tenant=user.tenant)
    if user.is_superuser or user.has_all_vehicle_access():
        return queryset
    return queryset.filter(vehicle_category__in=user.assigned_vehicle_categories())


@login_required
def archive_vehicle(request, pk):
    vehicle = vehicle_queryset_for_user(request.user).filter(pk=pk).first()
    if not vehicle:
        messages.error(request, "Vehicle was not found.")
        return redirect("vehicles:list")
    if vehicle.latra_records.exclude(status="cancelled").exists():
        messages.error(request, "Cancel related LATRA records before archiving this vehicle.")
        return redirect("vehicles:list")
    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            vehicle.status = ActiveStatus.INACTIVE
            vehicle.updated_by = request.user
            vehicle.save(update_fields=["status", "updated_by", "updated_at"])
            log_audit_event(
                request.user,
                "vehicle.archived",
                vehicle,
                "Vehicle archived.",
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "Vehicle archived. History is preserved.")
            return redirect("vehicles:list")
    else:
        form = ReasonForm()
    return render(
        request,
        "shared/reason_confirm.html",
        {
            "form": form,
            "action_label": "Archive Vehicle",
            "object_label": vehicle.plate_number,
            "help_text": "This hides the vehicle from daily lists after related LATRA records are cancelled.",
            "cancel_url": reverse_lazy("vehicles:list"),
        },
    )


@login_required
@require_POST
def restore_vehicle(request, pk):
    vehicle = vehicle_queryset_for_user(request.user).filter(pk=pk).first()
    if not vehicle:
        messages.error(request, "Vehicle was not found.")
        return redirect("vehicles:list")
    vehicle.status = ActiveStatus.ACTIVE
    vehicle.updated_by = request.user
    vehicle.save(update_fields=["status", "updated_by", "updated_at"])
    log_audit_event(request.user, "vehicle.restored", vehicle, "Vehicle restored.")
    messages.success(request, "Vehicle restored.")
    return redirect("vehicles:list")
