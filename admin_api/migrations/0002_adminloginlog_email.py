# Generated by Django 5.1.6 on 2025-02-24 19:22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="adminloginlog",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
    ]
