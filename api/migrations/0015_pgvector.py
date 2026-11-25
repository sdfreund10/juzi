from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0014_category_owner"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector",
        ),
    ]
