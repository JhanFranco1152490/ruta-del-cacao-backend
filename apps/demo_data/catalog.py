"""Los datos de demostración: dos cuentas para entrar y unos productores con fincas, parcelas y
fichas. Todo es inventado: correos de `example.com` (dominio reservado, nunca entrega correo) y
documentos en secuencia que no corresponden a nadie.

La contraseña es pública a propósito: la pantalla de inicio de sesión la muestra para que quien
evalúa la aplicación entre sin pedir una cuenta. Por eso estas cuentas solo se crean con este
comando, y nunca en un despliegue con datos reales.
"""

from datetime import date
from decimal import Decimal

DEMO_PASSWORD = "CacaoDemo2026"
DEMO_ADMIN_EMAIL = "administrador@example.com"
DEMO_PRODUCER_EMAIL = "productor@example.com"

DEMO_ADMIN = {
    "email": DEMO_ADMIN_EMAIL,
    "document_type": "CC",
    "identity_document": "1000000001",
    "first_name": "Laura",
    "last_name": "Méndez Ortega",
}

NORTE_DE_SANTANDER = "54"


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
                        "code": "L-01",
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
                        "code": "L-02",
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
                        "code": "L-03",
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
                        "code": "M-01",
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
                        "code": "VR-1",
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
                        "code": "VR-2",
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
                        "code": "G-01",
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
