from django.db import migrations, models
import django.db.models.functions.text


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("CC", "Cédula de ciudadanía"),
                    ("CE", "Cédula de extranjería"),
                    ("PPT", "Permiso por Protección Temporal"),
                ],
                default="CC",
                max_length=3,
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="identity_document",
            field=models.CharField(max_length=50),
        ),
        migrations.RemoveConstraint(
            model_name="user",
            name="accounts_user_email_ci_unique",
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                models.functions.text.Lower("email"),
                name="accounts_user_email_ci_unique",
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                fields=("document_type", "identity_document"),
                name="accounts_user_document_type_number_unique",
            ),
        ),
    ]
