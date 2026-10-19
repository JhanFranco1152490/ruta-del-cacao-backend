"""Una finca creada por error se elimina con los cajones y marquesinas que nunca se usaron."""

import pytest

from apps.accounts.tests.role_helpers import make_producer_owner
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.farms.models import Farm

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db


def delete_farm(auth_client, farm):
    client = auth_client(make_producer_owner(farm.producer))
    return client.delete(f"/api/farms/{farm.pk}?expected_version={farm.version}")


def test_a_farm_is_deleted_with_its_facilities_never_used(auth_client):
    facility = PostharvestFacilityFactory()
    farm = facility.farm

    response = delete_farm(auth_client, farm)

    assert response.status_code == 204, response.data
    assert not Farm.objects.filter(pk=farm.pk).exists()
    assert not PostharvestFacility.objects.filter(pk=facility.pk).exists()
    assert PostharvestFacilityAuditEvent.objects.filter(
        facility_ref=facility.pk, action="deleted"
    ).exists()


def test_a_used_facility_keeps_its_farm(auth_client, used_facility):
    farm = used_facility.farm

    response = delete_farm(auth_client, farm)

    assert (response.status_code, response.data["code"]) == (409, "farm_has_records")
    assert Farm.objects.filter(pk=farm.pk).exists()
    assert PostharvestFacility.objects.filter(pk=used_facility.pk).exists()
