from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView

from audit.forms import ReasonForm
from audit.services import log_audit_event

from .forms import UserForm, UserVehiclePermissionForm
from .mixins import AdminRequiredMixin
from .models import User, UserVehiclePermission


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/user_list.html"
    context_object_name = "users"
    paginate_by = 10

    def get_queryset(self):
        status_filter = self.request.GET.get("status", "active")
        query = self.request.GET.get("q", "").strip()
        queryset = User.objects.filter(tenant=self.request.user.tenant).prefetch_related("vehicle_permissions")
        if status_filter == "inactive":
            queryset = queryset.filter(is_active=False)
        elif status_filter == "all":
            pass
        else:
            queryset = queryset.filter(is_active=True)
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(email__icontains=query)
            )
        return queryset.order_by("username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status_filter = self.request.GET.get("status", "active")
        context["status_filter"] = status_filter if status_filter in {"active", "inactive", "all"} else "active"
        context["status_options"] = [
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("all", "All Users"),
        ]
        tenant_users = User.objects.filter(tenant=self.request.user.tenant)
        context["user_stats"] = tenant_users.aggregate(
            total=Count("id"),
            active=Count("id", filter=Q(is_active=True)),
            inactive=Count("id", filter=Q(is_active=False)),
        )
        context["user_columns"] = ["Username", "Name", "Role", "Vehicle Categories", "Active", "Actions"]
        context["user_categories"] = {
            user.pk: ", ".join(permission.vehicle_category for permission in user.vehicle_permissions.all()) or "-"
            for user in context["users"]
        }
        return context


class UserCreateView(AdminRequiredMixin, CreateView):
    form_class = UserForm
    template_name = "accounts/user_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.tenant = self.request.user.tenant
        self.object.save(update_fields=["tenant"])
        categories = form.cleaned_data["vehicle_categories"]
        UserVehiclePermission.objects.filter(user=self.object).delete()
        for category in categories:
            UserVehiclePermission.objects.create(
                tenant=self.request.user.tenant,
                user=self.object,
                vehicle_category=category,
            )
        messages.success(self.request, "User created successfully.")
        return response


class UserVehiclePermissionCreateView(AdminRequiredMixin, CreateView):
    form_class = UserVehiclePermissionForm
    template_name = "accounts/permission_form.html"
    success_url = reverse_lazy("accounts:user_list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["user"].queryset = User.objects.filter(tenant=self.request.user.tenant)
        return form

    def form_valid(self, form):
        form.instance.tenant = self.request.user.tenant
        messages.success(self.request, "Vehicle permission assigned.")
        return super().form_valid(form)


def accounts_home_redirect(request):
    return redirect("accounts:user_list")


def ensure_user_admin(request):
    if not request.user.is_authenticated:
        raise PermissionDenied("Login required.")
    if not request.user.is_superuser and not request.user.can_manage_users():
        raise PermissionDenied("Admin access is required.")


@login_required
def archive_user(request, pk):
    ensure_user_admin(request)
    target_user = User.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not target_user:
        messages.error(request, "User was not found.")
        return redirect("accounts:user_list")
    if target_user.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("accounts:user_list")

    if request.method == "POST":
        form = ReasonForm(request.POST)
        if form.is_valid():
            target_user.is_active = False
            target_user.save(update_fields=["is_active"])
            log_audit_event(
                request.user,
                "user.deactivated",
                target_user,
                "User deactivated.",
                reason=form.cleaned_data["reason"],
            )
            messages.success(request, "User deactivated. Their record and audit history are preserved.")
            return redirect("accounts:user_list")
    else:
        form = ReasonForm()

    return render(
        request,
        "shared/reason_confirm.html",
        {
            "form": form,
            "action_label": "Deactivate User",
            "object_label": target_user.username,
            "help_text": "This prevents login but preserves ownership and audit history for records created by this user.",
            "cancel_url": reverse_lazy("accounts:user_list"),
        },
    )


@login_required
@require_POST
def restore_user(request, pk):
    ensure_user_admin(request)
    target_user = User.objects.filter(tenant=request.user.tenant, pk=pk).first()
    if not target_user:
        messages.error(request, "User was not found.")
        return redirect("accounts:user_list")
    target_user.is_active = True
    target_user.save(update_fields=["is_active"])
    log_audit_event(request.user, "user.reactivated", target_user, "User reactivated.")
    messages.success(request, "User reactivated.")
    return redirect("accounts:user_list")
