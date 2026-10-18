from rest_framework import serializers


class PersonSerializer(serializers.Serializer):
    # Una cuenta por su id y su nombre, nunca su documento. Sin nombre, por su correo, como en los
    # historiales: es la única forma de reconocerla.
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return account.get_full_name() or account.email
