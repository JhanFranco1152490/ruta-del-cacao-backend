import pytest

from apps.common.municipalities import municipality_codes_matching
from apps.common.text import fold


@pytest.mark.parametrize(
    "text, expected",
    [("Cúcuta", "cucuta"), ("ÁBREGO", "abrego"), ("Chinácota", "chinacota"), ("", "")],
)
def test_fold_ignores_accents_and_case(text, expected):
    assert fold(text) == expected


def test_municipalities_match_by_name_without_accents():
    assert municipality_codes_matching("cucuta") == ["54001"]
    assert municipality_codes_matching("TIBÚ") == ["54810"]
    assert municipality_codes_matching("zzz") == []
