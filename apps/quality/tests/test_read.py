"""Consultar la calidad: la pantalla de trabajo, su recuento, la ficha y el campo del lote."""

from datetime import datetime, time, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_delegate
from apps.common.serializers import full_name
from apps.lots.choices import LotStatus

from .helpers import QualityEstate, discarded, dried_lot

pytestmark = pytest.mark.django_db

URL = "/api/quality"


@pytest.fixture
def estate():
    return QualityEstate()


def codes(response):
    assert response.status_code == 200, response.data
    return [row["lot"]["code"] for row in response.data["results"]]


# --- La lista ---


def test_by_default_it_lists_the_dried_lots_from_the_oldest_dried(auth_client, estate):
    response = auth_client(estate.owner).get(URL)

    assert codes(response) == [estate.dried_old.code, estate.dried_b.code, estate.dried_new.code]
    assert response.data["count"] == 3


def test_a_lot_to_evaluate_shows_its_dry_weight_and_no_evaluation(auth_client, estate):
    row = auth_client(estate.owner).get(URL).data["results"][0]

    assert row["lot"] == {
        "id": str(estate.dried_old.pk),
        "code": estate.dried_old.code,
        "status": "dried",
        "version": 1,
    }
    assert row["farm"] == {
        "id": str(estate.farm_a.pk),
        "code": estate.farm_a.code,
        "name": estate.farm_a.name,
    }
    assert (row["dry_weight_kg"], row["final_moisture_pct"]) == ("313.2", "7.0")
    assert row["drying_ended_at"] is not None
    assert (row["evaluation"], row["classification"], row["discard"]) == (None, None, None)


def test_the_evaluated_view_lists_the_lots_with_their_evaluation(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"view": "evaluated"})

    assert codes(response) == [estate.evaluated.code]
    evaluation = response.data["results"][0]["evaluation"]
    assert evaluation["well_fermented_pct"] == "78.5"
    assert (evaluation["moldy_pct"], evaluation["other_defects_pct"]) == ("2.0", "4.5")
    assert evaluation["evaluated_by"] == {
        "id": str(estate.inspector.pk),
        "full_name": full_name(estate.inspector),
    }
    assert (evaluation["corrected_by"], evaluation["corrected_at"], evaluation["version"]) == (
        None,
        None,
        1,
    )


def test_the_closed_view_lists_classified_and_discarded_from_the_newest(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"view": "closed"})

    # El descarte fue hace dos horas y la clasificación hace tres.
    assert codes(response) == [estate.discarded.code, estate.classified.code]
    discard, classification = response.data["results"]
    assert discard["discard"]["reason"] == "mold"
    assert discard["classification"] is None
    assert classification["classification"] == {
        "g1_kg": "250.0",
        "g2_kg": "55.2",
        "discard_kg": "8.0",
        "discard_reason": "mold",
        "discard_detail": "",
        "classified_at": classification["classification"]["classified_at"],
        "classified_by": {
            "id": str(estate.inspector.pk),
            "full_name": full_name(estate.inspector),
        },
    }


@pytest.mark.parametrize("view", ["to_evaluate", "evaluated", "closed"])
def test_a_lot_still_drying_is_never_listed(auth_client, estate, view):
    assert estate.drying.code not in codes(auth_client(estate.owner).get(URL, {"view": view}))


def test_an_unknown_view_is_refused(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"view": "sold"})

    assert response.status_code == 400
    assert "view" in response.data["fields"]


def test_the_list_filters_by_farm_and_by_part_of_the_code(auth_client, estate):
    client = auth_client(estate.owner)

    assert codes(client.get(URL, {"farm": str(estate.farm_b.pk)})) == [estate.dried_b.code]
    term = estate.dried_new.code[-12:].lower()
    assert codes(client.get(URL, {"search": term})) == [estate.dried_new.code]


# --- Alcance y permisos ---


def test_the_quality_manager_lists_only_the_lots_of_its_farms(auth_client, estate):
    listed = codes(auth_client(estate.inspector).get(URL))

    assert listed == [estate.dried_old.code, estate.dried_new.code]


def test_a_quality_manager_without_farms_lists_nothing(auth_client, estate):
    unassigned = make_delegate(estate.producer, ["quality.evaluate_lot"])

    assert codes(auth_client(unassigned).get(URL)) == []


def test_another_producer_sees_none_of_these_lots(auth_client, estate):
    other = QualityEstate()

    listed = codes(auth_client(other.owner).get(URL))

    assert estate.dried_old.code not in listed


def test_the_technical_account_filters_by_producer(auth_client, estate):
    QualityEstate()
    technical = UserFactory(is_superuser=True)

    listed = codes(auth_client(technical).get(URL, {"producer": str(estate.producer.pk)}))

    assert listed == [estate.dried_old.code, estate.dried_b.code, estate.dried_new.code]


def test_without_the_evaluation_permission_the_screen_is_forbidden(auth_client, estate):
    foreman = grant_role(
        UserFactory(producer=estate.producer, farm=estate.farm_a), get_system_role(FOREMAN)
    )
    client = auth_client(foreman)

    assert client.get(URL).status_code == 403
    assert client.get(f"{URL}/summary").status_code == 403
    assert client.get(f"{URL}/{estate.dried_old.pk}").status_code == 403


def test_without_a_session_it_is_401(anonymous_client):
    assert anonymous_client.get(URL).status_code == 401


def close_on(estate, lot, day, *, at=time(12, 0)):
    """Mueve el cierre de un lote cerrado a ese día, a esa hora de Bogotá."""
    moment = timezone.make_aware(datetime.combine(day, at))
    if lot == estate.classified:
        lot.classification.classified_at = moment
        lot.classification.save()
    else:
        lot.discard.discarded_at = moment
        lot.discard.save()


def test_the_closed_view_filters_by_result(auth_client, estate):
    client = auth_client(estate.owner)

    discarded = client.get(URL, {"view": "closed", "result": "discarded"})
    classified = client.get(URL, {"view": "closed", "result": "classified"})

    assert codes(discarded) == [estate.discarded.code]
    assert codes(classified) == [estate.classified.code]


def test_the_closed_view_filters_by_the_closing_period_with_both_days_included(
    auth_client, estate
):
    today = timezone.localdate()
    close_on(estate, estate.classified, today - timedelta(days=10), at=time(0, 0))
    close_on(estate, estate.discarded, today - timedelta(days=3), at=time(23, 59))
    client = auth_client(estate.owner)

    def listed(**period):
        return codes(client.get(URL, {"view": "closed", **period}))

    first, second = estate.discarded.code, estate.classified.code
    assert listed(closed_from=str(today - timedelta(days=10))) == [first, second]
    assert listed(closed_from=str(today - timedelta(days=9))) == [first]
    assert listed(closed_to=str(today - timedelta(days=3))) == [first, second]
    assert listed(closed_to=str(today - timedelta(days=4))) == [second]
    assert listed(
        closed_from=str(today - timedelta(days=3)), closed_to=str(today - timedelta(days=3))
    ) == [first]
    assert listed(closed_from=str(today + timedelta(days=1))) == []


def test_the_result_and_the_period_only_act_on_the_closed_view(auth_client, estate):
    today = timezone.localdate()
    response = auth_client(estate.owner).get(
        URL, {"view": "evaluated", "result": "discarded", "closed_from": str(today)}
    )

    assert codes(response) == [estate.evaluated.code]


@pytest.mark.parametrize(
    "query",
    [
        {"result": "evaluated"},
        {"closed_from": "ayer"},
        {"closed_from": "2026-11-05", "closed_to": "2026-11-04"},
    ],
)
def test_a_wrong_result_or_period_is_refused(auth_client, estate, query):
    response = auth_client(estate.owner).get(URL, {"view": "closed", **query})

    assert response.status_code == 400


# --- Lo que dejó el periodo ---


def test_the_closed_totals_add_the_grades_and_what_was_left_out(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/closed-summary")

    assert response.status_code == 200
    # 8,0 kg de descarte parcial más los 313,2 kg del lote descartado completo.
    assert response.data == {
        "classified": 1,
        "discarded": 1,
        "g1_kg": "250.0",
        "g2_kg": "55.2",
        "discarded_kg": "321.2",
    }


def test_the_closed_totals_follow_the_period_and_are_zero_without_lots(auth_client, estate):
    today = timezone.localdate()
    close_on(estate, estate.classified, today - timedelta(days=40))
    client = auth_client(estate.owner)

    recent = client.get(f"{URL}/closed-summary", {"closed_from": str(today - timedelta(days=7))})
    none = client.get(f"{URL}/closed-summary", {"closed_from": str(today + timedelta(days=1))})

    assert (recent.data["classified"], recent.data["discarded"]) == (0, 1)
    assert recent.data["g1_kg"] == "0.0"
    assert none.data == {
        "classified": 0,
        "discarded": 0,
        "g1_kg": "0.0",
        "g2_kg": "0.0",
        "discarded_kg": "0.0",
    }


def test_the_closed_totals_respect_the_reach_and_the_permission(auth_client, estate):
    foreman = UserFactory(producer=estate.producer, farm=estate.farm_a)
    grant_role(foreman, get_system_role(FOREMAN))

    assert auth_client(estate.inspector).get(f"{URL}/closed-summary").data["classified"] == 1
    assert auth_client(foreman).get(f"{URL}/closed-summary").status_code == 403
    other = QualityEstate()
    # Cada productor suma solo lo suyo: con los dos juntos serían 500,0 kg de G1.
    assert auth_client(other.owner).get(f"{URL}/closed-summary").data["g1_kg"] == "250.0"


# --- El recuento ---


def test_the_summary_counts_what_waits_and_what_was_discarded_this_month(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/summary")

    assert response.status_code == 200
    assert response.data == {
        "to_evaluate": 3,
        "to_evaluate_kg": "939.6",
        "evaluated": 1,
        "discarded_this_month": 1,
    }


def test_a_discard_of_a_previous_month_does_not_count(auth_client, estate):
    old = dried_lot(estate.plot_a, status=LotStatus.DISCARDED)
    discard = discarded(old, estate.owner)
    first_of_month = timezone.localdate().replace(day=1)
    discard.discarded_at = timezone.now() - timedelta(days=timezone.localdate().day)
    discard.save()
    assert timezone.localdate(discard.discarded_at) < first_of_month

    assert auth_client(estate.owner).get(f"{URL}/summary").data["discarded_this_month"] == 1


def test_the_summary_respects_the_farm_and_the_reach(auth_client, estate):
    by_farm = auth_client(estate.owner).get(f"{URL}/summary", {"farm": str(estate.farm_b.pk)})
    inspector = auth_client(estate.inspector).get(f"{URL}/summary")

    assert (by_farm.data["to_evaluate"], by_farm.data["discarded_this_month"]) == (1, 0)
    assert inspector.data["to_evaluate"] == 2


# --- La ficha ---


def test_the_detail_of_a_lot_in_quality(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/{estate.classified.pk}")

    assert response.status_code == 200
    assert response.data["lot"]["status"] == "classified"
    assert response.data["evaluation"]["moldy_pct"] == "2.0"
    assert response.data["classification"]["g1_kg"] == "250.0"


def test_a_lot_before_dried_has_no_quality_detail(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/{estate.drying.pk}")

    assert response.status_code == 404


def test_a_lot_outside_the_reach_has_no_quality_detail(auth_client, estate):
    response = auth_client(estate.inspector).get(f"{URL}/{estate.dried_b.pk}")

    assert response.status_code == 404


# --- El campo `quality` del lote ---


def lot_quality(client, lot):
    response = client.get(f"/api/lots/{lot.pk}")
    assert response.status_code == 200, response.data
    return response.data["quality"]


def test_a_lot_without_evaluation_has_no_quality(auth_client, estate):
    assert lot_quality(auth_client(estate.owner), estate.dried_old) is None


def test_an_evaluated_lot_shows_its_percentages(auth_client, estate):
    quality = lot_quality(auth_client(estate.owner), estate.evaluated)

    assert quality["well_fermented_pct"] == "78.5"
    assert (quality["g1_kg"], quality["discard_reason"], quality["discarded_at"]) == (
        None,
        None,
        None,
    )


def test_a_classified_lot_shows_its_grades(auth_client, estate):
    quality = lot_quality(auth_client(estate.owner), estate.classified)

    assert (quality["g1_kg"], quality["g2_kg"], quality["discard_kg"]) == (
        "250.0",
        "55.2",
        "8.0",
    )
    assert (quality["discard_reason"], quality["discarded_at"]) == ("mold", None)


def test_a_discarded_lot_shows_why_and_when(auth_client, estate):
    quality = lot_quality(auth_client(estate.owner), estate.discarded)

    assert (quality["g1_kg"], quality["g2_kg"], quality["discard_kg"]) == (None, None, None)
    assert quality["discard_reason"] == "mold"
    assert quality["discarded_at"] is not None


def test_the_lot_list_does_not_query_once_per_lot_for_its_quality(auth_client, estate):
    client = auth_client(estate.owner)

    def queries():
        with CaptureQueriesContext(connection) as captured:
            assert client.get("/api/lots").status_code == 200
        return len(captured)

    before = queries()
    discarded(dried_lot(estate.plot_a, status=LotStatus.DISCARDED), estate.owner)
    discarded(dried_lot(estate.plot_b, status=LotStatus.DISCARDED), estate.owner)

    assert queries() == before


def test_the_quality_list_does_not_query_once_per_lot(auth_client, estate):
    client = auth_client(estate.owner)

    def queries():
        with CaptureQueriesContext(connection) as captured:
            assert client.get(URL, {"view": "closed"}).status_code == 200
        return len(captured)

    before = queries()
    discarded(dried_lot(estate.plot_a, status=LotStatus.DISCARDED), estate.owner)

    assert queries() == before


# --- Un lote que bodega ya guardó sigue cerrado ---


@pytest.fixture
def stored(estate):
    """El lote clasificado de la finca, ya guardado en una bodega."""
    type(estate.classified).objects.filter(pk=estate.classified.pk).update(
        status=LotStatus.IN_WAREHOUSE
    )
    return estate.classified


def test_a_stored_lot_stays_in_the_closed_view(auth_client, estate, stored):
    client = auth_client(estate.owner)

    closed = codes(client.get(URL, {"view": "closed"}))
    classified = codes(client.get(URL, {"view": "closed", "result": "classified"}))
    discarded = codes(client.get(URL, {"view": "closed", "result": "discarded"}))

    assert closed == [estate.discarded.code, stored.code]
    assert classified == [stored.code]
    assert discarded == [estate.discarded.code]


def test_a_stored_lot_is_not_listed_to_evaluate_or_evaluated(auth_client, estate, stored):
    client = auth_client(estate.owner)

    assert stored.code not in codes(client.get(URL, {"view": "to_evaluate"}))
    assert stored.code not in codes(client.get(URL, {"view": "evaluated"}))


def test_the_closed_totals_keep_counting_a_stored_lot(auth_client, estate, stored):
    response = auth_client(estate.owner).get(f"{URL}/closed-summary")

    assert response.data["classified"] == 1
    assert response.data["g1_kg"] == "250.0"
    assert response.data["g2_kg"] == "55.2"
    assert response.data["discarded_kg"] == "321.2"


def test_a_stored_lot_keeps_its_quality_detail(auth_client, estate, stored):
    response = auth_client(estate.owner).get(f"{URL}/{stored.pk}")

    assert response.status_code == 200
    assert response.data["lot"]["status"] == "in_warehouse"
    assert response.data["classification"]["g1_kg"] == "250.0"
