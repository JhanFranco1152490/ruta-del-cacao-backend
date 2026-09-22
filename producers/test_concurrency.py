from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase

from producers.operations import DuplicateDocumentError, create_producer


class ProducerConcurrencyTests(TransactionTestCase):
    def producer_data(self, identity_document):
        return {
            "document_type": "CC",
            "identity_document": identity_document,
            "first_name": "Ana",
            "last_name": "Gomez",
            "municipality_code": "54001",
            "joined_on": date.today(),
        }

    def test_concurrent_creations_receive_distinct_member_codes(self):
        barrier = Barrier(2)

        def create(identity_document):
            close_old_connections()
            try:
                barrier.wait()
                return create_producer(self.producer_data(identity_document)).member_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            codes = list(executor.map(create, ["100", "200"]))

        self.assertEqual(len(set(codes)), 2)
        self.assertRegex(codes[0], r"^PROD-\d{6}$")
        self.assertRegex(codes[1], r"^PROD-\d{6}$")

    def test_concurrent_creations_reject_a_duplicate_document(self):
        barrier = Barrier(2)

        def create_duplicate():
            close_old_connections()
            try:
                barrier.wait()
                try:
                    create_producer(self.producer_data("300"))
                    return "created"
                except DuplicateDocumentError:
                    return "duplicate"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: create_duplicate(), range(2)))

        self.assertEqual(outcomes.count("created"), 1)
        self.assertEqual(outcomes.count("duplicate"), 1)
