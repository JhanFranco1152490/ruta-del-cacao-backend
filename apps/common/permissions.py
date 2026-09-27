from rest_framework.permissions import BasePermission


class ActionPermission(BasePermission):
    """Exige el permiso que la vista declara para la acción en curso.

    La vista define `action_permissions = {"list": "app.codename", ...}`. Un método sin
    acción (DELETE en una vista que no lo implementa) se deja pasar para que DRF responda
    405 y no 403.
    """

    def has_permission(self, request, view):
        if view.action is None:
            return True
        required = view.action_permissions.get(view.action)
        return required is not None and request.user.has_perm(required)


class HasPermission(BasePermission):
    """Exige un permiso fijo (`view.required_permission`), para una vista sin `view.action`
    (un `APIView` simple, no un `ViewSet`).
    """

    def has_permission(self, request, view):
        return request.user.has_perm(view.required_permission)
