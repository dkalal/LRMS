from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.cache import cache
from unittest.mock import patch

from accounts.models import RoleChoices, User, UserVehiclePermission, VehicleCategoryChoices
from brokers.models import Broker
from customers.models import Customer
from latra.models import LatraRecord
from tenants.models import TenantCompany
from vehicles.models import Vehicle


class DashboardTests(TestCase):
    def setUp(self):
        self.tenant = TenantCompany.objects.create(name="Tenant A", slug="tenant-a")
        self.user = User.objects.create_user(
            username="staff",
            password="pass12345",
            tenant=self.tenant,
            role=RoleChoices.RECEPTIONIST,
        )
        UserVehiclePermission.objects.create(
            tenant=self.tenant,
            user=self.user,
            vehicle_category=VehicleCategoryChoices.CAR,
        )
        self.broker = Broker.objects.create(
            tenant=self.tenant,
            full_name="Broker One",
            phone_number="255712345678",
            created_by=self.user,
            updated_by=self.user,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            full_name="Customer One",
            broker=self.broker,
            created_by=self.user,
            updated_by=self.user,
        )
        self.vehicle = Vehicle.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plate_number="T123ABC",
            vehicle_category=VehicleCategoryChoices.CAR,
            created_by=self.user,
            updated_by=self.user,
        )
        Vehicle.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            plate_number="MOTO1",
            vehicle_category=VehicleCategoryChoices.MOTORCYCLE,
            created_by=self.user,
            updated_by=self.user,
        )
        LatraRecord.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            vehicle=self.vehicle,
            broker=self.broker,
            service_name="Route Permit",
            issue_date=timezone.localdate(),
            expiry_date=timezone.localdate() + timedelta(days=2),
            created_by=self.user,
            updated_by=self.user,
        )

    def test_dashboard_respects_vehicle_permissions_for_counts(self):
        self.client.login(username="staff", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.context["total_vehicles"], 1)
        self.assertEqual(response.context["expiring_7_records"], 1)

    def test_dashboard_cards_are_clickable_drilldowns(self):
        self.client.login(username="staff", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, reverse("customers:list"))
        self.assertContains(response, reverse("vehicles:list"))
        self.assertContains(response, reverse("latra:list") + "?expiry_status=expiring_in_7_days")
        self.assertContains(response, "Priority Follow-up")

    def test_dashboard_tables_are_scrollable_and_customizable(self):
        self.client.login(username="staff", password="pass12345")
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "max-h-80 overflow-auto")
        self.assertContains(response, "data-column-toggle")
        self.assertContains(response, "sticky top-0")

    def test_dashboard_error_state_is_graceful(self):
        self.client.login(username="staff", password="pass12345")
        cache.clear()
        with patch("dashboard.views.get_dashboard_context", side_effect=RuntimeError("boom")):
            response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard summary is temporarily unavailable.")

    def test_reports_page_is_comprehensive_for_managerial_users(self):
        self.user.role = RoleChoices.MANAGER
        self.user.save(update_fields=["role"])
        self.client.login(username="staff", password="pass12345")

        response = self.client.get(reverse("reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Expiry Risk")
        self.assertContains(response, "Vehicle Categories")
        self.assertContains(response, "Top LATRA Services")
        self.assertContains(response, "Staff Activity")
        self.assertContains(response, "Broker Performance")
        self.assertContains(response, "Recent Audit Activity")

    def test_reports_context_is_cached_per_user_and_filter(self):
        self.user.role = RoleChoices.MANAGER
        self.user.save(update_fields=["role"])
        self.client.login(username="staff", password="pass12345")
        cache.clear()

        response = self.client.get(reverse("reports") + "?vehicle_category=CAR")

        self.assertEqual(response.status_code, 200)
        cache_key = f"reports:v1:tenant:{self.user.tenant_id}:user:{self.user.pk}:query:vehicle_category=CAR"
        self.assertIsNotNone(cache.get(cache_key))

    def test_receptionist_cannot_access_reports(self):
        self.client.login(username="staff", password="pass12345")
        response = self.client.get(reverse("reports"))
        self.assertEqual(response.status_code, 403)

    def test_old_broker_reports_route_redirects_to_reports_center(self):
        self.user.role = RoleChoices.MANAGER
        self.user.save(update_fields=["role"])
        self.client.login(username="staff", password="pass12345")
        response = self.client.get(reverse("brokers:reports"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("reports"))
