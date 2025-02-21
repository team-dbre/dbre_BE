# Generated by Django 5.1.6 on 2025-02-20 09:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscription", "0005_remove_subs_cancelled_reason_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subhistories",
            name="status",
            field=models.CharField(
                choices=[
                    ("renewal", "갱신"),
                    ("cancel", "취소"),
                    ("pause", "정지"),
                    ("restart", "재개"),
                    ("refund_pending", "환불 대기"),
                ],
                max_length=20,
            ),
        ),
    ]
