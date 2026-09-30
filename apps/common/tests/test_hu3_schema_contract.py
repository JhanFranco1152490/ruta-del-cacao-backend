from django.test import SimpleTestCase
from drf_spectacular.generators import SchemaGenerator


class AccountSchemaContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schemas = SchemaGenerator().get_schema(public=True)["components"]["schemas"]

    def test_roles_publish_their_fields_in_sessions_and_accounts(self):
        for name in ("SessionUser", "Account"):
            role = self.schemas[name]["properties"]["roles"]["items"]
            self.assertEqual(role["$ref"], "#/components/schemas/AccountRole")
        self.assertEqual(set(self.schemas["AccountRole"]["properties"]), {"id", "code", "name"})

    def test_producer_detail_allows_empty_contact_email(self):
        detail = self.schemas["ProducerDetail"]["properties"]
        self.assertTrue(detail["email"]["nullable"])
        self.assertTrue(detail["account"]["nullable"])
        self.assertIn("email", self.schemas["ProducerRequest"]["required"])
        self.assertFalse(self.schemas["ProducerRequest"]["properties"]["email"].get("nullable"))
