from django.db.models import PROTECT
from django.test import SimpleTestCase

from farms.models import Farm


class FarmModelTests(SimpleTestCase):
    def test_farm_has_the_expected_persistent_fields(self):
        fields = {field.name: field for field in Farm._meta.fields}

        self.assertEqual(fields["id"].get_internal_type(), "UUIDField")
        self.assertEqual(fields["producer"].remote_field.on_delete, PROTECT)
        self.assertEqual(fields["name_normalized"].editable, False)
        self.assertEqual(fields["area_hectares"].decimal_places, 2)
        self.assertEqual(fields["latitude"].decimal_places, 7)
        self.assertEqual(fields["longitude"].decimal_places, 7)
        self.assertEqual(fields["version"].default, 1)
