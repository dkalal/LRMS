from django.test import TestCase
from django.urls import reverse

from accounts.models import RoleChoices, User
from audit.models import AuditLog
from brokers.models import Broker
from customers.forms import CustomerForm
from customers.models import Customer
from tenants.models import TenantCompany


class CustomerFormWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.user = User.objects.create_user(
            username="admin",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.ADMIN,
        )

    def test_customer_form_omits_alternative_phone(self):
        form = CustomerForm(tenant=self.tenant)
        self.assertNotIn("alternative_phone", form.fields)

    def test_customer_create_page_has_quick_broker_flow(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("customers:create"))
        self.assertContains(response, "Add broker")
        self.assertContains(response, "Customer Details")
        self.assertContains(response, "Broker Relationship")
        self.assertContains(response, "sticky bottom-0")
        self.assertNotContains(response, "Alternative phone")
        self.assertContains(response, 'data-required-when-visible="true"')
        self.assertNotContains(response, 'name="quick_broker-full_name" maxlength="255" required')

    def test_customer_create_validation_errors_are_actionable(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "",
                "phone_number": "",
                "broker": "",
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Review the highlighted fields below")
        self.assertContains(response, "Full name:")
        self.assertContains(response, "Error: This field is required.")

    def test_quick_broker_validation_errors_keep_panel_open(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "New Customer",
                "phone_number": "",
                "broker": "",
                "notes": "",
                "status": "active",
                "quick_broker-full_name": "",
                "quick_broker-phone_number": "",
                "quick_broker-location": "",
                "quick_broker_submit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Broker name:")
        self.assertContains(response, "Broker phone:")
        self.assertContains(response, 'id="quick-broker-panel" class=" mt-4')

    def test_quick_broker_create_keeps_user_on_customer_form(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "New Customer",
                "phone_number": "",
                "broker": "",
                "notes": "Reached via broker",
                "status": "active",
                "quick_broker-full_name": "New Broker",
                "quick_broker-phone_number": "255700123456",
                "quick_broker-location": "Arusha",
                "quick_broker_submit": "1",
            },
        )

        broker = Broker.objects.get(full_name="New Broker")
        self.assertEqual(broker.tenant, self.tenant)
        self.assertFalse(Customer.objects.filter(full_name="New Customer").exists())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Broker added. Continue saving the customer.")
        self.assertContains(response, f'value="{broker.pk}" selected')

    def test_customer_duplicate_warning_is_tenant_scoped_and_uses_phone(self):
        self.client.login(username="admin", password="pass12345")
        other_tenant = TenantCompany.objects.create(name="Tenant B", slug="tenant-b")
        Customer.objects.create(
            tenant=other_tenant,
            full_name="Other Tenant Customer",
            phone_number="255700123456",
        )
        Customer.objects.create(
            tenant=self.tenant,
            full_name="Existing Customer",
            phone_number="+255 700 123 456",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "Different Name",
                "phone_number": "255700123456",
                "broker": "",
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Possible duplicate found")
        self.assertContains(response, "Existing Customer")
        self.assertNotContains(response, "Other Tenant Customer")
        self.assertEqual(Customer.objects.filter(tenant=self.tenant).count(), 1)

    def test_customer_duplicate_override_saves_and_logs(self):
        self.client.login(username="admin", password="pass12345")
        Customer.objects.create(
            tenant=self.tenant,
            full_name="Existing Customer",
            phone_number="255700123456",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "Different Name",
                "phone_number": "+255 700 123 456",
                "broker": "",
                "notes": "",
                "status": "active",
                "save_anyway": "1",
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("customers:list"))
        self.assertEqual(Customer.objects.filter(tenant=self.tenant).count(), 2)
        self.assertTrue(AuditLog.objects.filter(action="customer.duplicate_override").exists())

    def test_quick_broker_duplicate_warning_stays_in_customer_form(self):
        self.client.login(username="admin", password="pass12345")
        Broker.objects.create(
            tenant=self.tenant,
            full_name="Known Broker",
            phone_number="255711000111",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("customers:create"),
            {
                "full_name": "New Customer",
                "phone_number": "",
                "broker": "",
                "notes": "",
                "status": "active",
                "quick_broker-full_name": "Known Broker",
                "quick_broker-phone_number": "+255 711 000 111",
                "quick_broker-location": "",
                "quick_broker_submit": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Possible duplicate found")
        self.assertContains(response, "Known Broker")
        self.assertEqual(Broker.objects.filter(tenant=self.tenant).count(), 1)

    def test_customer_archive_hides_from_default_list_and_can_restore(self):
        self.client.login(username="admin", password="pass12345")
        customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Wrong Customer",
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("customers:archive", args=[customer.pk]),
            {"reason": "Created by mistake"},
            follow=True,
        )
        customer.refresh_from_db()
        self.assertEqual(customer.status, "inactive")
        self.assertNotContains(response, "Wrong Customer")

        archived_response = self.client.get(reverse("customers:list") + "?status=inactive")
        self.assertContains(archived_response, "Wrong Customer")

        self.client.post(reverse("customers:restore", args=[customer.pk]))
        customer.refresh_from_db()
        self.assertEqual(customer.status, "active")

    def test_customer_list_has_scrollable_customizable_table(self):
        self.client.login(username="admin", password="pass12345")
        Customer.objects.create(
            tenant=self.tenant,
            full_name="Asha Customer",
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.get(reverse("customers:list"))
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")
        self.assertContains(response, "Showing 1 result")

    def test_customer_archive_page_requests_reason_and_shows_warning(self):
        self.client.login(username="admin", password="pass12345")
        customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Archive Candidate",
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.get(reverse("customers:archive", args=[customer.pk]))
        self.assertContains(response, "Archive Customer")
        self.assertContains(response, "Reason")
        self.assertContains(response, "Vehicles and LATRA records linked to this customer remain preserved")

    def test_customer_archive_validation_error_preserves_confirmation_page(self):
        self.client.login(username="admin", password="pass12345")
        customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Archive Candidate",
            created_by=self.user,
            updated_by=self.user,
        )
        response = self.client.post(
            reverse("customers:archive", args=[customer.pk]),
            {"reason": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Reason:")
        self.assertContains(response, "Error: This field is required.")
