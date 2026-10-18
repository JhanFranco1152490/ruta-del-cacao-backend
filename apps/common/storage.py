import mimetypes

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

from .models import StoredFile

DEFAULT_CONTENT_TYPE = "application/octet-stream"


@deconstructible
class DatabaseStorage(Storage):
    """Almacenamiento de Django que guarda cada archivo en una fila de `StoredFile`.

    El disco del servidor no sirve para las fotos: se borra en cada despliegue y no se comparte
    entre varios servidores. Como escribe en la base, guardar un archivo dentro de una transacción
    se revierte con ella: un registro que falla no deja su archivo huérfano.
    """

    def _save(self, name, content):
        if hasattr(content, "seek"):
            content.seek(0)
        data = b"".join(content.chunks())
        StoredFile.objects.create(
            name=name,
            content=data,
            content_type=_content_type(name, content),
            size=len(data),
        )
        return name

    def _open(self, name, mode="rb"):
        content = StoredFile.objects.filter(name=name).values_list("content", flat=True).first()
        if content is None:
            raise FileNotFoundError(name)
        return ContentFile(bytes(content), name=name)

    def delete(self, name):
        StoredFile.objects.filter(name=name).delete()

    def exists(self, name):
        return StoredFile.objects.filter(name=name).exists()

    def size(self, name):
        size = StoredFile.objects.filter(name=name).values_list("size", flat=True).first()
        if size is None:
            raise FileNotFoundError(name)
        return size

    def url(self, name):
        # Los archivos nunca se sirven por una dirección pública: se entregan por una vista que
        # revisa antes que quien los pide alcance el registro al que pertenecen.
        raise NotImplementedError("Los archivos guardados en la base no tienen URL pública.")


def _content_type(name, content) -> str:
    declared = getattr(content, "content_type", None)
    if declared:
        return declared
    guessed, _ = mimetypes.guess_type(name)
    return guessed or DEFAULT_CONTENT_TYPE
