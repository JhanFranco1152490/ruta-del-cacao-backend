import unicodedata

MUNICIPALITIES_BY_CODE = {
    "54001": "C\u00facuta",
    "54003": "\u00c1brego",
    "54051": "Arboledas",
    "54099": "Bochalema",
    "54109": "Bucarasica",
    "54125": "C\u00e1cota",
    "54128": "C\u00e1chira",
    "54172": "Chin\u00e1cota",
    "54174": "Chitag\u00e1",
    "54206": "Convenci\u00f3n",
    "54223": "Cucutilla",
    "54239": "Durania",
    "54245": "El Carmen",
    "54250": "El Tarra",
    "54261": "El Zulia",
    "54313": "Gramalote",
    "54344": "Hacar\u00ed",
    "54347": "Herr\u00e1n",
    "54377": "Labateca",
    "54385": "La Esperanza",
    "54398": "La Playa",
    "54405": "Los Patios",
    "54418": "Lourdes",
    "54480": "Mutiscua",
    "54498": "Oca\u00f1a",
    "54518": "Pamplona",
    "54520": "Pamplonita",
    "54553": "Puerto Santander",
    "54599": "Ragonvalia",
    "54660": "Salazar",
    "54670": "San Calixto",
    "54673": "San Cayetano",
    "54680": "Santiago",
    "54720": "Sardinata",
    "54743": "Silos",
    "54800": "Teorama",
    "54810": "Tib\u00fa",
    "54820": "Toledo",
    "54871": "Villa Caro",
    "54874": "Villa del Rosario",
}


def list_municipalities():
    return [
        {"code": code, "name": name}
        for code, name in sorted(
            MUNICIPALITIES_BY_CODE.items(),
            key=lambda item: unicodedata.normalize("NFKD", item[1])
            .encode("ascii", "ignore")
            .decode()
            .casefold(),
        )
    ]
