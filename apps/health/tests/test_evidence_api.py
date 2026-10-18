import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import AgriculturalActivityFactory, done_activity
from apps.farms.tests.factories import FarmFactory
from apps.health.models import HealthEvidenceAuditEvent, PhytosanitaryMonitoringEvidence
from apps.health.tests.factories import (
    DetectionFactory,
    PhytosanitaryMonitoringFactory,
    PhytosanitaryTreatmentFactory,
    done_monitoring,
)
from apps.plots.tests.factories import PlotFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

COMPLETE = "activities.complete_agriculturalactivity"
MAX_BYTES = 5 * 1024 * 1024
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"foto" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"foto" * 200
PDF = b"%PDF-1.4\n" + b"documento" * 100


def evidence_url(activity) -> str:
    return f"/api/agricultural-activities/{activity.pk}/evidence"


def file_url(evidence_id) -> str:
    return f"/api/evidence/{evidence_id}/file"


def photo(name="mazorca.jpg", content=JPEG, content_type="image/jpeg"):
    return SimpleUploadedFile(name, content, content_type=content_type)


def upload(client, activity, file=None, evidence_id=None):
    return client.post(
        evidence_url(activity),
        {
            "id": str(evidence_id or uuid.uuid4()),
            "file": file or photo(),
            "captured_at": "2026-10-19T15:20:00Z",
        },
        format="multipart",
    )


@pytest.fixture
def plot():
    return PlotFactory()


@pytest.fixture
def owner(plot):
    return make_producer_owner(plot.farm.producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def monitoring(plot, owner):
    """Un monitoreo realizado, a nombre del Productor."""
    return PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, assignee=owner)
    ).activity


@pytest.fixture
def done_control(monitoring, owner):
    detection = DetectionFactory(monitoring=monitoring.phytosanitary_monitoring)
    control = done_activity(
        plot=monitoring.plot,
        activity_type=ActivityType.PHYTOSANITARY_CONTROL,
        assignee=owner,
    )
    return PhytosanitaryTreatmentFactory(activity=control, detection=detection).activity


# --- Subir --------------------------------------------------------------------------------------


def test_a_photo_is_attached_to_a_recorded_monitoring(client, monitoring, owner):
    evidence_id = uuid.uuid4()

    response = upload(client, monitoring, evidence_id=evidence_id)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(evidence_id)
    assert (body["file_name"], body["content_type"], body["size"]) == (
        "mazorca.jpg",
        "image/jpeg",
        len(JPEG),
    )
    assert body["uploaded_by"] == {
        "id": str(owner.pk),
        "full_name": owner.get_full_name() or owner.email,
    }
    event = HealthEvidenceAuditEvent.objects.get()
    assert (event.action, event.evidence_ref, event.activity_ref, event.actor) == (
        "uploaded",
        evidence_id,
        monitoring.pk,
        owner,
    )


def test_the_photos_are_listed_and_counted_in_the_activity(client, monitoring):
    first = upload(client, monitoring, photo("uno.jpg")).json()["id"]
    second = upload(client, monitoring, photo("dos.png", PNG, "image/png")).json()["id"]

    listed = client.get(evidence_url(monitoring)).json()["results"]
    activity = client.get(f"/api/agricultural-activities/{monitoring.pk}").json()

    assert [row["id"] for row in listed] == [first, second]
    assert activity["monitoring"]["evidence_count"] == 2


def test_a_photo_is_attached_to_a_done_control(client, done_control):
    response = upload(client, done_control)

    assert response.status_code == 201
    detail = client.get(f"/api/agricultural-activities/{done_control.pk}").json()
    assert detail["control_of"]["evidence_count"] == 1


def test_the_type_comes_from_the_content_not_from_the_name(client, monitoring):
    response = upload(client, monitoring, photo("disfrazada.jpg", PNG, "image/jpeg"))

    assert response.status_code == 201
    assert response.json()["content_type"] == "image/png"


@pytest.mark.parametrize(
    "name, content, content_type",
    [
        ("informe.pdf", PDF, "application/pdf"),
        # Un PDF que dice ser una foto.
        ("foto.jpg", PDF, "image/jpeg"),
        ("informe.docx", b"PK\x03\x04" + b"x" * 100, "application/octet-stream"),
        ("vacia.jpg", b"", "image/jpeg"),
    ],
)
def test_only_jpg_and_png_photos_are_accepted(client, monitoring, name, content, content_type):
    response = upload(client, monitoring, photo(name, content, content_type))

    assert response.status_code == 415
    assert response.json()["code"] == "evidence_format_not_allowed"
    assert not PhytosanitaryMonitoringEvidence.objects.exists()


def test_a_photo_over_5_mb_is_rejected(client, monitoring):
    big = JPEG + b"x" * (MAX_BYTES - len(JPEG) + 1)

    response = upload(client, monitoring, photo("grande.jpg", big))

    assert response.status_code == 413
    assert response.json()["code"] == "evidence_too_large"
    assert not PhytosanitaryMonitoringEvidence.objects.exists()


def test_a_photo_of_exactly_5_mb_is_accepted(client, monitoring):
    exact = JPEG + b"x" * (MAX_BYTES - len(JPEG))

    assert upload(client, monitoring, photo("justa.jpg", exact)).status_code == 201


def test_a_huge_body_is_rejected_before_reading_it(client, monitoring):
    response = client.generic(
        "POST",
        evidence_url(monitoring),
        b"x" * 10,
        content_type="multipart/form-data; boundary=limite",
        CONTENT_LENGTH=str(50 * 1024 * 1024),
    )

    assert response.status_code == 413
    assert response.json()["code"] == "evidence_too_large"


def test_without_a_file_it_is_a_400(client, monitoring):
    response = client.post(evidence_url(monitoring), {"id": str(uuid.uuid4())}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.json()["fields"]


def test_the_device_path_is_not_kept_in_the_name(client, monitoring):
    response = upload(client, monitoring, photo("C:\\fakepath\\mazorca enferma.jpg"))

    assert response.json()["file_name"] == "mazorca enferma.jpg"


def test_a_monitoring_still_scheduled_takes_no_photos(client, plot, owner):
    scheduled = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=owner
    )

    response = upload(client, scheduled)

    assert response.status_code == 409
    assert response.json()["code"] == "evidence_requires_done"


def test_a_scheduled_control_takes_no_photos(client, monitoring, owner):
    treatment = PhytosanitaryTreatmentFactory(
        detection=DetectionFactory(monitoring=monitoring.phytosanitary_monitoring)
    )

    response = upload(client, treatment.activity)

    assert response.status_code == 409
    assert response.json()["code"] == "evidence_requires_done"


def test_other_activities_take_no_photos_here(client, plot, owner):
    pruning = done_activity(plot=plot, assignee=owner)

    response = upload(client, pruning)

    assert response.status_code == 422
    assert response.json()["code"] == "evidence_not_allowed"


def test_up_to_five_photos_per_record(client, monitoring):
    for _ in range(5):
        assert upload(client, monitoring).status_code == 201

    response = upload(client, monitoring)

    assert response.status_code == 409
    assert response.json()["code"] == "evidence_limit_reached"
    assert PhytosanitaryMonitoringEvidence.objects.count() == 5


def test_the_same_photo_sent_again_is_a_200(client, monitoring):
    evidence_id = uuid.uuid4()
    upload(client, monitoring, evidence_id=evidence_id)

    response = upload(client, monitoring, evidence_id=evidence_id)

    assert response.status_code == 200
    assert PhytosanitaryMonitoringEvidence.objects.count() == 1


def test_an_id_used_in_another_record_is_a_400(client, monitoring, done_control):
    evidence_id = uuid.uuid4()
    upload(client, monitoring, evidence_id=evidence_id)

    response = upload(client, done_control, evidence_id=evidence_id)

    assert response.status_code == 400
    assert "id" in response.json()["fields"]


# --- Quién sube ---------------------------------------------------------------------------------


def foreman_of(farm):
    return grant_role(UserFactory(producer=farm.producer, farms=[farm]), get_system_role(FOREMAN))


def test_the_foreman_attaches_photos_days_later(auth_client, monitoring, plot):
    assert upload(auth_client(foreman_of(plot.farm)), monitoring).status_code == 201


def test_the_assignee_attaches_to_its_own(auth_client, plot):
    worker = make_delegate(plot.farm.producer, [COMPLETE], farm=plot.farm)
    own = PhytosanitaryMonitoringFactory(
        activity=done_monitoring(plot=plot, assignee=worker)
    ).activity

    assert upload(auth_client(worker), own).status_code == 201


def test_a_worker_does_not_attach_to_a_colleague_s_record(auth_client, monitoring, plot):
    worker = make_delegate(plot.farm.producer, [COMPLETE], farm=plot.farm)

    response = upload(auth_client(worker), monitoring)

    assert response.status_code == 403
    assert not PhytosanitaryMonitoringEvidence.objects.exists()


def test_another_farm_gets_a_404(auth_client, monitoring, plot):
    other = foreman_of(FarmFactory(producer=plot.farm.producer))

    assert upload(auth_client(other), monitoring).status_code == 404
    assert auth_client(other).get(evidence_url(monitoring)).status_code == 404


def test_the_association_gets_a_403(auth_client, monitoring):
    assert upload(auth_client(make_administrator()), monitoring).status_code == 403


def test_without_a_session_it_is_a_401(api_client, monitoring):
    assert upload(api_client, monitoring).status_code == 401


# --- Ver la foto --------------------------------------------------------------------------------


def test_the_photo_is_served_after_checking_the_farm(client, monitoring):
    evidence_id = upload(client, monitoring, photo("mazorca.jpg")).json()["id"]

    response = client.get(file_url(evidence_id))

    assert response.status_code == 200
    assert b"".join(response.streaming_content) == JPEG
    assert response["Content-Type"] == "image/jpeg"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Disposition"] == 'inline; filename="mazorca.jpg"'
    cache = response["Cache-Control"]
    assert "private" in cache and "no-store" in cache


def test_the_photo_of_a_control_is_served_too(client, done_control):
    evidence_id = upload(client, done_control).json()["id"]

    assert client.get(file_url(evidence_id)).status_code == 200


def test_the_photo_of_another_farm_does_not_exist(auth_client, client, monitoring, plot):
    evidence_id = upload(client, monitoring).json()["id"]
    other = foreman_of(FarmFactory(producer=plot.farm.producer))

    response = auth_client(other).get(file_url(evidence_id))

    assert response.status_code == 404


def test_a_photo_that_does_not_exist_is_a_404(client):
    assert client.get(file_url(uuid.uuid4())).status_code == 404


def test_the_scheduled_monitoring_lists_no_photos(client, plot, owner):
    scheduled = AgriculturalActivityFactory(
        plot=plot, activity_type=ActivityType.PHYTOSANITARY_MONITORING, assignee=owner
    )

    response = client.get(evidence_url(scheduled))

    assert response.json() == {"results": []}
