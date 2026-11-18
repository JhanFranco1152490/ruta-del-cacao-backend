from django.db import models


class ReportAccess(models.Model):
    """Solo existe para declarar los permisos de los reportes: Django crea un permiso a partir del
    `Meta` de un modelo. Los reportes se arman al pedirlos con los datos de otras apps y no guardan
    nada, así que el modelo no tiene tabla."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_producer_reports", "Puede generar y exportar los reportes del productor"),
            (
                "view_association_reports",
                "Puede generar y exportar los reportes de la asociación",
            ),
        ]
