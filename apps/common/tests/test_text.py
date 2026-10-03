import pytest

from apps.common.text import fold


@pytest.mark.parametrize(
    "text, expected",
    [("Cúcuta", "cucuta"), ("ÁBREGO", "abrego"), ("Chinácota", "chinacota"), ("", "")],
)
def test_fold_ignores_accents_and_case(text, expected):
    assert fold(text) == expected
