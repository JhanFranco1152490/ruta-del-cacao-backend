from cryptography.hazmat.primitives import serialization
from django.core.management.base import BaseCommand
from py_vapid import Vapid02, b64urlencode


class Command(BaseCommand):
    help = (
        "Genera el par de llaves de las notificaciones push y las imprime listas para las "
        "variables de entorno. Se hace una sola vez: si cambian, cada dispositivo tiene que "
        "volver a activar los avisos."
    )

    def handle(self, *args, **options):
        vapid = Vapid02()
        vapid.generate_keys()
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
        private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64urlencode(public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64urlencode(private)}")
