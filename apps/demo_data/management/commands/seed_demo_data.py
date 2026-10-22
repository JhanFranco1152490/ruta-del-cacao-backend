from django.core.management.base import BaseCommand, CommandError

from apps.demo_data.catalog import (
    DEMO_ADMIN_EMAIL,
    DEMO_FOREMAN_EMAIL,
    DEMO_OPERATOR_EMAIL,
    DEMO_PASSWORD,
    DEMO_PRODUCER_EMAIL,
)
from apps.demo_data.seed import MissingVarietyCatalog, seed_demo_data


class Command(BaseCommand):
    help = (
        "Carga datos de demostración (productores, fincas, parcelas, fichas y, en La Esperanza, "
        "empleados, insumos, infraestructura, labores, monitoreos, cosechas y lotes) y deja "
        "cuentas con una contraseña pública. Se puede repetir: no duplica nada, restablece las "
        "cuentas y deja otra vez programado el monitoreo de hoy. No se corre en un despliegue "
        "con datos reales."
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
        for line in report.operations:
            self.stdout.write(f"  {line}")
        self.stdout.write(f"Administrador de la asociación: {DEMO_ADMIN_EMAIL}")
        self.stdout.write(f"Productor: {DEMO_PRODUCER_EMAIL}")
        self.stdout.write(f"Capataz de La Esperanza: {DEMO_FOREMAN_EMAIL}")
        self.stdout.write(f"Operario de El Mirador: {DEMO_OPERATOR_EMAIL}")
        self.stdout.write(f"Contraseña de todas: {DEMO_PASSWORD}")
