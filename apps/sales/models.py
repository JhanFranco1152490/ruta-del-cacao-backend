import uuid

from django.db import models

from apps.common.audit import AuditEventBase

MAX_LINES = 20
# Un tope generoso que solo atrapa un cero de más al escribir el precio.
MAX_PRICE_PER_KG = 1_000_000
NOTES_MAX_LENGTH = 300
VOID_REASON_MAX_LENGTH = 300
INVOICE_MAX_BYTES = 5 * 1024 * 1024
NUMBER_UNIQUE_CONSTRAINT = "sales_sale_producer_number_unique"
LINE_UNIQUE_CONSTRAINT = "sales_line_sale_lot_grade_unique"


class Grade(models.TextChoices):
    """El calibre vendido: los mismos dos de la clasificación y de la bodega."""

    G1 = "g1", "G1"
    G2 = "g2", "G2"


class Sale(models.Model):
    """Lo que se le vende a un comprador en una fecha, de los lotes de una finca. No se edita ni se
    elimina: un error se anula, y la venta queda en el historial con quién la anuló y por qué."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Registrada"
        VOIDED = "voided", "Anulada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # El de la finca. Va aparte para numerar por productor y para filtrar sin pasar por la finca.
    producer = models.ForeignKey(
        "producers.Producer", on_delete=models.PROTECT, related_name="sales"
    )
    number = models.PositiveIntegerField(editable=False)
    farm = models.ForeignKey("farms.Farm", on_delete=models.PROTECT, related_name="sales")
    # PROTECT: un comprador con ventas, también anuladas, no se elimina; se desactiva.
    buyer = models.ForeignKey("buyers.Buyer", on_delete=models.PROTECT, related_name="sales")
    sale_date = models.DateField()
    notes = models.CharField(max_length=NOTES_MAX_LENGTH, blank=True, default="")
    # El soporte de la factura. El nombre en el almacenamiento lo pone el servidor; el original va
    # en `invoice_name` para mostrarlo.
    invoice = models.FileField(max_length=150, blank=True, default="")
    invoice_name = models.CharField(max_length=255, blank=True, default="")
    invoice_content_type = models.CharField(max_length=40, blank=True, default="")
    invoice_size = models.PositiveIntegerField(null=True, blank=True)
    invoice_uploaded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField()
    voided_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=VOID_REASON_MAX_LENGTH, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sale_date", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["producer", "number"], name=NUMBER_UNIQUE_CONSTRAINT),
            models.CheckConstraint(
                condition=models.Q(voided_by__isnull=True, voided_at__isnull=True, void_reason="")
                | models.Q(voided_by__isnull=False, voided_at__isnull=False, void_reason__gt=""),
                name="sales_sale_void_complete",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    invoice="",
                    invoice_name="",
                    invoice_content_type="",
                    invoice_size__isnull=True,
                    invoice_uploaded_at__isnull=True,
                )
                | models.Q(
                    invoice__gt="",
                    invoice_name__gt="",
                    invoice_content_type__gt="",
                    invoice_size__isnull=False,
                    invoice_uploaded_at__isnull=False,
                ),
                name="sales_sale_invoice_complete",
            ),
        ]
        indexes = [
            models.Index(fields=["producer", "sale_date"], name="sales_producer_date_idx"),
            models.Index(fields=["farm", "sale_date"], name="sales_farm_date_idx"),
            models.Index(fields=["buyer", "sale_date"], name="sales_buyer_date_idx"),
        ]
        default_permissions = ()
        permissions = [
            ("view_sale", "Puede consultar ventas"),
            ("add_sale", "Puede registrar ventas y adjuntar su soporte"),
            ("void_sale", "Puede anular ventas"),
        ]

    def __str__(self):
        return self.code

    @property
    def code(self) -> str:
        return f"V-{self.number:04d}"

    @property
    def status(self) -> str:
        return self.Status.VOIDED if self.voided_at is not None else self.Status.REGISTERED


class SaleLine(models.Model):
    """Un lote y un calibre de una venta. Es exactamente una salida de bodega con motivo Venta."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    lot = models.ForeignKey("lots.Lot", on_delete=models.PROTECT, related_name="sale_lines")
    grade = models.CharField(max_length=2, choices=Grade.choices)
    quantity_kg = models.DecimalField(max_digits=7, decimal_places=1)
    # En pesos colombianos, sin decimales.
    price_per_kg = models.PositiveIntegerField()
    subtotal = models.PositiveBigIntegerField()
    # Al anular la venta, se sabe qué salida deshacer sin buscarla por lote, calibre y fecha.
    stock_exit = models.OneToOneField(
        "warehouse.StockExit", on_delete=models.PROTECT, related_name="sale_line"
    )

    class Meta:
        ordering = ["lot__code", "grade"]
        constraints = [
            models.UniqueConstraint(fields=["sale", "lot", "grade"], name=LINE_UNIQUE_CONSTRAINT),
            models.CheckConstraint(
                condition=models.Q(quantity_kg__gt=0), name="sales_line_quantity_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_kg__gte=1, price_per_kg__lte=MAX_PRICE_PER_KG),
                name="sales_line_price_range",
            ),
        ]
        default_permissions = ()

    def __str__(self):
        return f"{self.sale} {self.lot} {self.grade}"


class SaleCodeSequence(models.Model):
    """El último número de venta de un productor. No baja al anular: el número no se recicla."""

    # Con ventas, el productor nunca se borra en cascada: las ventas lo protegen.
    producer = models.OneToOneField(
        "producers.Producer", on_delete=models.CASCADE, related_name="+"
    )
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()


class SaleAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Venta registrada"
        VOIDED = "voided", "Venta anulada"
        INVOICE_ATTACHED = "invoice_attached", "Soporte adjuntado"
        INVOICE_REPLACED = "invoice_replaced", "Soporte reemplazado"
        INVOICE_REMOVED = "invoice_removed", "Soporte quitado"

    # PROTECT: una venta nunca se elimina, y su historial tampoco.
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="audit_events")
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión de la venta que dejó este cambio.
    version = models.PositiveIntegerField()

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
