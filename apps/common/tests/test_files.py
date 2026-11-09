import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.common.files import JPEG, PDF, PNG, clean_file_name, declared_length, detect_format

JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"x" * 20
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * 20
PDF_BYTES = b"%PDF-1.7\n" + b"x" * 20


def uploaded(content, name="archivo"):
    return SimpleUploadedFile(name, content)


@pytest.mark.parametrize(
    "content, expected",
    [(JPEG_BYTES, JPEG), (PNG_BYTES, PNG), (PDF_BYTES, PDF)],
)
def test_the_format_comes_from_the_first_bytes(content, expected):
    assert detect_format(uploaded(content), (JPEG, PNG, PDF)) == expected


def test_a_format_outside_the_accepted_ones_is_none():
    assert detect_format(uploaded(PDF_BYTES), (JPEG, PNG)) is None


def test_the_name_does_not_decide_the_format():
    assert detect_format(uploaded(b"PK\x03\x04docx", name="factura.pdf"), (PDF,)) is None


def test_detecting_leaves_the_file_at_its_start():
    file = uploaded(PDF_BYTES)

    detect_format(file, (PDF,))

    assert file.read() == PDF_BYTES


def test_each_format_knows_its_type_and_extension():
    assert (PDF.content_type, PDF.extension) == ("application/pdf", "pdf")
    assert (JPEG.content_type, PNG.extension) == ("image/jpeg", "png")


@pytest.mark.parametrize("header, expected", [("2048", 2048), ("", 0), ("no-es-un-numero", 0)])
def test_the_declared_length_is_read_from_the_header(header, expected):
    request = RequestFactory().post("/", CONTENT_LENGTH=header)
    request.META["CONTENT_LENGTH"] = header

    assert declared_length(request) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("factura.pdf", "factura.pdf"),
        ("C:\\Users\\Ana\\Documentos\\factura.pdf", "factura.pdf"),
        ("/storage/emulated/0/factura.pdf", "factura.pdf"),
        ("  ", "documento"),
        (None, "documento"),
        ("x" * 30, "x" * 20),
    ],
)
def test_the_file_name_keeps_only_its_last_part(name, expected):
    assert clean_file_name(name, max_length=20, fallback="documento") == expected
