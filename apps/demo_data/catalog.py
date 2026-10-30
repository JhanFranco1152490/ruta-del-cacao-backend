"""Los datos de demostración: cuentas para entrar y unos productores con fincas, parcelas y
fichas; de La Esperanza, además, lo que se hace en ella (insumos, infraestructura, labores,
monitoreos, cosechas y lotes). Todo es inventado: correos de `example.com` (dominio reservado,
nunca entrega correo) y documentos en secuencia que no corresponden a nadie.

La contraseña es pública a propósito: la pantalla de inicio de sesión la muestra para que quien
evalúa la aplicación entre sin pedir una cuenta. Por eso estas cuentas solo se crean con este
comando, y nunca en un despliegue con datos reales.
"""

from datetime import date
from decimal import Decimal

DEMO_PASSWORD = "CacaoDemo2026"
DEMO_ADMIN_EMAIL = "administrador@example.com"
DEMO_PRODUCER_EMAIL = "productor@example.com"
DEMO_FOREMAN_EMAIL = "capataz@example.com"
DEMO_OPERATOR_EMAIL = "operario@example.com"

DEMO_ADMIN = {
    "email": DEMO_ADMIN_EMAIL,
    "document_type": "CC",
    "identity_document": "1000000001",
    "first_name": "Laura",
    "last_name": "Méndez Ortega",
}

NORTE_DE_SANTANDER = "54"

# Los empleados del productor de demostración, con el rol Capataz/Operario: cada uno trabaja en una
# sola finca y solo alcanza lo de ella.
DEMO_EMPLOYEES = [
    {
        "email": DEMO_FOREMAN_EMAIL,
        "document_type": "CC",
        "identity_document": "1000000011",
        "first_name": "Marcos Elías",
        "last_name": "Villamizar Pérez",
        "farm": "La Esperanza",
    },
    {
        "email": DEMO_OPERATOR_EMAIL,
        "document_type": "CC",
        "identity_document": "1000000012",
        "first_name": "Yolanda",
        "last_name": "Suárez Arias",
        "farm": "El Mirador",
    },
]

# La finca y la parcela donde se hacen las demostraciones en vivo (el código de la parcela, P01, lo
# asigna el servidor: es la primera de la finca).
DEMO_FARM = "La Esperanza"
DEMO_PLOT = "L-01"
HISTORY_PLOT = "L-02"
# Nombre reservado para el cajón que se registra en vivo: la semilla lo libera para poder repetir.
LIVE_FACILITY_NAME = "CF-01"

# Insumos del catálogo del productor de demostración, con lo que hay en la bodega de La Esperanza.
DEMO_INPUTS = [
    {
        "name": "Urea 46 %",
        "input_type": "fertilizer",
        "unit": "kg",
        "package_type": "sack",
        "package_size": Decimal("50"),
        "stock": Decimal("200"),
    },
    {
        "name": "Abono orgánico (compost)",
        "input_type": "organic_fertilizer",
        "unit": "kg",
        "package_type": "sack",
        "package_size": Decimal("40"),
        "stock": Decimal("480"),
    },
    {
        "name": "Oxicloruro de cobre",
        "input_type": "fungicide",
        "unit": "kg",
        "package_type": "bag",
        "package_size": Decimal("1"),
        "stock": Decimal("12"),
    },
    {
        "name": "Cipermetrina",
        "input_type": "insecticide",
        "unit": "ml",
        "package_type": "bottle",
        "package_size": Decimal("500"),
        "stock": Decimal("3000"),
    },
]

# Cajones de fermentación y marquesinas de secado de La Esperanza (`CF-01` se deja libre).
DEMO_FACILITIES = [
    {"facility_type": "fermentation_box", "name": "C-01", "capacity_kg": Decimal("600")},
    {"facility_type": "fermentation_box", "name": "C-02", "capacity_kg": Decimal("400")},
    {"facility_type": "solar_dryer", "name": "M-01", "capacity_kg": Decimal("800")},
    # La que ocupa el lote en secado: M-01 queda libre para iniciar un secado en vivo.
    {"facility_type": "solar_dryer", "name": "M-02", "capacity_kg": Decimal("600")},
    # Los que ocupan los lotes que muestran cada aviso de poscosecha, para no quitarle a la
    # demostración en vivo el cajón y la marquesina libres.
    {"facility_type": "fermentation_box", "name": "C-03", "capacity_kg": Decimal("300")},
    {"facility_type": "fermentation_box", "name": "C-04", "capacity_kg": Decimal("300")},
    {"facility_type": "solar_dryer", "name": "M-03", "capacity_kg": Decimal("600")},
]

# Dónde está cada lote que muestra un aviso de poscosecha, y la marquesina del lote en secado en el
# que se registra en vivo la bitácora del sobresecado.
REMINDER_BOX = "C-03"
DEVIATIONS_BOX = "C-04"
NEAR_TARGET_DRYER = "M-03"
LIVE_LOG_DRYER = "M-02"

# Lo que el productor de demostración ajustó de la línea base del secado: así se ve qué cambió y se
# puede restablecer en vivo. Los demás productores quedan en la línea base.
DEMO_DRYING_PARAMETERS = {"slow_duration_day": 9, "estimated_days_max": 8}


def _planting(variety, year, month, trees, propagation, stage):
    return {
        "variety": variety,
        "planting_date": date(year, month, 1),
        "tree_count": trees,
        "propagation": propagation,
        "stage": stage,
    }


# Las parcelas se dibujan como rectángulos alrededor del punto de la finca: `east_m` y `north_m`
# son el centro del rectángulo medido desde ese punto. Las de una misma finca no se tocan.
PRODUCERS = [
    {
        "document_type": "CC",
        "identity_document": "1000000002",
        "first_name": "Carlos Andrés",
        "last_name": "Rincón Peña",
        "email": DEMO_PRODUCER_EMAIL,
        "municipality_code": "54810",
        "joined_on": date(2019, 3, 15),
        "farms": [
            {
                "name": "La Esperanza",
                "municipality_code": "54810",
                "details": "Vereda Campo Dos, a 20 minutos del casco urbano.",
                "area_hectares": Decimal("12.00"),
                "altitude_masl": 140,
                "latitude": Decimal("8.6512000"),
                "longitude": Decimal("-72.7398000"),
                "plots": [
                    {
                        "name": "L-01",
                        "area_hectares": Decimal("3.00"),
                        "shape": {"east_m": 120, "north_m": 0, "width_m": 200, "height_m": 150},
                        "characterization": {
                            "management_system": "conventional",
                            "shade_type": "permanent",
                            "plantings": [
                                _planting("CCN-51", 2017, 4, 1800, "grafted", "full_production"),
                                _planting("ICS-95", 2023, 5, 900, "grafted", "early_production"),
                            ],
                        },
                    },
                    {
                        "name": "L-02",
                        "area_hectares": Decimal("2.50"),
                        "shape": {"east_m": -120, "north_m": 0, "width_m": 200, "height_m": 125},
                        "characterization": {
                            "management_system": "in_transition",
                            "shade_type": "mixed",
                            "plantings": [
                                _planting("FSA-13", 2025, 2, 1500, "grafted", "establishment"),
                                _planting(
                                    "Híbrido o común (sin identificar)",
                                    2008,
                                    6,
                                    600,
                                    "seed",
                                    "renovation",
                                ),
                            ],
                        },
                    },
                    {
                        "name": "L-03",
                        "area_hectares": Decimal("1.50"),
                        "shape": None,
                    },
                ],
            },
            {
                "name": "El Mirador",
                "municipality_code": "54250",
                "details": "Finca pequeña de renovación con clones regionales.",
                "area_hectares": Decimal("4.50"),
                "altitude_masl": 260,
                "latitude": Decimal("8.5781000"),
                "longitude": Decimal("-73.0942000"),
                "plots": [
                    {
                        "name": "M-01",
                        "area_hectares": Decimal("2.00"),
                        "shape": {"east_m": 0, "north_m": 60, "width_m": 160, "height_m": 125},
                        "characterization": {
                            "management_system": "organic",
                            "shade_type": "temporary",
                            "plantings": [
                                _planting("TSH-565", 2024, 1, 1100, "grafted", "early_production"),
                            ],
                        },
                    },
                ],
            },
        ],
    },
    {
        "document_type": "CC",
        "identity_document": "1000000003",
        "first_name": "Rosa Elena",
        "last_name": "Quintero Duarte",
        "email": "rosa.quintero@example.com",
        "municipality_code": "54720",
        "joined_on": date(2020, 8, 1),
        "farms": [
            {
                "name": "Villa Rosa",
                "municipality_code": "54720",
                "details": "",
                "area_hectares": Decimal("8.00"),
                "altitude_masl": 320,
                "latitude": Decimal("8.0843000"),
                "longitude": Decimal("-72.8015000"),
                "plots": [
                    {
                        "name": "VR-1",
                        "area_hectares": Decimal("4.00"),
                        "shape": {"east_m": 0, "north_m": 110, "width_m": 250, "height_m": 160},
                        "characterization": {
                            "management_system": "conventional",
                            "shade_type": "permanent",
                            "plantings": [
                                _planting("CCN-51", 2015, 9, 3200, "grafted", "full_production"),
                            ],
                        },
                    },
                    {
                        "name": "VR-2",
                        "area_hectares": Decimal("2.00"),
                        "shape": {"east_m": 0, "north_m": -110, "width_m": 160, "height_m": 125},
                    },
                ],
            },
        ],
    },
    {
        "document_type": "CC",
        "identity_document": "1000000004",
        "first_name": "Jorge Luis",
        "last_name": "Pabón Sierra",
        "email": "jorge.pabon@example.com",
        "municipality_code": "54261",
        "joined_on": date(2021, 2, 10),
        "farms": [
            {
                "name": "Los Guaduales",
                "municipality_code": "54261",
                "details": "Cerca a la quebrada; parte del lote se inunda en invierno.",
                "area_hectares": Decimal("6.00"),
                "altitude_masl": 240,
                "latitude": Decimal("7.9361000"),
                "longitude": Decimal("-72.6024000"),
                "plots": [
                    {
                        "name": "G-01",
                        "area_hectares": Decimal("3.50"),
                        "shape": {"east_m": 0, "north_m": 0, "width_m": 250, "height_m": 140},
                        "characterization": {
                            "management_system": "conventional",
                            "shade_type": "temporary",
                            "plantings": [
                                _planting("ICS-1", 2019, 11, 2100, "grafted", "full_production"),
                                _planting("ICS-60", 2019, 11, 700, "grafted", "full_production"),
                            ],
                        },
                    },
                ],
            },
        ],
    },
    {
        "document_type": "CE",
        "identity_document": "1000000005",
        "first_name": "Ana Milena",
        "last_name": "Carrascal Vega",
        "email": "ana.carrascal@example.com",
        "municipality_code": "54800",
        "joined_on": date(2022, 6, 20),
        "farms": [
            {
                "name": "Santa Lucía",
                "municipality_code": "54800",
                "details": "",
                "area_hectares": Decimal("5.00"),
                "altitude_masl": 850,
                "latitude": Decimal("8.4372000"),
                "longitude": Decimal("-73.2868000"),
                "plots": [],
            },
        ],
    },
    {
        "document_type": "CC",
        "identity_document": "1000000006",
        "first_name": "Pedro Pablo",
        "last_name": "Contreras Lizcano",
        "email": "pedro.contreras@example.com",
        "municipality_code": "54673",
        "joined_on": date(2018, 11, 5),
        "status": "inactive",
        "farms": [],
    },
]
