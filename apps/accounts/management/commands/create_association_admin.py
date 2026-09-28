from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.exceptions import (
    AdministratorAlreadyExists,
    DuplicateAccountDocument,
    DuplicateEmail,
)
from apps.accounts.users.services import create_first_administrator
from apps.common.choices import DocumentType


def _format_validation_error(error: DjangoValidationError) -> str:
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {', '.join(messages)}" for field, messages in error.message_dict.items()
        )
    return "; ".join(error.messages)


class Command(BaseCommand):
    help = "Crea la cuenta Administrador inicial de la asociación y le envía la activación."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--document-type", required=True, choices=DocumentType.values)
        parser.add_argument("--identity-document", required=True)
        parser.add_argument("--first-name", required=True)
        parser.add_argument("--last-name", required=True)

    def handle(self, *args, **options):
        data = {
            "email": options["email"],
            "document_type": options["document_type"],
            "identity_document": options["identity_document"],
            "first_name": options["first_name"],
            "last_name": options["last_name"],
        }
        try:
            user = create_first_administrator(data)
        except (AdministratorAlreadyExists, DuplicateEmail, DuplicateAccountDocument) as error:
            raise CommandError(error.default_detail) from error
        except DjangoValidationError as error:
            raise CommandError(_format_validation_error(error)) from error

        self.stdout.write(self.style.SUCCESS(f"Cuenta Administrador creada: {user.email}"))
