import uuid
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.activities.models import AgriculturalActivity
from apps.health.choices import ControlMethod, SamplingMethod, SamplingUnit
from apps.health.exceptions import PestDiseaseInUse
from apps.health.models import Detection, PhytosanitaryMonitoring, PhytosanitaryTreatment
from apps.health.services.catalog import delete_pest_disease
from apps.health.tests.factories import (
    DetectionFactory,
    PestDiseaseFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
)
from apps.inputs.tests.factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db


def rejected_by_the_database(create):
    with pytest.raises(IntegrityError), transaction.atomic():
        create()


# --- Monitoreo ----------------------------------------------------------------------------------


def test_the_result_is_identified_by_its_activity():
    monitoring = PhytosanitaryMonitoringFactory(
        sampling_method=SamplingMethod.ZIGZAG, notes="Foco en la zona baja."
    )

    assert monitoring.pk == monitoring.activity.pk
    assert monitoring.activity.phytosanitary_monitoring == monitoring
    assert monitoring.no_presence is False


def test_the_evaluated_units_are_more_than_zero():
    rejected_by_the_database(lambda: PhytosanitaryMonitoringFactory(evaluated_units=0))


def test_the_sampling_unit_is_one_of_the_two():
    rejected_by_the_database(lambda: PhytosanitaryMonitoringFactory(sampling_unit="leaves"))


def test_the_result_goes_away_with_its_activity():
    detection = DetectionFactory()
    activity = detection.monitoring.activity

    activity.delete()

    assert not PhytosanitaryMonitoring.objects.exists()
    assert not Detection.objects.exists()


# --- Detecciones --------------------------------------------------------------------------------


def test_a_detection_keeps_the_id_of_the_device_and_its_incidence():
    detection_id = uuid.uuid4()

    detection = DetectionFactory(id=detection_id, affected_units=1, incidence=Decimal("33.33"))

    detection.refresh_from_db()
    assert detection.pk == detection_id
    assert detection.incidence == Decimal("33.33")


def test_a_detection_with_other_has_no_catalog_entry():
    detection = DetectionFactory(
        pest_disease=None,
        other_description="Hormigas en hojas",
        normalized_other="hormigasenhojas",
    )

    assert detection.pest_disease is None


@pytest.mark.parametrize(
    "fields",
    [
        # Las dos cosas a la vez.
        {"other_description": "Hormigas", "normalized_other": "hormigas"},
        # Ninguna.
        {"pest_disease": None},
        # Otra sin texto.
        {"pest_disease": None, "other_description": "", "normalized_other": ""},
        # Otra sin su forma normalizada.
        {"pest_disease": None, "other_description": "Hormigas"},
    ],
)
def test_a_detection_is_either_from_the_catalog_or_other(fields):
    rejected_by_the_database(lambda: DetectionFactory(**fields))


def test_the_same_pest_appears_once_per_monitoring():
    first = DetectionFactory()

    rejected_by_the_database(
        lambda: DetectionFactory(monitoring=first.monitoring, pest_disease=first.pest_disease)
    )


def test_the_same_other_text_appears_once_per_monitoring():
    first = DetectionFactory(
        pest_disease=None, other_description="Hormigas", normalized_other="hormigas"
    )

    rejected_by_the_database(
        lambda: DetectionFactory(
            monitoring=first.monitoring,
            pest_disease=None,
            other_description="HORMIGAS",
            normalized_other="hormigas",
        )
    )


def test_the_same_pest_can_appear_in_another_monitoring():
    first = DetectionFactory()

    DetectionFactory(pest_disease=first.pest_disease)

    assert Detection.objects.filter(pest_disease=first.pest_disease).count() == 2


@pytest.mark.parametrize("affected", [0, -1])
def test_the_affected_units_are_more_than_zero(affected):
    rejected_by_the_database(lambda: DetectionFactory(affected_units=affected))


@pytest.mark.parametrize("incidence", [Decimal("-0.01"), Decimal("100.01")])
def test_the_incidence_is_a_percentage(incidence):
    rejected_by_the_database(lambda: DetectionFactory(incidence=incidence))


def test_a_pest_used_in_a_detection_is_not_deleted():
    detection = DetectionFactory()

    with pytest.raises(ProtectedError):
        detection.pest_disease.delete()


def test_the_admin_explains_why_a_pest_in_use_is_not_deleted():
    detection = DetectionFactory()

    with pytest.raises(PestDiseaseInUse):
        delete_pest_disease(detection.pest_disease)


def test_an_unused_pest_is_deleted():
    pest = PestDiseaseFactory()

    delete_pest_disease(pest)

    assert not type(pest).objects.filter(pk=pest.pk).exists()


# --- Controles ----------------------------------------------------------------------------------


def test_a_detection_can_have_several_controls():
    first = PhytosanitaryTreatmentFactory()

    PhytosanitaryTreatmentFactory(detection=first.detection)

    assert first.detection.treatments.count() == 2


def test_a_control_is_identified_by_its_activity():
    treatment = PhytosanitaryTreatmentFactory(method=ControlMethod.FRUIT_REMOVAL)

    assert treatment.pk == treatment.activity.pk
    assert treatment.activity.phytosanitary_treatment == treatment


def test_a_scheduled_control_may_not_say_what_will_be_done():
    treatment = PhytosanitaryTreatmentFactory(method=None)

    assert treatment.method_description is None


@pytest.mark.parametrize(
    "fields",
    [
        {"method": ControlMethod.OTHER},
        {"method": ControlMethod.OTHER, "method_description": ""},
        {"method": ControlMethod.FRUIT_REMOVAL, "method_description": "Quité mazorcas"},
        {"method": None, "method_description": "Algo"},
    ],
)
def test_only_other_describes_what_was_done(fields):
    rejected_by_the_database(lambda: PhytosanitaryTreatmentFactory(**fields))


def test_other_with_its_description_is_valid():
    treatment = PhytosanitaryTreatmentFactory(
        method=ControlMethod.OTHER, method_description="Trampa con melaza"
    )

    assert treatment.method_description == "Trampa con melaza"


def test_a_monitoring_with_controls_cannot_lose_its_detections():
    # El vínculo protege a la detección: el control no puede quedar atendiendo algo que no existe.
    treatment = PhytosanitaryTreatmentFactory()

    with pytest.raises(ProtectedError):
        treatment.detection.monitoring.activity.delete()


def test_deleting_a_scheduled_control_removes_its_link():
    treatment = PhytosanitaryTreatmentFactory()

    AgriculturalActivity.objects.filter(pk=treatment.activity.pk).delete()

    assert not PhytosanitaryTreatment.objects.exists()
    assert Detection.objects.filter(pk=treatment.detection.pk).exists()


def test_a_planned_input_counts_as_used():
    treatment = PhytosanitaryTreatmentFactory()
    item = AgriculturalInputFactory(producer=treatment.activity.plot.farm.producer)
    treatment.planned_input = item
    treatment.save()

    with pytest.raises(ProtectedError):
        item.delete()


def test_sampling_choices_are_the_ones_the_client_sends():
    assert set(SamplingUnit.values) == {"trees", "pods"}
    assert set(SamplingMethod.values) == {"zigzag", "five_of_gold", "diagonal", "all_units"}
    assert set(ControlMethod.values) == {
        "fruit_removal",
        "sanitary_pruning",
        "product_application",
        "other",
    }
