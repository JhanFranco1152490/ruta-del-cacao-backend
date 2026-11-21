from datetime import date
from decimal import Decimal

import pytest

from apps.lots.history import HarvestData, LotCreatedData, created_stage, harvest_stage
from apps.lots.tests.factories import LotFactory

pytestmark = pytest.mark.django_db


def test_the_harvest_stage_is_the_origin_of_the_lot():
    lot = LotFactory(
        harvest__harvest_date=date(2026, 3, 14),
        harvest__green_weight_kg=Decimal("120.0"),
        harvest__collector__first_name="Luis",
        harvest__collector__last_name="Peña",
    )
    harvest = lot.harvest

    stage = harvest_stage(lot)

    assert stage.kind == "harvest"
    assert stage.occurred_on == date(2026, 3, 14)
    assert stage.occurred_at is None
    assert stage.recorded_at == harvest.created_at
    assert stage.data == HarvestData(
        harvest_id=harvest.pk,
        variety=harvest.variety.name,
        characterization_version=harvest.characterization_version,
        collector="Luis Peña",
        green_weight_kg=Decimal("120.0"),
    )


def test_the_created_stage_says_who_formed_the_lot_and_when():
    lot = LotFactory(created_by__first_name="Rosa", created_by__last_name="Quintero")

    stage = created_stage(lot)

    assert stage.kind == "lot_created"
    assert stage.occurred_at == lot.created_at
    assert stage.recorded_at == lot.created_at
    assert stage.data == LotCreatedData(created_by="Rosa Quintero")


def test_a_lot_formed_by_a_deleted_account_has_no_name():
    lot = LotFactory(created_by=None)

    assert created_stage(lot).data == LotCreatedData(created_by=None)
