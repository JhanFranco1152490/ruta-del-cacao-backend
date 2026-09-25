from datetime import date

from django.test import TestCase

from apps.producers.listing import list_producers
from apps.producers.models import Producer


class ProducerListingTests(TestCase):
    def setUp(self):
        Producer.objects.create(
            member_code="PROD-000002",
            document_type="CC",
            identity_document="2",
            first_name="Ana",
            last_name="Zuluaga",
            municipality_code="54001",
            joined_on=date.today(),
        )
        Producer.objects.create(
            member_code="PROD-000001",
            document_type="CC",
            identity_document="1",
            first_name="Bea",
            last_name="Alvarez",
            municipality_code="54003",
            joined_on=date.today(),
        )
        Producer.objects.create(
            member_code="PROD-000003",
            document_type="CC",
            identity_document="3",
            first_name="Carlos",
            last_name="Alvarez",
            municipality_code="54001",
            joined_on=date.today(),
            status="inactive",
        )

    def test_filters_and_orders_results(self):
        result = list_producers({"municipality_code": "54001", "page": 1, "page_size": 20})

        self.assertEqual(result["count"], 2)
        self.assertEqual(
            [producer.member_code for producer in result["results"]],
            ["PROD-000003", "PROD-000002"],
        )

    def test_searches_by_member_code(self):
        result = list_producers({"search": "000001", "page": 1, "page_size": 20})

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["results"][0].identity_document, "1")

    def test_paginates_results(self):
        result = list_producers({"page": 2, "page_size": 1})

        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0].member_code, "PROD-000003")
