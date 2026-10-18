import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.common.tests.concurrency import run_in_parallel
from apps.health.exceptions import EvidenceLimitReached
from apps.health.models import PhytosanitaryMonitoringEvidence
from apps.health.services.evidence import attach_evidence
from apps.health.tests.factories import PhytosanitaryMonitoringFactory, done_monitoring
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db(transaction=True)

JPEG = b"\xff\xd8\xff\xe0" + b"foto" * 100


def photo():
    return {
        "id": uuid.uuid4(),
        "file": SimpleUploadedFile("mazorca.jpg", JPEG, content_type="image/jpeg"),
        "captured_at": None,
    }


def test_two_uploads_at_once_never_pass_the_limit_of_five():
    plot = PlotFactory()
    owner = make_producer_owner(plot.farm.producer)
    monitoring = PhytosanitaryMonitoringFactory(activity=done_monitoring(plot=plot)).activity
    for _ in range(4):
        attach_evidence(owner, monitoring.pk, photo())

    def attach(_):
        try:
            attach_evidence(owner, monitoring.pk, photo())
            return "saved"
        except EvidenceLimitReached:
            return "limit"

    results = run_in_parallel(attach, [1, 2])

    assert sorted(results) == ["limit", "saved"]
    assert PhytosanitaryMonitoringEvidence.objects.count() == 5
