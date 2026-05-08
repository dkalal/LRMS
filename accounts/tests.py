from django.test import TestCase
from django.urls import reverse

from accounts.models import RoleChoices, User
from audit.models import AuditLog
from tenants.models import TenantCompany


class UserSoftDeleteTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.admin = User.objects.create_user(
            username="admin",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.ADMIN,
        )
        self.staff = User.objects.create_user(
            username="staff",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.RECEPTIONIST,
        )

    def test_user_deactivation_requires_reason_and_hides_from_active_list(self):
        self.client.login(username="admin", password="pass12345")
        confirm_response = self.client.get(reverse("accounts:user_archive", args=[self.staff.pk]))
        self.assertContains(confirm_response, "Reason")

        response = self.client.post(
            reverse("accounts:user_archive", args=[self.staff.pk]),
            {"reason": "Staff left the company"},
            follow=True,
        )
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)
        self.assertNotIn(self.staff, list(response.context["users"]))

        audit_log = AuditLog.objects.get(action="user.deactivated", object_id=self.staff.pk)
        self.assertEqual(audit_log.reason, "Staff left the company")

        inactive_response = self.client.get(reverse("accounts:user_list") + "?status=inactive")
        self.assertContains(inactive_response, "staff")

    def test_user_list_has_search_stats_and_table_controls(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("accounts:user_list"))

        self.assertContains(response, "Total Users")
        self.assertContains(response, "User Records")
        self.assertContains(response, "Search username, name, or email")
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_admin_cannot_deactivate_self(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("accounts:user_archive", args=[self.admin.pk]), follow=True)
        self.assertContains(response, "You cannot deactivate your own account.")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_user_can_be_restored(self):
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        self.client.login(username="admin", password="pass12345")
        self.client.post(reverse("accounts:user_restore", args=[self.staff.pk]))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
