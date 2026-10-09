from apps.accounts import registry
from apps.accounts.registry import is_delegable, with_dependencies
from apps.accounts.system_roles import PRODUCER, SYSTEM_ROLES


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


def test_users_delete_is_delegable_and_needs_the_view_permission():
    assert registry.is_delegable("accounts.users_delete")
    assert registry.PERMISSION_DEPENDENCIES["accounts.users_delete"] == "accounts.users_view"
    assert registry.area_of("accounts.users_delete") == "users"


def test_every_permission_of_the_producer_role_can_be_delegated():
    # Por eso la cuenta Productor se protege con una regla explícita (`ensure_can_manage_account`)
    # y no con un permiso que solo ella tenga: un empleado puede llegar a tener todos los suyos.
    assert all(is_delegable(code) for code in SYSTEM_ROLES[PRODUCER]["permissions"])


def test_input_actions_bring_the_permission_to_see_the_catalog():
    for code in (
        "inputs.add_agriculturalinput",
        "inputs.change_agriculturalinput",
        "inputs.delete_agriculturalinput",
        "inputs.manage_inputstock",
    ):
        assert with_dependencies({code}) == {code, "inputs.view_agriculturalinput"}
    assert registry.area_of("inputs.view_agriculturalinput") == "inputs"
