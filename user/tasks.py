from datetime import timedelta

from django.utils import timezone

from .models import CustomUser


def delete_inactive_users() -> None:
    one_year_ago = timezone.now() - timedelta(days=365)
    users_to_delete = CustomUser.objects.filter(
        deleted_at__lte=one_year_ago, is_active=False, is_deletion_confirmed=True
    )
    deleted_count = users_to_delete.count()
    users_to_delete.delete()
    print(f"{deleted_count} users were deleted.")
