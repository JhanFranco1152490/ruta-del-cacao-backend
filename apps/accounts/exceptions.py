from rest_framework import status

from apps.common.exceptions import ApiError


class InvalidResetToken(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "El enlace no es válido o ya venció. Solicita uno nuevo."
    default_code = "invalid_reset_token"


class SessionExpired(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "La sesión venció. Inicia sesión de nuevo."
    default_code = "authentication_failed"


class InvalidCredentials(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Usuario o contraseña incorrectos."
    default_code = "invalid_credentials"


class AccountInactive(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "La cuenta está inactiva."
    default_code = "account_inactive"


class AccountLocked(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "La cuenta está bloqueada temporalmente. Intenta de nuevo en 15 minutos."
    default_code = "account_locked"


class ExceedsOwnPermissions(ApiError):
    """Conceder, asignar o administrar más de lo que se tiene (nadie da lo que no tiene).

    `field` marca `permission_codes` o `role_ids` cuando el rechazo viene del cuerpo de la
    petición (conceder o asignar); al administrar una cuenta o un rol ya existente, el objeto
    lo identifica la URL y no hay campo que marcar.
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No puedes conceder, asignar ni administrar más de lo que tienes."
    default_code = "exceeds_own_permissions"

    def __init__(self, field=None):
        super().__init__(fields={field: [self.default_detail]} if field else {})


class SelfModification(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "No puedes modificar tu propia cuenta desde aquí."
    default_code = "self_modification"


class RoleImmutable(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Este rol es del sistema: no se puede editar ni borrar."
    default_code = "role_immutable"


class LastAdministrator(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Debe quedar al menos un administrador activo."
    default_code = "last_administrator"


class RoleNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El rol no existe."
    default_code = "not_found"


class DuplicateRoleName(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe un rol con ese nombre."
    default_code = "duplicate_role_name"

    def __init__(self):
        super().__init__(fields={"name": [self.default_detail]})


class RoleInUse(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El rol tiene cuentas asignadas: no se puede borrar."
    default_code = "role_in_use"


class AccountNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La cuenta no existe."
    default_code = "not_found"


class DuplicateEmail(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El correo ya está registrado."
    default_code = "duplicate_email"

    def __init__(self):
        super().__init__(fields={"email": [self.default_detail]})


class DuplicateAccountDocument(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El documento ya está registrado en otra cuenta."
    default_code = "duplicate_document"

    def __init__(self):
        super().__init__(fields={"identity_document": [self.default_detail]})


class ProducerInactive(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El productor está inactivo."
    default_code = "producer_inactive"


class ProducerAlreadyLinked(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El productor ya tiene una cuenta vinculada."
    default_code = "producer_already_linked"


class NotActivationPending(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La cuenta ya está activada."
    default_code = "not_activation_pending"


class AssociationAccessNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Esta cuenta no tiene un productor asociado."
    default_code = "not_found"
