from django.db import models


class IndicatorAccess(models.Model):
    """Solo existe para declarar los permisos de los paneles: Django crea un permiso a partir del
    `Meta` de un modelo. Los paneles se calculan con los datos de otras apps y no guardan nada, así
    que el modelo no tiene tabla."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            (
                "view_producer_indicators",
                "Puede consultar el panel de indicadores del productor",
            ),
            (
                "view_association_indicators",
                "Puede consultar el panel de indicadores de la asociación",
            ),
        ]
