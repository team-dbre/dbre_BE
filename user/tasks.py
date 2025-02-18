from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

@shared_task
def send_reset_password_email(email, user_data, temp_password):
    subject = "[DeSub] 임시 비밀번호가 발급되었습니다"
    html_message = render_to_string(
        "password_reset_email.html",
        {"user": user_data, "temp_password": temp_password},
    )

    send_mail(
        subject=subject,
        message="",
        from_email=settings.EMAIL_HOST_USER,
        recipient_list=[email],
        html_message=html_message,
        fail_silently=False,
    )