from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import RoleChoices, User, UserVehiclePermission, VehicleCategoryChoices
from brokers.models import Broker
from customers.models import Customer
from latra.models import LatraRecord, LatraRecordStatus
from latra.services import (
    build_whatsapp_url,
    calculate_expiry_status,
    generate_whatsapp_message,
    get_contact_person,
    renew_latra_record,
)
from tenants.models import TenantCompany
from vehicles.models import Vehicle


class LatraWorkflowTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.other_tenant = TenantCompany.objects.create(name="Tenant B", slug="tenant-b")
        self.admin = User.objects.create_user(
            username="admin",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.ADMIN,
        )
        self.car_user = User.objects.create_user(
            username="caruser",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.RECEPTIONIST,
        )
        UserVehiclePermission.objects.create(
            tenant=self.tenant,
            user=self.car_user,
            vehicle_category=VehicleCategoryChoices.CAR,
        )
        self.other_user = User.objects.create_user(
            username="other",
            password="pass12345",
            tenant=self.other_tenant,
            role=RoleChoices.ADMIN,
        )
        self.broker = Broker.objects.create(
            tenant=self.tenant,
            full_name="Broker One",
            phone_number="255712345678",
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Customer One",
            phone_number="255700000001",
            broker=self.broker,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.vehicle = Vehicle.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plate_number="T123ABC",
            vehicle_category=VehicleCategoryChoices.CAR,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.other_vehicle = Vehicle.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plate_number="MC001",
            vehicle_category=VehicleCategoryChoices.MOTORCYCLE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.record = LatraRecord.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            vehicle=self.vehicle,
            broker=self.broker,
            service_name="Route Permit",
            issue_date=timezone.localdate() - timedelta(days=20),
            expiry_date=timezone.localdate() + timedelta(days=5),
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.motorcycle_record = LatraRecord.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            vehicle=self.other_vehicle,
            broker=self.broker,
            service_name="Goods Carrying Permit",
            issue_date=timezone.localdate() - timedelta(days=20),
            expiry_date=timezone.localdate() + timedelta(days=15),
            created_by=self.admin,
            updated_by=self.admin,
        )

    def test_expiry_statuses_are_calculated_correctly(self):
        self.assertEqual(calculate_expiry_status(self.record), "expiring_in_7_days")

        self.record.expiry_date = timezone.localdate() - timedelta(days=1)
        self.assertEqual(calculate_expiry_status(self.record), "expired")

        self.record.expiry_date = timezone.localdate()
        self.assertEqual(calculate_expiry_status(self.record), "expires_today")

    def test_contact_logic_prefers_customer_then_broker(self):
        contact = get_contact_person(self.record)
        self.assertEqual(contact["contact_type"], "Customer")
        self.customer.phone_number = ""
        self.customer.save(update_fields=["phone_number"])

        contact = get_contact_person(self.record)
        self.assertEqual(contact["contact_type"], "Broker")
        self.assertEqual(contact["phone_number"], self.broker.phone_number)

    def test_whatsapp_message_and_url_are_generated(self):
        contact = get_contact_person(self.record)
        message = generate_whatsapp_message(self.record, contact)
        self.assertIn(self.record.vehicle.plate_number, message)
        url = build_whatsapp_url(contact["phone_number"], message)
        self.assertIn("https://wa.me/255700000001?text=", url)
        self.assertIn("%20", url)

    def test_invalid_expiry_date_is_rejected(self):
        invalid_record = LatraRecord(
            tenant=self.tenant,
            customer=self.customer,
            vehicle=self.vehicle,
            service_name="Private Hire Permit",
            issue_date=timezone.localdate(),
            expiry_date=timezone.localdate() - timedelta(days=1),
        )
        with self.assertRaises(ValidationError):
            invalid_record.full_clean()

    def test_renewal_preserves_history(self):
        renewed = renew_latra_record(
            self.record,
            user=self.admin,
            issue_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=365),
            notes="Renewed for one year",
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, LatraRecordStatus.RENEWED)
        self.assertEqual(renewed.previous_record, self.record)
        self.assertEqual(renewed.status, LatraRecordStatus.ACTIVE)

    def test_vehicle_category_permissions_limit_latra_list(self):
        self.client.login(username="caruser", password="pass12345")
        response = self.client.get(reverse("latra:list"))
        records = response.context["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].vehicle.vehicle_category, VehicleCategoryChoices.CAR)

    def test_latra_expiry_filter_stays_paginated_and_database_filtered(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:list") + "?expiry_status=expiring_in_7_days")
        self.assertEqual(response.status_code, 200)
        self.assertIn("paginator", response.context)
        statuses = [
            calculate_expiry_status(record)
            for record in response.context["records"]
        ]
        self.assertEqual(statuses, ["expiring_in_7_days"])

    def test_latra_list_has_professional_table_controls(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:list"))

        self.assertContains(response, "LATRA Records")
        self.assertContains(response, "Operational Records")
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_latra_create_form_has_sections_and_error_summary(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("latra:create"),
            {
                "customer": self.customer.pk,
                "vehicle": self.vehicle.pk,
                "broker": self.broker.pk,
                "service_name": "",
                "issue_date": timezone.localdate(),
                "expiry_date": timezone.localdate() + timedelta(days=30),
                "notes": "",
                "status": LatraRecordStatus.ACTIVE,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "There is a problem")
        self.assertContains(response, "Record Details")
        self.assertContains(response, "Optional Notes")

    def test_latra_create_form_uses_server_side_lookup_inputs(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:create"))

        self.assertContains(response, 'id="lookup-customer"')
        self.assertContains(response, 'id="lookup-vehicle"')
        self.assertContains(response, 'id="lookup-broker"')
        self.assertContains(response, 'type="hidden" name="customer"')
        self.assertContains(response, 'type="hidden" name="vehicle"')

    def test_latra_customer_lookup_returns_related_broker(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:customer_lookup") + "?q=Customer")

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertEqual(results[0]["name"], "Customer One")
        self.assertEqual(results[0]["broker"]["name"], "Broker One")

    def test_latra_vehicle_lookup_filters_by_customer_and_returns_relationships(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:vehicle_lookup") + f"?customer={self.customer.pk}")

        self.assertEqual(response.status_code, 200)
        plates = [item["plate"] for item in response.json()["results"]]
        self.assertIn("T123ABC", plates)
        self.assertIn("MC001", plates)
        first = response.json()["results"][0]
        self.assertIn("customer", first)

    def test_latra_vehicle_lookup_respects_vehicle_category_permission(self):
        self.client.login(username="caruser", password="pass12345")
        response = self.client.get(reverse("latra:vehicle_lookup"))

        self.assertEqual(response.status_code, 200)
        plates = [item["plate"] for item in response.json()["results"]]
        self.assertEqual(plates, ["T123ABC"])

    def test_reminder_status_pages_have_followup_table_controls(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:status_list", args=["expiring"]))

        self.assertContains(response, "Follow-up Queue")
        self.assertContains(response, "max-h-96 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_tenant_isolation_blocks_other_tenant_records(self):
        other_broker = Broker.objects.create(
            tenant=self.other_tenant,
            full_name="Other Broker",
            phone_number="255711111111",
            created_by=self.other_user,
            updated_by=self.other_user,
        )
        other_customer = Customer.objects.create(
            tenant=self.other_tenant,
            full_name="Other Customer",
            broker=other_broker,
            created_by=self.other_user,
            updated_by=self.other_user,
        )
        other_vehicle = Vehicle.objects.create(
            tenant=self.other_tenant,
            customer=other_customer,
            plate_number="T999ZZZ",
            vehicle_category=VehicleCategoryChoices.CAR,
            created_by=self.other_user,
            updated_by=self.other_user,
        )
        other_record = LatraRecord.objects.create(
            tenant=self.other_tenant,
            customer=other_customer,
            vehicle=other_vehicle,
            broker=other_broker,
            service_name="Route Permit",
            issue_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=90),
            created_by=self.other_user,
            updated_by=self.other_user,
        )
        self.client.login(username="admin", password="pass12345")
        response = self.client.get(reverse("latra:update", args=[other_record.pk]))
        self.assertEqual(response.status_code, 404)

    def test_latra_record_can_be_cancelled_and_restored(self):
        self.client.login(username="admin", password="pass12345")
        response = self.client.post(
            reverse("latra:cancel", args=[self.record.pk]),
            {"reason": "Created with wrong expiry"},
            follow=True,
        )
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, LatraRecordStatus.CANCELLED)
        self.assertNotContains(response, self.record.service_name)

        cancelled_response = self.client.get(reverse("latra:list") + "?record_state=cancelled")
        self.assertContains(cancelled_response, self.record.service_name)

        self.client.post(reverse("latra:restore", args=[self.record.pk]))
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, LatraRecordStatus.ACTIVE)
