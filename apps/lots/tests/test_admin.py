import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.lots.models import LotAuditEvent, LotCodeSequence
from apps.lots.tests.factories import LotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


def superuser_client():
    return login(UserFactory(is_staff=True, is_superuser=True))


def test_a_superuser_reads_lots_and_nobody_edits_them():
    lot = LotFactory(code="000123-F02-P05-261014-1")
    client = superuser_client()
    url = reverse("admin:lots_lot_change", args=[lot.pk])

    listing = client.get(reverse("admin:lots_lot_changelist"))
    detail = client.get(url)

    assert listing.status_code == 200
    assert "000123-F02-P05-261014-1" in detail.content.decode()
    assert client.get(reverse("admin:lots_lot_add")).status_code == 403
    assert client.post(url, {"code": "OTRO"}).status_code == 403
    deletion = reverse("admin:lots_lot_delete", args=[lot.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403
    lot.refresh_from_db()
    assert lot.code == "000123-F02-P05-261014-1"


def test_the_lot_list_searches_by_code():
    LotFactory(code="000123-F02-P05-261014-1")
    LotFactory(code="000999-F01-P01-260101-1")

    body = (
        superuser_client()
        .get(reverse("admin:lots_lot_changelist"), {"q": "000123"})
        .content.decode()
    )

    assert "000123-F02-P05-261014-1" in body
    assert "000999-F01-P01-260101-1" not in body


def test_staff_with_the_lot_permission_does_not_read_them():
    lot = LotFactory()
    client = login(UserFactory(is_staff=True, permissions=["lots.view_lot"]))

    assert client.get(reverse("admin:lots_lot_changelist")).status_code == 403
    assert client.get(reverse("admin:lots_lot_change", args=[lot.pk])).status_code == 403


def test_the_sequences_and_the_history_are_read_only():
    lot = LotFactory()
    sequence = LotCodeSequence.objects.create(
        plot=lot.harvest.plot, harvest_date=lot.harvest.harvest_date, last_value=1
    )
    event = LotAuditEvent.record(
        lot=lot,
        lot_ref=lot.pk,
        code=lot.code,
        harvest_ref=lot.harvest_id,
        action="created",
        version=1,
    )
    client = superuser_client()

    sequence_url = reverse("admin:lots_lotcodesequence_change", args=[sequence.pk])
    event_url = reverse("admin:lots_lotauditevent_change", args=[event.pk])

    assert client.get(sequence_url).status_code == 200
    assert client.get(event_url).status_code == 200
    assert client.post(sequence_url, {"last_value": 0}).status_code == 403
    assert client.post(event_url, {"action": "deleted"}).status_code == 403
    sequence.refresh_from_db()
    assert sequence.last_value == 1
