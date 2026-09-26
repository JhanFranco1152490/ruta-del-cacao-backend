from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.db import connection
from django.utils import timezone

from apps.producers.exceptions import DuplicateDocument, StaleVersion
from apps.producers.services import create_producer, update_producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db(transaction=True)


def producer_data(identity_document):
    return {
        "document_type": "CC",
        "identity_document": identity_document,
        "first_name": "Ana",
        "last_name": "Gomez",
        "municipality_code": "54001",
        "joined_on": timezone.localdate(),
    }


def run_in_parallel(action, arguments):
    barrier = Barrier(len(arguments))

    def run(argument):
        try:
            barrier.wait()
            return action(argument)
        finally:
            # Con conexiones persistentes close_old_connections() no cierra la de un hilo
            # y la base de pruebas no se puede destruir con una sesión abierta.
            connection.close()

    with ThreadPoolExecutor(max_workers=len(arguments)) as executor:
        return list(executor.map(run, arguments))


def test_concurrent_creations_receive_distinct_member_codes():
    codes = run_in_parallel(
        lambda document: create_producer(producer_data(document)).member_code,
        ["100000", "200000"],
    )

    assert len(set(codes)) == 2


def test_concurrent_duplicates_create_only_one_record():
    def create(_):
        try:
            create_producer(producer_data("300000"))
            return "created"
        except DuplicateDocument:
            return "duplicate"

    outcomes = run_in_parallel(create, [0, 1])

    assert sorted(outcomes) == ["created", "duplicate"]


def test_concurrent_edits_with_the_same_version_apply_only_once():
    producer = ProducerFactory(first_name="Ana")

    def edit(first_name):
        try:
            update_producer(producer.id, 1, {"first_name": first_name})
            return "updated"
        except StaleVersion:
            return "stale"

    outcomes = run_in_parallel(edit, ["Beatriz", "Carolina"])

    assert sorted(outcomes) == ["stale", "updated"]
    producer.refresh_from_db()
    assert producer.version == 2
    assert producer.first_name in {"Beatriz", "Carolina"}
