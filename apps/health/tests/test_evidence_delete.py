import uuid

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.tests.factories import FarmFactory
from apps.health.models import HealthEvidenceAuditEvent, PhytosanitaryMonitoringEvidence
from apps.health.services.evidence import attach_evidence
from apps.health.tests.factories import PhytosanitaryMonitoringFactory, done_monitoring
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

COMPLETE = "activities.complete_agriculturalactivity"
SCHEDULE = "activities.add_agriculturalactivity"
JPEG = b"\xff\xd8\xff\xe0" + b"foto" * 100


def url(evidence) -> str:
    return f"/api/evidence/{evidence.pk}"


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def owner(plot):
    return make_producer_owner(plot.farm.producer)


@pytest.fixture
def foreman(plot):
    return foreman_of(plot.farm)


@pytest.fixture
def monitoring(plot, owner):
    return PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, assignee=owner)
    ).activity


def uploaded_by(account, monitoring):
    evidence, _ = attach_evidence(
        account,
        monitoring.pk,
        {
            "id": uuid.uuid4(),
            "file": SimpleUploadedFile("mazorca.jpg", JPEG, content_type="image/jpeg"),
            "captured_at": None,
        },
    )
    return evidence


def test_whoever_uploaded_it_deletes_it_and_the_file_goes_too(
    auth_client, foreman, monitoring, django_capture_on_commit_callbacks
):
    evidence = uploaded_by(foreman, monitoring)
    stored_name = evidence.file.name
    assert default_storage.exists(stored_name)

    with django_capture_on_commit_callbacks(execute=True):
        response = auth_client(foreman).delete(url(evidence))

    assert response.status_code == 204
    assert not PhytosanitaryMonitoringEvidence.objects.exists()
    assert not default_storage.exists(stored_name)
    event = HealthEvidenceAuditEvent.objects.get(action="deleted")
    assert (event.evidence_ref, event.activity_ref, event.actor) == (
        evidence.pk,
        monitoring.pk,
        foreman,
    )


def test_the_file_stays_if_the_deletion_does_not_commit(auth_client, foreman, monitoring):
    # Sin confirmar la transacción no se borra el archivo: se borra después, con el registro.
    evidence = uploaded_by(foreman, monitoring)

    auth_client(foreman).delete(url(evidence))

    assert default_storage.exists(evidence.file.name)


def test_the_producer_deletes_a_photo_uploaded_by_someone_else(
    auth_client, foreman, owner, monitoring
):
    evidence = uploaded_by(foreman, monitoring)

    assert auth_client(owner).delete(url(evidence)).status_code == 204


def test_the_foreman_deletes_a_photo_uploaded_by_someone_else(
    auth_client, owner, plot, monitoring
):
    evidence = uploaded_by(owner, monitoring)

    assert auth_client(foreman_of(plot.farm)).delete(url(evidence)).status_code == 204


def test_a_custom_role_that_schedules_deletes_it_whatever_its_name(
    auth_client, owner, plot, monitoring
):
    evidence = uploaded_by(owner, monitoring)
    admin_role = make_delegate(plot.farm.producer, [COMPLETE, SCHEDULE], farm=plot.farm)

    assert auth_client(admin_role).delete(url(evidence)).status_code == 204


def test_a_worker_who_only_records_does_not_delete_someone_else_s(
    auth_client, foreman, plot, monitoring
):
    evidence = uploaded_by(foreman, monitoring)
    worker = make_delegate(plot.farm.producer, [COMPLETE], farm=plot.farm)

    response = auth_client(worker).delete(url(evidence))

    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    assert PhytosanitaryMonitoringEvidence.objects.exists()


def test_a_worker_who_only_records_deletes_its_own(auth_client, plot):
    worker = make_delegate(plot.farm.producer, [COMPLETE], farm=plot.farm)
    own = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, assignee=worker)
    ).activity
    evidence = uploaded_by(worker, own)

    assert auth_client(worker).delete(url(evidence)).status_code == 204


def test_an_employee_of_every_farm_who_does_not_schedule_is_not_the_producer(
    auth_client, foreman, plot, monitoring
):
    evidence = uploaded_by(foreman, monitoring)
    everywhere = make_delegate(plot.farm.producer, [COMPLETE], all_farms=True)

    assert auth_client(everywhere).delete(url(evidence)).status_code == 403


def test_when_the_uploader_account_is_gone_the_foreman_or_the_producer_deletes_it(
    auth_client, foreman, owner, plot, monitoring
):
    evidence = uploaded_by(foreman, monitoring)
    PhytosanitaryMonitoringEvidence.objects.filter(pk=evidence.pk).update(uploaded_by=None)
    worker = make_delegate(plot.farm.producer, [COMPLETE], farm=plot.farm)

    assert auth_client(worker).delete(url(evidence)).status_code == 403
    assert auth_client(foreman_of(plot.farm)).delete(url(evidence)).status_code == 204


def test_a_photo_of_another_farm_does_not_exist(auth_client, foreman, plot, monitoring):
    evidence = uploaded_by(foreman, monitoring)
    elsewhere = foreman_of(FarmFactory(producer=plot.farm.producer))

    assert auth_client(elsewhere).delete(url(evidence)).status_code == 404


def test_a_photo_that_does_not_exist_is_a_404(auth_client, owner):
    response = auth_client(owner).delete(f"/api/evidence/{uuid.uuid4()}")

    assert response.status_code == 404


def test_without_the_permission_to_record_it_is_a_403(auth_client, foreman, plot, monitoring):
    evidence = uploaded_by(foreman, monitoring)
    viewer = make_delegate(
        plot.farm.producer, ["activities.view_agriculturalactivity"], farm=plot.farm
    )

    assert auth_client(viewer).delete(url(evidence)).status_code == 403


def test_the_association_does_not_delete_photos(auth_client, foreman, monitoring):
    evidence = uploaded_by(foreman, monitoring)

    assert auth_client(make_administrator()).delete(url(evidence)).status_code == 403


def test_the_history_survives_the_photo(auth_client, owner, monitoring):
    evidence = uploaded_by(owner, monitoring)

    auth_client(owner).delete(url(evidence))

    actions = set(
        HealthEvidenceAuditEvent.objects.filter(evidence_ref=evidence.pk).values_list(
            "action", flat=True
        )
    )
    assert actions == {"uploaded", "deleted"}
