import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.health.tests.factories import DetectionFactory, PhytosanitaryTreatmentFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def logged_in(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    "url",
    ["admin:health_phytosanitarymonitoring_change", "admin:health_phytosanitarytreatment_change"],
)
def test_only_a_superuser_reads_the_results_and_they_cannot_be_edited(url):
    treatment = PhytosanitaryTreatmentFactory()
    record = treatment if "treatment" in url else treatment.detection.monitoring
    superuser = logged_in(UserFactory(is_staff=True, is_superuser=True))
    employee = logged_in(
        UserFactory(
            is_staff=True,
            permissions=["activities.view_agriculturalactivity"],
        )
    )

    page = superuser.get(reverse(url, args=[record.pk]))

    assert page.status_code == 200
    assert 'name="_save"' not in page.content.decode()
    assert employee.get(reverse(url, args=[record.pk])).status_code == 403


def test_the_monitoring_shows_its_detections():
    detection = DetectionFactory()
    superuser = logged_in(UserFactory(is_staff=True, is_superuser=True))

    page = superuser.get(
        reverse("admin:health_phytosanitarymonitoring_change", args=[detection.monitoring.pk])
    )

    assert detection.pest_disease.name in page.content.decode()
