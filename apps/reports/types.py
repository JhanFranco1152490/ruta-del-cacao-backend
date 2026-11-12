"""Los tipos de reporte de cada vista y el permiso de módulo que pide cada uno."""

PRODUCTION = "production"
QUALITY = "quality"
INVENTORY = "inventory"
SALES = "sales"
TRACEABILITY = "traceability"

TITLES = {
    PRODUCTION: "Producción",
    QUALITY: "Calidad",
    INVENTORY: "Inventario",
    SALES: "Comercialización",
    TRACEABILITY: "Trazabilidad",
}

PRODUCER_TYPES = (PRODUCTION, QUALITY, INVENTORY, SALES, TRACEABILITY)
# La asociación ve cifras por finca: nada de existencias ni de lotes uno por uno.
ASSOCIATION_TYPES = (PRODUCTION, QUALITY, SALES)

# Las existencias son las de hoy, como en bodega: no hay periodo que filtrar.
WITHOUT_PERIOD = frozenset({INVENTORY})

# El reporte del productor trae detalle y precios: cada tipo pide además el permiso con que se
# consulta su módulo, para que nadie vea por aquí lo que no ve allá.
MODULE_PERMISSIONS = {
    PRODUCTION: "harvests.view_harvest",
    QUALITY: "lots.view_lot",
    INVENTORY: "warehouse.view_stock",
    SALES: "sales.view_sale",
    TRACEABILITY: "lots.view_lot",
}
