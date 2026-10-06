class ReadOnlyAdminMixin:
    # Registros que solo escribe el sistema (eventos, historiales, catálogos sembrados): el admin
    # los consulta pero no los crea, edita ni elimina.

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
