import pytest

from apps.crops.text import normalize_variety_name


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
    assert normalize_variety_name(name) == "ccn51"


def test_accents_do_not_distinguish_names():
    assert normalize_variety_name("Híbrido o común") == normalize_variety_name("hibrido o comun")


def test_other_characters_still_distinguish_names():
    assert normalize_variety_name("ICS-1") != normalize_variety_name("ICS-10")
    assert normalize_variety_name("FSA-11") != normalize_variety_name("FSA 1-1.")
