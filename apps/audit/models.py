from django.db import models


class AuditLogAccess(models.Model):
    """Solo existe para declarar el permiso de la bitácora: Django crea un permiso a partir del
    `Meta` de un modelo. La bitácora se arma al pedirla con los historiales de las demás apps y no
    guarda nada, así que el modelo no tiene tabla."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [("view_audit_log", "Puede consultar la bitácora de cambios")]
