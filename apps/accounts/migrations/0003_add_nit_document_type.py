from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_document_type")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("CC", "Cédula de ciudadanía"),
                    ("CE", "Cédula de extranjería"),
                    ("PPT", "Permiso por Protección Temporal"),
                    ("NIT", "Número de Identificación Tributaria"),
                ],
                max_length=3,
            ),
        ),
    ]
