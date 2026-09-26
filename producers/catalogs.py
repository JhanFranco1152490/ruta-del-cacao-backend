import unicodedata

from common.territorial import MUNICIPALITIES_BY_CODE as TERRITORIAL_MUNICIPALITIES_BY_CODE

MUNICIPALITIES_BY_CODE = {
    code: municipality.name for code, municipality in TERRITORIAL_MUNICIPALITIES_BY_CODE.items()
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
