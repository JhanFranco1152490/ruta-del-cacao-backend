import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.crops.models import CacaoVariety, CacaoVarietyAuditEvent
from apps.crops.tests.factories import CacaoVarietyFactory, PlotCharacterizationVarietyFactory

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.usefixtures("plain_static_files", "empty_catalog"),
]

MANAGE = "crops.manage_cacaovariety"


def staff(*permissions):
    user = UserFactory(is_staff=True, permissions=list(permissions))
    client = Client()
    client.force_login(user)
    return client, user


def changelist_url():
    return reverse("admin:crops_cacaovariety_changelist")


def add_url():
    return reverse("admin:crops_cacaovariety_add")


def change_url(variety):
    return reverse("admin:crops_cacaovariety_change", args=[variety.pk])


def delete_url(variety):
    return reverse("admin:crops_cacaovariety_delete", args=[variety.pk])


def test_the_admin_needs_the_catalog_permission():
    without, _ = staff()
    manager, _ = staff(MANAGE)

    assert without.get(changelist_url()).status_code == 403
    assert manager.get(changelist_url()).status_code == 200


def test_adding_from_the_admin_normalizes_and_leaves_the_event():
    client, user = staff(MANAGE)

    response = client.post(add_url(), {"name": " ABC – 12 ", "description": "", "is_active": "on"})

    assert response.status_code == 302
    variety = CacaoVariety.objects.get()
    assert (variety.name, variety.name_normalized) == ("ABC – 12", "abc12")
    event = CacaoVarietyAuditEvent.objects.get(action=CacaoVarietyAuditEvent.Action.CREATED)
    assert event.actor == user


def test_the_admin_rejects_a_repeated_name_without_saving():
    CacaoVarietyFactory(name="CCN-51")
    client, _ = staff(MANAGE)

    response = client.post(add_url(), {"name": "ccn 51", "description": "", "is_active": "on"})

    assert response.status_code == 200
    assert "Ya existe una variedad con este nombre." in response.content.decode()
    assert CacaoVariety.objects.count() == 1


def test_editing_from_the_admin_leaves_its_events():
    variety = CacaoVarietyFactory(name="ABC-12")
    client, _ = staff(MANAGE)

    client.post(change_url(variety), {"name": "ABC-13", "description": ""})

    variety.refresh_from_db()
    assert (variety.name, variety.is_active) == ("ABC-13", False)
    actions = set(
        CacaoVarietyAuditEvent.objects.filter(variety_ref=variety.pk).values_list(
            "action", flat=True
        )
    )
    assert actions == {
        CacaoVarietyAuditEvent.Action.UPDATED,
        CacaoVarietyAuditEvent.Action.STATUS_CHANGED,
    }


def test_deleting_an_unused_variety_keeps_its_history():
    variety = CacaoVarietyFactory(name="ABC-12")
    client, user = staff(MANAGE)

    response = client.post(delete_url(variety), {"post": "yes"})

    assert response.status_code == 302
    assert not CacaoVariety.objects.exists()
    event = CacaoVarietyAuditEvent.objects.get(action=CacaoVarietyAuditEvent.Action.DELETED)
    assert (event.variety, event.variety_ref, event.variety_name) == (None, variety.pk, "ABC-12")
    assert event.actor == user


def test_deleting_several_from_the_list_leaves_one_event_each():
    varieties = CacaoVarietyFactory.create_batch(2)
    client, _ = staff(MANAGE)

    client.post(
        changelist_url(),
        {
            "action": "delete_selected",
            "_selected_action": [str(variety.pk) for variety in varieties],
            "post": "yes",
        },
    )

    assert not CacaoVariety.objects.exists()
    assert (
        CacaoVarietyAuditEvent.objects.filter(action=CacaoVarietyAuditEvent.Action.DELETED).count()
        == 2
    )


def test_a_variety_in_use_is_not_deleted():
    row = PlotCharacterizationVarietyFactory()
    client, _ = staff(MANAGE)

    client.post(delete_url(row.variety), {"post": "yes"})

    assert CacaoVariety.objects.filter(pk=row.variety.pk).exists()
    assert not CacaoVarietyAuditEvent.objects.exists()
