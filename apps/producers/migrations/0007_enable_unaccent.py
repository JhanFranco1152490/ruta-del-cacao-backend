from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("producers", "0006_alter_producer_identity_document_and_more"),
    ]

    operations = [UnaccentExtension()]
