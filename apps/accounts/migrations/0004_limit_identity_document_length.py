from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_add_nit_document_type")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="identity_document",
            field=models.CharField(max_length=15),
        ),
    ]
