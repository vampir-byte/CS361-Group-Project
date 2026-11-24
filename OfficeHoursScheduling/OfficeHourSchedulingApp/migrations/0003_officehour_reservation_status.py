from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("OfficeHourSchedulingApp", "0002_role_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="officehour",
            name="status",
            field=models.CharField(
                choices=[("scheduled", "Scheduled"), ("canceled", "Canceled")],
                default="scheduled",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="reservation",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("canceled", "Canceled")],
                default="active",
                max_length=10,
            ),
        ),
    ]
