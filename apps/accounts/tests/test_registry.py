from apps.accounts import registry
from apps.accounts.registry import with_dependencies


def test_with_dependencies_adds_the_view_permission_of_an_action():
    assert with_dependencies({"farms.add_farm"}) == {"farms.add_farm", "farms.view_farm"}


def test_with_dependencies_follows_a_chain_to_the_end(monkeypatch):
    monkeypatch.setattr(
        registry,
        "PERMISSION_DEPENDENCIES",
        {"app.add_child": "app.view_child", "app.view_child": "app.view_parent"},
    )

    assert with_dependencies({"app.add_child"}) == {
        "app.add_child",
        "app.view_child",
        "app.view_parent",
    }


def test_with_dependencies_keeps_codes_without_dependencies():
    assert with_dependencies({"accounts.users_view"}) == {"accounts.users_view"}


def test_characterizing_plots_brings_the_permissions_to_see_the_plot_and_its_farm():
    assert with_dependencies({"crops.change_plotcharacterization"}) == {
        "crops.change_plotcharacterization",
        "plots.view_plot",
        "farms.view_farm",
    }


def test_adding_plots_brings_the_permissions_to_see_them_and_their_farm():
    assert with_dependencies({"plots.add_plot"}) == {
        "plots.add_plot",
        "plots.view_plot",
        "farms.view_farm",
    }
