"""Lo común a los archivos que se suben: qué son por su contenido, cuánto dicen pesar antes de
leerlos y con qué nombre se muestran."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileFormat:
    """Un formato admitido: los primeros bytes que lo delatan, su tipo y la extensión con que se
    guarda."""

    signature: bytes
    content_type: str
    extension: str


JPEG = FileFormat(b"\xff\xd8\xff", "image/jpeg", "jpg")
PNG = FileFormat(b"\x89PNG\r\n\x1a\n", "image/png", "png")
PDF = FileFormat(b"%PDF-", "application/pdf", "pdf")


def detect_format(uploaded, formats) -> FileFormat | None:
    """El formato de `formats` que dicen los primeros bytes, o `None`. El nombre y el tipo que
    envía el cliente no se creen: un `.docx` renombrado a `.pdf` no pasa."""
    uploaded.seek(0)
    head = uploaded.read(max(len(file_format.signature) for file_format in formats))
    uploaded.seek(0)
    return next(
        (file_format for file_format in formats if head.startswith(file_format.signature)), None
    )


def declared_length(request) -> int:
    """Lo que el cliente dice que pesa el cuerpo. Se mira antes de leerlo: un cuerpo enorme no
    debe llegar a escribirse en el disco del servidor."""
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return 0


def clean_file_name(name: str | None, *, max_length: int, fallback: str) -> str:
    """El nombre con que se muestra un archivo, sin la carpeta del dispositivo: algunos
    navegadores envían la ruta completa, con barras invertidas."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return base[:max_length] or fallback
