from django.core.management.base import BaseCommand, CommandError

from apps.demo_data.catalog import DEMO_ADMIN_EMAIL, DEMO_PASSWORD, DEMO_PRODUCER_EMAIL
from apps.demo_data.seed import MissingVarietyCatalog, seed_demo_data


class Command(BaseCommand):
    help = (
        "Carga datos de demostración (productores, fincas, parcelas y fichas) y deja dos cuentas "
        "con una contraseña pública. Se puede repetir: no duplica nada y restablece las dos "
        "cuentas. No se corre en un despliegue con datos reales."
    )

    def handle(self, *args, **options):
        try:
            report = seed_demo_data()
        except MissingVarietyCatalog as error:
            raise CommandError(
                "Falta el catálogo de variedades de cacao: corre `python manage.py migrate` antes."
            ) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Productores creados: {report.producers_created}; "
                f"ya existían: {report.producers_skipped}."
            )
        )
        self.stdout.write(f"Administrador de la asociación: {DEMO_ADMIN_EMAIL}")
        self.stdout.write(f"Productor: {DEMO_PRODUCER_EMAIL}")
        self.stdout.write(f"Contraseña de ambas: {DEMO_PASSWORD}")
