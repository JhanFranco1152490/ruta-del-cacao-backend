from django.db import models


class DocumentType(models.TextChoices):
    CC = "CC", "Cédula de ciudadanía"
    CE = "CE", "Cédula de extranjería"
    PPT = "PPT", "Permiso por Protección Temporal"
    NIT = "NIT", "Número de Identificación Tributaria"
