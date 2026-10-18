import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.db import transaction

from apps.common.models import StoredFile
from apps.common.storage import DatabaseStorage
from config import settings as project_settings

pytestmark = pytest.mark.django_db

PHOTO = b"\xff\xd8\xff\xe0" + b"foto de prueba" * 100


@pytest.fixture
def storage():
    return DatabaseStorage()


def test_the_project_stores_files_in_the_database():
    assert project_settings.STORAGES["default"]["BACKEND"] == "apps.common.storage.DatabaseStorage"


def test_a_saved_file_is_read_back_with_the_same_content(storage):
    name = storage.save("evidence/foto.jpg", ContentFile(PHOTO))

    assert name == "evidence/foto.jpg"
    with storage.open(name) as stored:
        assert stored.read() == PHOTO


def test_the_size_and_content_type_are_kept(storage):
    name = storage.save(
        "evidence/foto.png", SimpleUploadedFile("foto.png", PHOTO, content_type="image/png")
    )

    row = StoredFile.objects.get(name=name)
    assert row.size == len(PHOTO)
    assert row.content_type == "image/png"
    assert storage.size(name) == len(PHOTO)


def test_without_a_declared_type_it_is_guessed_from_the_name(storage):
    name = storage.save("evidence/foto.jpg", ContentFile(PHOTO))

    assert StoredFile.objects.get(name=name).content_type == "image/jpeg"


def test_a_repeated_name_gets_another_name_and_keeps_the_first_file(storage):
    first = storage.save("evidence/foto.jpg", ContentFile(PHOTO))
    second = storage.save("evidence/foto.jpg", ContentFile(b"otra"))

    assert second != first
    with storage.open(first) as stored:
        assert stored.read() == PHOTO
    with storage.open(second) as stored:
        assert stored.read() == b"otra"


def test_exists_and_delete(storage):
    name = storage.save("evidence/foto.jpg", ContentFile(PHOTO))
    assert storage.exists(name)

    storage.delete(name)

    assert not storage.exists(name)
    assert not StoredFile.objects.filter(name=name).exists()


def test_deleting_a_missing_file_does_nothing(storage):
    storage.delete("evidence/no-existe.jpg")


def test_a_missing_file_cannot_be_opened_or_measured(storage):
    with pytest.raises(FileNotFoundError):
        storage.open("evidence/no-existe.jpg")
    with pytest.raises(FileNotFoundError):
        storage.size("evidence/no-existe.jpg")


def test_files_have_no_public_url(storage):
    name = storage.save("evidence/foto.jpg", ContentFile(PHOTO))

    with pytest.raises(NotImplementedError):
        storage.url(name)


def test_a_rolled_back_transaction_leaves_no_file(storage):
    with pytest.raises(RuntimeError), transaction.atomic():
        storage.save("evidence/foto.jpg", ContentFile(PHOTO))
        raise RuntimeError("falla después de guardar")

    assert not storage.exists("evidence/foto.jpg")


def test_the_tests_keep_files_in_memory():
    from django.core.files.storage import InMemoryStorage, default_storage

    default_storage.save("prueba.txt", ContentFile(b"x"))

    assert isinstance(default_storage._wrapped, InMemoryStorage)
    assert not StoredFile.objects.exists()


def test_a_big_upload_kept_in_a_temporary_file_is_saved_whole(storage):
    # Django deja en un archivo temporal las subidas de más de 2,5 MB.
    content = PHOTO + b"x" * (3 * 1024 * 1024)
    uploaded = TemporaryUploadedFile("grande.jpg", "image/jpeg", len(content), None)
    uploaded.write(content)
    uploaded.seek(0)

    name = storage.save("evidence/grande.jpg", uploaded)
    uploaded.close()

    with storage.open(name) as stored:
        assert stored.read() == content
    assert storage.size(name) == len(content)
