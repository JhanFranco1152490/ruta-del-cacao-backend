from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("producers", "0001_initial")]

    operations = [
        migrations.RunSQL(
            sql=(
                "CREATE SEQUENCE producers_member_code_sequence "
                "START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999"
            ),
            reverse_sql="DROP SEQUENCE producers_member_code_sequence",
        ),
    ]
