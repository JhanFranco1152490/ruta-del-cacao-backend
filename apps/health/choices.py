from django.db import models


class PestDiseaseKind(models.TextChoices):
    PEST = "pest", "Plaga"
    DISEASE = "disease", "Enfermedad"
