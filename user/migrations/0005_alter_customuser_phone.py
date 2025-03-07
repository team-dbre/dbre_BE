# Generated by Django 5.1.6 on 2025-02-05 20:27

import django.core.validators

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0004_customuser_img_url"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customuser",
            name="phone",
            field=models.CharField(
                max_length=13,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="전화번호는 '010-1234-5678' 형식으로 입력해주세요.",
                        regex="^01([0|1|6|7|8|9]?)-?([0-9]{3,4})-?([0-9]{4})$",
                    )
                ],
            ),
        ),
    ]
