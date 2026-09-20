from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, identity_document, password, **extra_fields):
        if not email:
            raise ValueError("El correo electrónico es obligatorio.")
        if not identity_document:
            raise ValueError("El documento de identidad es obligatorio.")

        email = self.normalize_email(email).lower()
        identity_document = identity_document.strip()
        user = self.model(
            email=email,
            identity_document=identity_document,
            **extra_fields,
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, identity_document, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, identity_document, password, **extra_fields)

    def create_superuser(self, email, identity_document, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Un superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Un superusuario debe tener is_superuser=True.")

        return self._create_user(email, identity_document, password, **extra_fields)
