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
