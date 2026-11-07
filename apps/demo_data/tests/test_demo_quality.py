"""La calidad en La Esperanza: lo que deja la semilla y la demostración por la API.

Llama a la semilla directamente y no al comando, para que corra también en Windows."""

from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.accounts.system_roles import QUALITY_MANAGER, get_system_role
from apps.demo_data.catalog import DEMO_FARM, DEMO_PRODUCER_EMAIL, DEMO_QUALITY_EMAIL
from apps.demo_data.seed import seed_demo_data
from apps.lots.choices import LotStatus
from apps.lots.models import Lot
from apps.notifications.models import Notification
from apps.quality.models import LotClassification, LotDiscard, QualityEvaluation

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded():
    seed_demo_data()


def demo_lots(status):
    return Lot.objects.filter(harvest__plot__farm__name=DEMO_FARM, status=status)


def test_the_quality_manager_works_on_every_farm(seeded):
    inspector = User.objects.get(email=DEMO_QUALITY_EMAIL)

    assert inspector.is_active
    assert inspector.all_farms
    assert get_system_role(QUALITY_MANAGER).group in inspector.groups.all()
    assert inspector.check_password("CacaoDemo2026")


def test_the_seed_leaves_a_lot_in_every_quality_state(seeded):
    assert demo_lots(LotStatus.DRIED).count() == 1
    assert demo_lots(LotStatus.EVALUATED).count() == 1
    assert demo_lots(LotStatus.CLASSIFIED).count() == 1
    assert demo_lots(LotStatus.DISCARDED).count() == 1


def test_the_classified_lot_has_a_partial_discard_for_mold(seeded):
    classification = LotClassification.objects.get(lot__harvest__plot__farm__name=DEMO_FARM)

    assert classification.discard_kg > 0
    assert classification.discard_reason == "mold"
    total = classification.g1_kg + classification.g2_kg + classification.discard_kg
    assert total == classification.lot.drying.dry_weight_kg


def test_the_producer_was_told_about_the_discarded_lot(django_capture_on_commit_callbacks):
    # El aviso se guarda al confirmar la transacción de la semilla.
    with django_capture_on_commit_callbacks(execute=True):
        seed_demo_data()
    owner = User.objects.get(email=DEMO_PRODUCER_EMAIL)
    discarded = demo_lots(LotStatus.DISCARDED).get()

    assert Notification.objects.filter(
        recipient=owner, lot=discarded, kind="lot_discarded"
    ).exists()


def test_running_it_again_adds_no_quality_record(seeded):
    before = (
        QualityEvaluation.objects.count(),
        LotClassification.objects.count(),
        LotDiscard.objects.count(),
        Lot.objects.count(),
        Notification.objects.count(),
    )

    seed_demo_data()

    assert (
        QualityEvaluation.objects.count(),
        LotClassification.objects.count(),
        LotDiscard.objects.count(),
        Lot.objects.count(),
        Notification.objects.count(),
    ) == before


def test_after_a_demonstration_it_leaves_again_a_lot_to_evaluate_and_one_to_close(
    seeded, auth_client
):
    client = auth_client(User.objects.get(email=DEMO_QUALITY_EMAIL))
    dried = demo_lots(LotStatus.DRIED).get()
    evaluated = demo_lots(LotStatus.EVALUATED).get()
    client.post(
        f"/api/quality/{dried.pk}/evaluation",
        {
            "expected_lot_version": dried.version,
            "well_fermented_pct": "80.0",
            "moldy_pct": "1.0",
            "other_defects_pct": "3.0",
        },
        format="json",
    )
    client.post(
        f"/api/quality/{evaluated.pk}/discard",
        {"expected_lot_version": evaluated.version, "reason": "contamination"},
        format="json",
    )
    assert not demo_lots(LotStatus.DRIED).exists()

    seed_demo_data()

    assert demo_lots(LotStatus.DRIED).count() == 1
    assert demo_lots(LotStatus.EVALUATED).count() >= 1


def test_the_demonstration_evaluates_fails_to_classify_and_then_classifies(seeded, auth_client):
    client = auth_client(User.objects.get(email=DEMO_QUALITY_EMAIL))
    lot = demo_lots(LotStatus.DRIED).get()
    dry_weight = lot.drying.dry_weight_kg

    evaluated = client.post(
        f"/api/quality/{lot.pk}/evaluation",
        {
            "expected_lot_version": lot.version,
            "well_fermented_pct": "80.0",
            "moldy_pct": "1.0",
            "other_defects_pct": "3.0",
        },
        format="json",
    )
    assert evaluated.status_code == 201, evaluated.data
    version = evaluated.data["lot"]["version"]

    # El caso negativo de la demostración: la suma no llega al peso seco.
    short = client.post(
        f"/api/quality/{lot.pk}/classification",
        {
            "expected_lot_version": version,
            "g1_kg": str(dry_weight - Decimal("10.0")),
            "g2_kg": "0.0",
            "discard_kg": "0.0",
        },
        format="json",
    )
    assert short.status_code == 400
    assert short.data["fields"]["non_field_errors"] == ["Faltan 10,0 kg por distribuir"]

    classified = client.post(
        f"/api/quality/{lot.pk}/classification",
        {
            "expected_lot_version": version,
            "g1_kg": str(dry_weight - Decimal("10.0")),
            "g2_kg": "10.0",
            "discard_kg": "0.0",
        },
        format="json",
    )
    assert classified.status_code == 201, classified.data
    assert classified.data["lot"]["status"] == "classified"


def test_the_demonstration_discards_the_evaluated_lot(seeded, auth_client):
    client = auth_client(User.objects.get(email=DEMO_QUALITY_EMAIL))
    lot = demo_lots(LotStatus.EVALUATED).get()

    response = client.post(
        f"/api/quality/{lot.pk}/discard",
        {"expected_lot_version": lot.version, "reason": "mold"},
        format="json",
    )

    assert response.status_code == 201, response.data
    assert response.data["lot"]["status"] == "discarded"
