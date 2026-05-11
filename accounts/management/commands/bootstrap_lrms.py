from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.utils import timezone

from accounts.models import RoleChoices, User, UserVehiclePermission, VehicleCategoryChoices
from brokers.models import Broker
from customers.models import Customer
from latra.models import LatraRecord
from tenants.models import TenantCompany
from vehicles.models import Vehicle


class Command(BaseCommand):
    help = "Create a default tenant and admin user for local LRMS development."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-name", default="Demo Tenant")
        parser.add_argument("--tenant-slug", default="demo-tenant")
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", default="admin12345")
        parser.add_argument(
            "--with-demo-data",
            action="store_true",
            help="Create sample broker, customer, vehicle, and LATRA records.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and options.get("password") == "admin12345":
            raise CommandError(
                "Refusing to bootstrap with the default password in production. "
                "Pass a strong --password value (or disable bootstrapping)."
            )

        tenant, _ = TenantCompany.objects.get_or_create(
            slug=options["tenant_slug"],
            defaults={"name": options["tenant_name"]},
        )
        user, created = User.objects.get_or_create(
            username=options["username"],
            defaults={
                "tenant": tenant,
                "role": RoleChoices.ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.tenant = tenant
        user.role = RoleChoices.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.set_password(options["password"])
        user.save()
        UserVehiclePermission.objects.get_or_create(
            tenant=tenant,
            user=user,
            vehicle_category=VehicleCategoryChoices.ALL,
        )

        if created:
            self.stdout.write(self.style.SUCCESS("Demo tenant and admin user created."))
        else:
            self.stdout.write(self.style.SUCCESS("Demo admin user updated."))

        if options["with_demo_data"]:
            self.create_demo_data(tenant, user)
            self.stdout.write(self.style.SUCCESS("Demo business records created."))

    def create_demo_data(self, tenant, user):
        today = timezone.localdate()
        broker, _ = Broker.objects.get_or_create(
            tenant=tenant,
            full_name="Juma Broker",
            defaults={
                "phone_number": "255712345678",
                "location": "Dar es Salaam",
                "created_by": user,
                "updated_by": user,
            },
        )
        customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            full_name="Asha Mteja",
            defaults={
                "phone_number": "255755000111",
                "broker": broker,
                "created_by": user,
                "updated_by": user,
            },
        )
        broker_only_customer, _ = Customer.objects.get_or_create(
            tenant=tenant,
            full_name="Mteja Kupitia Broker",
            defaults={
                "phone_number": "",
                "broker": broker,
                "created_by": user,
                "updated_by": user,
            },
        )

        car, _ = Vehicle.objects.get_or_create(
            tenant=tenant,
            plate_number="T123 ABC",
            defaults={
                "customer": customer,
                "vehicle_category": VehicleCategoryChoices.CAR,
                "created_by": user,
                "updated_by": user,
            },
        )
        motorcycle, _ = Vehicle.objects.get_or_create(
            tenant=tenant,
            plate_number="MC 456",
            defaults={
                "customer": broker_only_customer,
                "vehicle_category": VehicleCategoryChoices.MOTORCYCLE,
                "created_by": user,
                "updated_by": user,
            },
        )

        samples = [
            (customer, car, "Route Permit", today - timedelta(days=20), today + timedelta(days=25)),
            (broker_only_customer, motorcycle, "Road Service Licence", today - timedelta(days=60), today + timedelta(days=6)),
            (customer, car, "Private Hire Permit", today - timedelta(days=100), today - timedelta(days=3)),
        ]
        for sample_customer, vehicle, service_name, issue_date, expiry_date in samples:
            LatraRecord.objects.get_or_create(
                tenant=tenant,
                customer=sample_customer,
                vehicle=vehicle,
                broker=sample_customer.broker,
                service_name=service_name,
                issue_date=issue_date,
                expiry_date=expiry_date,
                defaults={"created_by": user, "updated_by": user},
            )
