from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RoleChoices, User, VehicleCategoryChoices
from customers.models import Customer
from latra.models import LatraRecord
from tenants.models import TenantCompany
from vehicles.models import Vehicle
from vehicles.forms import VehicleForm


class VehicleFormTests(TestCase):
    def test_vehicle_category_does_not_include_all_permission_choice(self):
        tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        form = VehicleForm(tenant=tenant)
        category_values = [value for value, _label in form.fields["vehicle_category"].choices]
        self.assertIn(VehicleCategoryChoices.CAR, category_values)
        self.assertIn(VehicleCategoryChoices.MOTORCYCLE, category_values)
        self.assertNotIn(VehicleCategoryChoices.ALL, category_values)


class VehicleArchiveWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.user = User.objects.create_user(
            username="admin",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.ADMIN,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Customer One",
            created_by=self.user,
            updated_by=self.user,
        )
        self.vehicle = Vehicle.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plate_number="T555ABC",
            vehicle_category=VehicleCategoryChoices.CAR,
            created_by=self.user,
            updated_by=self.user,
        )

    def test_vehicle_archive_hides_from_default_list_and_can_restore(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("vehicles:archive", args=[self.vehicle.pk]),
            {"reason": "Wrong plate created"},
            follow=True,
        )
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, "inactive")
        self.assertNotContains(response, "T555ABC")

        archived_response = self.client.get(reverse("vehicles:list") + "?status=inactive")
        self.assertContains(archived_response, "T555ABC")

        self.client.post(reverse("vehicles:restore", args=[self.vehicle.pk]))
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, "active")

    def test_vehicle_list_has_category_filters_and_table_controls(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("vehicles:list"))

        self.assertContains(response, "Total Vehicles")
        self.assertContains(response, "All categories")
        self.assertContains(response, "Vehicle Records")
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_vehicle_create_form_has_sections_and_customer_recovery_link(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("vehicles:create"))

        self.assertContains(response, "Vehicle Details")
        self.assertContains(response, "Customer missing?")
        self.assertContains(response, "Optional Notes")

    def test_vehicle_create_validation_errors_are_actionable(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("vehicles:create"),
            {
                "customer": "",
                "plate_number": "",
                "vehicle_category": "",
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Error: This field is required.")

    def test_duplicate_vehicle_plate_error_is_attached_to_plate_field(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("vehicles:create"),
            {
                "customer": self.customer.pk,
                "plate_number": "T555ABC",
                "vehicle_category": VehicleCategoryChoices.CAR,
                "notes": "",
                "status": "active",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Plate number:")
        self.assertContains(response, "Error:")

    def test_vehicle_with_operational_latra_record_must_not_archive(self):
        self.client.login(username="admin", password="pass12345")
        LatraRecord.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            vehicle=self.vehicle,
            service_name="Route Permit",
            issue_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=30),
            created_by=self.user,
            updated_by=self.user,
        )

        response = self.client.post(
            reverse("vehicles:archive", args=[self.vehicle.pk]),
            {"reason": "Wrong vehicle"},
            follow=True,
        )
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.status, "active")
        self.assertContains(response, "Cancel related LATRA records before archiving this vehicle.")
