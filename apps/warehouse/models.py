import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.lookups import GreaterThan

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_catalog_name

from .choices import ExitReason, Grade

NAME_MAX_LENGTH = 40
LOCATION_MAX_LENGTH = 60
DETAIL_MAX_LENGTH = 300
ONE_DECIMAL = 1


def _kilograms():
    return models.DecimalField(max_digits=7, decimal_places=ONE_DECIMAL)


def _grade():
    return models.CharField(max_length=2, choices=Grade.choices)


class Warehouse(models.Model):
    """Un lugar donde una finca guarda su cacao seco. No tiene capacidad: no se mide cuánto cabe.
    Normalmente hay una por finca."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey("farms.Farm", on_delete=models.PROTECT, related_name="warehouses")
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    # Sin acotar a 40: la normalización de Unicode puede expandir algunos caracteres.
    name_normalized = models.CharField(max_length=120, editable=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name_normalized", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "name_normalized"], name="warehouse_warehouse_farm_name_unique"
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados. Van todos aquí: son los de toda la app.
        default_permissions = ()
        permissions = [
            ("view_stock", "Puede consultar las existencias y las bodegas"),
            ("register_entry", "Puede ingresar lotes a bodega y corregir el ingreso"),
            ("register_exit", "Puede registrar y anular salidas de bodega"),
            ("manage_warehouse", "Puede registrar, editar, desactivar y eliminar bodegas"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.name_normalized = normalize_catalog_name(self.name or "")
        # La longitud se revisa aquí y no en un validador del campo: ese correría antes de recortar
        # los espacios.
        if not self.name_normalized:
            raise ValidationError({"name": "Este campo es obligatorio."})
        if len(self.name) > NAME_MAX_LENGTH:
            raise ValidationError(
                {"name": f"El nombre debe tener máximo {NAME_MAX_LENGTH} caracteres."}
            )


class StockEntry(models.Model):
    """El ingreso de un lote a una bodega: cuándo, dónde y los kilos de G1 y de G2 que tenía su
    clasificación. Un lote ingresa una sola vez y por completo."""

    lot = models.OneToOneField(
        "lots.Lot", on_delete=models.PROTECT, primary_key=True, related_name="stock_entry"
    )
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="entries")
    # Opcional: una bodega pequeña no necesita estantes y no siempre se sabe dónde quedó.
    location = models.CharField(max_length=LOCATION_MAX_LENGTH, blank=True)
    entry_date = models.DateField()
    g1_kg = _kilograms()
    g2_kg = _kilograms()
    # PROTECT: una cuenta que ingresó o corrigió un lote no se elimina.
    entered_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    entered_at = models.DateTimeField()
    corrected_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    corrected_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["entered_at"]
        default_permissions = ()
        constraints = [
            models.CheckConstraint(
                condition=models.Q(g1_kg__gte=0, g2_kg__gte=0),
                name="warehouse_entry_kilograms_not_negative",
            ),
            models.CheckConstraint(
                condition=GreaterThan(models.F("g1_kg") + models.F("g2_kg"), 0),
                name="warehouse_entry_has_kilograms",
            ),
            models.CheckConstraint(
                condition=models.Q(corrected_by__isnull=True, corrected_at__isnull=True)
                | models.Q(corrected_by__isnull=False, corrected_at__isnull=False),
                name="warehouse_entry_correction_complete",
            ),
        ]

    def __str__(self):
        return str(self.lot)


class StockBalance(models.Model):
    """Los kilos que quedan de un calibre de un lote. Parte de lo ingresado y baja con cada salida;
    es el saldo que se consulta y el que se bloquea al escribir. Nunca baja de 0."""

    lot = models.ForeignKey("lots.Lot", on_delete=models.PROTECT, related_name="stock_balances")
    grade = _grade()
    quantity_kg = _kilograms()
    # Copia de los del ingreso: la corrección del ingreso las actualiza en la misma transacción.
    # Así la consulta no cruza tablas, y G1 y G2 podrían separarse sin migrar datos.
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="balances")
    location = models.CharField(max_length=LOCATION_MAX_LENGTH, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["lot_id", "grade"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["lot", "grade"], name="warehouse_balance_lot_grade"),
            models.CheckConstraint(
                condition=models.Q(quantity_kg__gte=0), name="warehouse_balance_not_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["warehouse", "grade"], name="warehouse_balance_wh_grade_idx"),
            models.Index(fields=["grade", "quantity_kg"], name="warehouse_balance_qty_idx"),
        ]

    def __str__(self):
        return f"{self.lot} {self.grade}"


class StockExit(models.Model):
    """Kilos de un calibre que dejan la bodega por un motivo. No se elimina ni se edita: un error
    se anula, y la salida queda en el historial con quién la anuló y por qué."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey("lots.Lot", on_delete=models.PROTECT, related_name="stock_exits")
    grade = _grade()
    quantity_kg = _kilograms()
    exit_date = models.DateField()
    reason = models.CharField(max_length=16, choices=ExitReason.choices)
    detail = models.CharField(max_length=DETAIL_MAX_LENGTH, blank=True, default="")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()
    voided_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=DETAIL_MAX_LENGTH, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "id"]
        default_permissions = ()
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_kg__gt=0), name="warehouse_exit_quantity_positive"
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=ExitReason.OTHER) | ~models.Q(detail=""),
                name="warehouse_exit_other_has_detail",
            ),
            models.CheckConstraint(
                condition=models.Q(voided_by__isnull=True, voided_at__isnull=True, void_reason="")
                | models.Q(voided_by__isnull=False, voided_at__isnull=False, void_reason__gt=""),
                name="warehouse_exit_void_complete",
            ),
        ]
        indexes = [models.Index(fields=["lot", "grade"], name="warehouse_exit_lot_grade_idx")]

    def __str__(self):
        return f"{self.lot} {self.grade} {self.quantity_kg}"

    # La venta saca y devuelve existencias por estos dos métodos: llega al modelo por la relación
    # de su línea y no importa esta app. En los dos, quien llama ya bloqueó la finca del lote.
    @classmethod
    def remove_for_sale(cls, actor, lot, grade, quantity, *, exit_date):
        """Saca `quantity` kg del calibre del lote con motivo Venta y devuelve la salida."""
        from .services.exits import remove_stock

        return remove_stock(
            actor, lot, grade, quantity, exit_date=exit_date, reason=ExitReason.SALE
        )

    def void_for_sale(self, actor, reason):
        """Anula esta salida por venta: los kilos vuelven a la existencia."""
        from .services.exits import void_sale_exit

        return void_sale_exit(actor, self, reason)


class StockMove(models.Model):
    """Un cambio de lugar del cacao de un lote dentro de su finca: de qué bodega y ubicación a
    cuál. No sale cacao ni cambian los kilos; es el historial de dónde estuvo. Una bodega que
    aparece aquí ya fue usada, así que no se elimina."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lot = models.ForeignKey("lots.Lot", on_delete=models.PROTECT, related_name="stock_moves")
    from_warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="moves_out"
    )
    from_location = models.CharField(max_length=LOCATION_MAX_LENGTH, blank=True)
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="moves_in")
    to_location = models.CharField(max_length=LOCATION_MAX_LENGTH, blank=True)
    moved_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    moved_at = models.DateTimeField()

    class Meta:
        ordering = ["-moved_at", "id"]
        default_permissions = ()
        indexes = [models.Index(fields=["lot", "moved_at"], name="warehouse_move_lot_idx")]

    def __str__(self):
        return f"{self.lot} {self.from_warehouse} → {self.to_warehouse}"


class StockAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        ENTERED = "entered", "Lote ingresado a bodega"
        ENTRY_CORRECTED = "entry_corrected", "Ingreso corregido"
        MOVED = "moved", "Cacao movido de lugar"
        EXITED = "exited", "Salida registrada"
        EXIT_VOIDED = "exit_voided", "Salida anulada"

    # Un lote En bodega no se elimina, así que el historial apunta a él directamente.
    lot = models.ForeignKey(
        "lots.Lot", on_delete=models.PROTECT, related_name="stock_audit_events"
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión del ingreso que dejó el cambio.
    version = models.PositiveIntegerField()
    # Por cada campo, su valor anterior y nuevo con los textos de la API. No hay datos personales:
    # las cuentas se guardan por su id.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()


class WarehouseAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Bodega registrada"
        UPDATED = "updated", "Bodega actualizada"
        STATUS_CHANGED = "status_changed", "Estado de bodega modificado"
        DELETED = "deleted", "Bodega eliminada"

    # El historial sobrevive a la bodega: una registrada por error se puede eliminar, y sus eventos
    # quedan sin la relación pero con la copia de su id, su nombre y su finca.
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.SET_NULL, null=True, related_name="audit_events"
    )
    warehouse_ref = models.UUIDField(db_index=True)
    warehouse_name = models.CharField(max_length=NAME_MAX_LENGTH)
    farm_ref = models.UUIDField(db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="warehouse_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión de la bodega que dejó este cambio.
    version = models.PositiveIntegerField()
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
