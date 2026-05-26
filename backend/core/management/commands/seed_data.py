from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import DataSource, EmissionFactor, Tenant, User

EMISSION_FACTORS = [
    # Scope 1 — direct combustion
    {
        "factor_type": "fuel_diesel_combustion",
        "factor_value_kg_co2e": Decimal("2.68"),
        "unit": "liter",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "fuel_petrol_combustion",
        "factor_value_kg_co2e": Decimal("2.31"),
        "unit": "liter",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "fuel_natural_gas_combustion",
        "factor_value_kg_co2e": Decimal("0.18"),
        "unit": "kWh",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    # Scope 2 — electricity
    {
        "factor_type": "electricity_consumption",
        "factor_value_kg_co2e": Decimal("0.233"),
        "unit": "kWh",
        "region": "UK",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "electricity_consumption",
        "factor_value_kg_co2e": Decimal("0.386"),
        "unit": "kWh",
        "region": "US",
        "source": "EPA_2024",
    },
    {
        "factor_type": "electricity_consumption",
        "factor_value_kg_co2e": Decimal("0.475"),
        "unit": "kWh",
        "region": "GLOBAL",
        "source": "IEA_2024",
    },
    # Scope 3 — business travel (category 6)
    {
        "factor_type": "flight_economy_short_haul",
        "factor_value_kg_co2e": Decimal("0.158"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "flight_economy_long_haul",
        "factor_value_kg_co2e": Decimal("0.103"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "flight_business_short_haul",
        "factor_value_kg_co2e": Decimal("0.237"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "flight_business_long_haul",
        "factor_value_kg_co2e": Decimal("0.309"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    # Scope 3 — business travel (rail, car, bus)
    {
        "factor_type": "travel_rail",
        "factor_value_kg_co2e": Decimal("0.041"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "travel_car",
        "factor_value_kg_co2e": Decimal("0.171"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
    {
        "factor_type": "travel_bus",
        "factor_value_kg_co2e": Decimal("0.097"),
        "unit": "km",
        "region": "GLOBAL",
        "source": "DEFRA_2024",
    },
]

VALID_FROM = date(2024, 1, 1)
VALID_UNTIL = date(2025, 12, 31)


class Command(BaseCommand):
    help = "Seed database with initial emission factors, tenant, data source, and sample users."

    def handle(self, *args, **options):
        self.stdout.write("Starting data seeding...")

        with transaction.atomic():
            self._create_emission_factors()
            tenant = self._create_sample_tenant()
            self._create_sample_data_source(tenant)
            self._create_sample_users(tenant)

        self.stdout.write(self.style.SUCCESS("Data seeding completed."))

    # ------------------------------------------------------------------

    def _create_emission_factors(self):
        self.stdout.write("  Creating emission factors...")
        created = 0
        skipped = 0

        for spec in EMISSION_FACTORS:
            _, was_created = EmissionFactor.objects.get_or_create(
                factor_type=spec["factor_type"],
                unit=spec["unit"],
                region=spec["region"],
                source=spec["source"],
                defaults={
                    "factor_value_kg_co2e": spec["factor_value_kg_co2e"],
                    "valid_from": VALID_FROM,
                    "valid_until": VALID_UNTIL,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            f"    Emission factors: {created} created, "
            + self.style.WARNING(f"{skipped} already existed")
        )

    def _create_sample_tenant(self) -> Tenant:
        self.stdout.write("  Creating sample tenant...")
        tenant, created = Tenant.objects.get_or_create(
            slug="demo-company",
            defaults={"name": "Demo Company Ltd"},
        )
        if created:
            self.stdout.write(f"    Created tenant: {tenant.name}")
        else:
            self.stdout.write(self.style.WARNING(f"    Tenant '{tenant.name}' already exists"))
        return tenant

    def _create_sample_data_source(self, tenant: Tenant) -> None:
        self.stdout.write("  Creating sample data source...")
        source, created = DataSource.objects.get_or_create(
            tenant=tenant,
            name="Demo SAP System",
            defaults={
                "source_type": DataSource.SourceType.SAP_PROCUREMENT,
                "configuration": {
                    "column_mappings": {
                        "Material": "activity_type",
                        "Quantity": "quantity",
                        "Unit": "unit",
                        "Posting Date": "activity_date",
                        "Plant": "location_name",
                        "Country": "country_code",
                    }
                },
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(f"    Created data source: {source.name}")
        else:
            self.stdout.write(self.style.WARNING(f"    Data source '{source.name}' already exists"))

        # Utility source
        util_source, created = DataSource.objects.get_or_create(
            tenant=tenant,
            name="Demo Utility Bills",
            defaults={
                "source_type": DataSource.SourceType.UTILITY_ELECTRICITY,
                "configuration": {
                    "column_mappings": {
                        "Meter": "location_code",
                        "kWh": "quantity",
                        "Bill Period": "activity_date",
                        "Site": "location_name",
                        "Country": "country_code",
                    }
                },
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(f"    Created data source: {util_source.name}")
        else:
            self.stdout.write(self.style.WARNING(f"    Data source '{util_source.name}' already exists"))

        # Corporate Travel source
        travel_source, created = DataSource.objects.get_or_create(
            tenant=tenant,
            name="Demo Corporate Travel",
            defaults={
                "source_type": DataSource.SourceType.CORPORATE_TRAVEL,
                "configuration": {
                    "column_mappings": {
                        "Date": "activity_date",
                        "Employee": "metadata",
                        "From": "location_from",
                        "To": "location_to",
                        "Distance": "quantity",
                        "Mode": "activity_type",
                        "Flight Class": "metadata",
                    }
                },
                "is_active": True,
            },
        )
        if created:
            self.stdout.write(f"    Created data source: {travel_source.name}")
        else:
            self.stdout.write(self.style.WARNING(f"    Data source '{travel_source.name}' already exists"))

    def _create_sample_users(self, tenant: Tenant) -> None:
        self.stdout.write("  Creating sample users...")

        users = [
            {
                "username": "analyst_demo",
                "email": "analyst@demo-company.example",
                "first_name": "Alex",
                "last_name": "Analyst",
                "role": User.Role.ANALYST,
                "password": "analyst_demo_password_123",
            },
            {
                "username": "manager_demo",
                "email": "manager@demo-company.example",
                "first_name": "Morgan",
                "last_name": "Manager",
                "role": User.Role.MANAGER,
                "password": "manager_demo_password_123",
            },
            {
                "username": "auditor_demo",
                "email": "auditor@demo-company.example",
                "first_name": "Avery",
                "last_name": "Auditor",
                "role": User.Role.AUDITOR,
                "password": "auditor_demo_password_123",
            },
        ]

        for spec in users:
            password = spec.pop("password")
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={**spec, "tenant": tenant},
            )
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
                self.stdout.write(f"    Created user: {user.username} ({user.get_role_display()})")
            else:
                self.stdout.write(
                    self.style.WARNING(f"    User '{user.username}' already exists")
                )
