import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.text import normalize_catalog_name

from ..choices import PestDiseaseKind


class PestDisease(models.Model):
    """El catálogo de plagas y enfermedades del cacao: lo mantiene la asociación y el capataz elige
    de él al registrar un monitoreo, para que el historial no cuente `Monilia` y `monilia` como
    dos plagas distintas."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)
    normalized_name = models.CharField(max_length=120, editable=False)
    kind = models.CharField(max_length=16, choices=PestDiseaseKind.choices)
    # Para buscarla en una guía o consultarla con un agrónomo; en campo se reconoce por la
    # descripción.
    scientific_name = models.CharField(max_length=100, null=True, blank=True)
    # Lo que se ve y dónde, en palabras del capataz.
    description = models.CharField(max_length=300)
    # El nombre y el nombre científico normalizados, separados por `|`: la búsqueda los compara
    # como el nombre, y el separador evita que un término una el final de uno con el inicio del
    # otro.
    search_normalized = models.TextField(editable=False, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["normalized_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["normalized_name"], name="health_pestdisease_name_unique"
            ),
        ]
        default_permissions = ()
        permissions = [
            (
                "manage_pestdisease",
                "Puede registrar, editar, activar y desactivar plagas y enfermedades",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.normalized_name = normalize_catalog_name(self.name or "")
        # Un nombre hecho solo de espacios o guiones quedaría vacío al compararlo.
        if not self.normalized_name:
            raise ValidationError({"name": "Este campo es obligatorio."})
        self.scientific_name = (self.scientific_name or "").strip() or None
        if isinstance(self.description, str):
            self.description = self.description.strip()
        self.search_normalized = search_text(self.name, self.scientific_name)


def search_text(name: str, scientific_name: str | None) -> str:
    return "|".join(normalize_catalog_name(text) for text in [name, scientific_name] if text)
