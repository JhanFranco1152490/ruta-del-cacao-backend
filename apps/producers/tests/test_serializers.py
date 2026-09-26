from apps.producers.serializers import ProducerStatusSerializer


def test_status_serializer_accepts_both_statuses():
    for value in ("active", "inactive"):
        serializer = ProducerStatusSerializer(data={"status": value, "expected_version": 1})
        assert serializer.is_valid(), serializer.errors


def test_status_serializer_rejects_extra_fields():
    serializer = ProducerStatusSerializer(
        data={"status": "active", "expected_version": 1, "first_name": "Ana"}
    )

    assert not serializer.is_valid()
    assert "first_name" in serializer.errors
