"""Altitud mínima y máxima (m s. n. m.) del terreno de cada municipio de Norte de Santander.

Salen de muestrear una malla dentro del contorno de cada municipio sobre un modelo digital de
elevación de 30 m (SRTM). Es el rango del terreno del municipio, no la altitud de su cabecera: un
municipio puede ir de la llanura a la montaña. El frontend usa la misma tabla para avisar mientras
se escribe, y los dos aplican el mismo margen.
"""

# El muestreo es una malla y el modelo tiene sus errores: sin este margen se rechazaría una finca
# legítima en el borde del rango.
ALTITUDE_MARGIN_M = 100

ALTITUDE_RANGES: dict[str, tuple[int, int]] = {
    "54001": (51, 1547),
    "54003": (398, 3287),
    "54051": (506, 3917),
    "54099": (612, 2925),
    "54109": (409, 2937),
    "54125": (1696, 3738),
    "54128": (155, 3894),
    "54172": (648, 3133),
    "54174": (746, 4368),
    "54206": (61, 1985),
    "54223": (822, 4126),
    "54239": (276, 2063),
    "54245": (73, 2252),
    "54250": (56, 1454),
    "54261": (69, 2313),
    "54313": (555, 3274),
    "54344": (275, 2279),
    "54347": (1439, 3201),
    "54377": (1123, 3683),
    "54385": (52, 3055),
    "54398": (714, 2301),
    "54405": (341, 2301),
    "54418": (582, 3240),
    "54480": (2124, 4115),
    "54498": (509, 2458),
    "54518": (1550, 3802),
    "54520": (1042, 3200),
    "54553": (43, 72),
    "54599": (852, 2549),
    "54660": (395, 3876),
    "54670": (238, 2316),
    "54673": (203, 1490),
    "54680": (282, 2179),
    "54720": (56, 2203),
    "54743": (2060, 4256),
    "54800": (65, 1876),
    "54810": (13, 1632),
    "54820": (288, 3159),
    "54871": (801, 3564),
    "54874": (308, 2006),
}


def altitude_range_for(municipality_code: str) -> tuple[int, int] | None:
    """El rango de altitud que se acepta para una finca de ese municipio, con el margen ya
    aplicado; `None` si no se conoce el municipio."""
    terrain = ALTITUDE_RANGES.get(municipality_code)
    if terrain is None:
        return None
    # Con el margen el mínimo puede quedar bajo el nivel del mar, y Norte de Santander no tiene
    # terreno ahí: decir "de -49 a 1647 m" confunde.
    return max(0, terrain[0] - ALTITUDE_MARGIN_M), terrain[1] + ALTITUDE_MARGIN_M
