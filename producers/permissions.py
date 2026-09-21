from rest_framework.permissions import BasePermission


class ProducerPermission(BasePermission):
    permission = ""

    def has_permission(self, request, view):
        return bool(request.user and request.user.has_perm(self.permission))


class CanViewProducers(ProducerPermission):
    permission = "producers.view"


class CanCreateProducers(ProducerPermission):
    permission = "producers.create"


class CanUpdateProducers(ProducerPermission):
    permission = "producers.update"


class CanChangeProducerStatus(ProducerPermission):
    permission = "producers.change_status"
