import pytest

from apps.common.text import fold, normalize_catalog_name, normalize_name


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


@pytest.mark.parametrize(
    "name",
    [
        "CCN-51",
        "CCN 51",
        "CCN51",
        "ccn-51",
        " CCN 51 ",
        "CCN – 51",
        "CCN—51",
        "CCN‐51",
        "CCN‑51",
        "CCN‒51",
        "CCN−51",
        "CCN 51",
        "CCN\t-\t51",
    ],
)
def test_the_usual_ways_of_writing_a_clone_are_the_same_name(name):
    assert normalize_catalog_name(name) == "ccn51"


def test_accents_do_not_distinguish_names():
    assert normalize_catalog_name("Híbrido o común") == normalize_catalog_name("hibrido o comun")


def test_other_characters_still_distinguish_names():
    assert normalize_catalog_name("ICS-1") != normalize_catalog_name("ICS-10")
    assert normalize_catalog_name("FSA-11") != normalize_catalog_name("FSA 1-1.")
