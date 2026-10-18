from django.db import models


class StoredFile(models.Model):
    """El contenido de un archivo subido (una foto de evidencia), guardado en la base de datos.

    Lo usa solo `DatabaseStorage`: los modelos que tienen archivos usan un `FileField` como con
    cualquier almacenamiento y no conocen esta tabla. Así la foto y su registro quedan en la misma
    base, persisten entre despliegues y entran en los respaldos.
    """

    name = models.CharField(max_length=255, unique=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
