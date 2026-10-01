import pytest

from apps.common.municipalities import municipality_codes_matching
from apps.common.text import fold, normalize_name


@pytest.mark.parametrize(
    "text, expected",
    [("Cúcuta", "cucuta"), ("ÁBREGO", "abrego"), ("Chinácota", "chinacota"), ("", "")],
)
def test_fold_ignores_accents_and_case(text, expected):
    assert fold(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [("  La Esperanza  ", "la esperanza"), (" p-01 ", "p-01"), ("ＰＡＲＣＥＬＡ", "parcela")],
)
def test_normalize_name_trims_and_ignores_case_and_width(text, expected):
    assert normalize_name(text) == expected


def test_municipalities_match_by_name_without_accents():
    assert municipality_codes_matching("cucuta") == ["54001"]
    assert municipality_codes_matching("TIBÚ") == ["54810"]
    assert municipality_codes_matching("zzz") == []
