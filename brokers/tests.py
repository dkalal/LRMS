from django.test import TestCase
from django.urls import reverse

from accounts.models import RoleChoices, User
from audit.models import AuditLog
from brokers.models import Broker
from tenants.models import TenantCompany


class BrokerWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.user = User.objects.create_user(
            username="admin",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.ADMIN,
        )

    def test_broker_archive_hides_from_default_list_and_can_restore(self):
        self.client.login(username="admin", password="pass12345")
        broker = Broker.objects.create(
            tenant=self.tenant,
            full_name="Wrong Broker",
            phone_number="255700000001",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("brokers:archive", args=[broker.pk]),
            {"reason": "Duplicate broker"},
            follow=True,
        )
        broker.refresh_from_db()
        self.assertEqual(broker.status, "inactive")
        self.assertNotContains(response, "Wrong Broker")

        archived_response = self.client.get(reverse("brokers:list") + "?status=inactive")
        self.assertContains(archived_response, "Wrong Broker")

        self.client.post(reverse("brokers:restore", args=[broker.pk]))
        broker.refresh_from_db()
        self.assertEqual(broker.status, "active")

    def test_broker_list_has_professional_table_controls(self):
        self.client.login(username="admin", password="pass12345")
        Broker.objects.create(
            tenant=self.tenant,
            full_name="Juma Broker",
            phone_number="255700000001",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.get(reverse("brokers:list"))

        self.assertContains(response, "Total Brokers")
        self.assertContains(response, "Broker Records")
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_broker_form_has_error_summary_and_sections(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("brokers:create"),
            {
                "full_name": "",
                "phone_number": "",
                "location": "",
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Broker Details")
        self.assertContains(response, "Optional Notes")

    def test_broker_duplicate_warning_uses_normalized_phone(self):
        self.client.login(username="admin", password="pass12345")
        Broker.objects.create(
            tenant=self.tenant,
            full_name="Juma Broker",
            phone_number="+255 700 000 001",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("brokers:create"),
            {
                "full_name": "Juma B.",
                "phone_number": "255700000001",
                "location": "",
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Possible duplicate found")
        self.assertContains(response, "Juma Broker")
        self.assertContains(response, "same phone")
        self.assertEqual(Broker.objects.filter(tenant=self.tenant).count(), 1)

    def test_broker_duplicate_override_saves_and_logs(self):
        self.client.login(username="admin", password="pass12345")
        Broker.objects.create(
            tenant=self.tenant,
            full_name="Juma Broker",
            phone_number="+255 700 000 001",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("brokers:create"),
            {
                "full_name": "Juma B.",
                "phone_number": "255700000001",
                "location": "",
                "notes": "",
                "status": "active",
                "save_anyway": "1",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("brokers:list"))
        self.assertEqual(Broker.objects.filter(tenant=self.tenant).count(), 2)
        self.assertTrue(AuditLog.objects.filter(action="broker.duplicate_override").exists())
