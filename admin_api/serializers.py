from rest_framework import serializers

from subscription.models import SubHistories, Subs
from user.models import CustomUser


class AdminUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ["email", "name", "password", "phone"]

    def create(self, validated_data: dict[str, str]) -> CustomUser:
        password = validated_data.pop("password")
        user = CustomUser.objects.create(**validated_data)
        user.set_password(password)
        user.is_staff = True
        user.save()
        return user


class SubscriptionSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    user_status = serializers.CharField(source="user.sub_status", read_only=True)
    plan_name = serializers.CharField(source="plan.plan_name", read_only=True)
    first_payment_date = serializers.SerializerMethodField()
    last_payment_date = serializers.SerializerMethodField()
    expiry_date = serializers.SerializerMethodField()

    class Meta:
        model = Subs
        fields = [
            "id",
            "user_name",
            "user_email",
            "user_phone",
            "plan_name",
            "user_status",
            "first_payment_date",
            "last_payment_date",
            "expiry_date",
            "auto_renew",
        ]

    def get_first_payment_date(self, obj: Subs) -> str | None:
        """
        최초 결제일 (subhistory에서 첫 구독 날짜 가져오기)
        """
        history = SubHistories.objects.filter(sub=obj).order_by("change_date").first()
        return history.change_date.strftime("%Y-%m-%d") if history else None

    def get_last_payment_date(self, obj: Subs) -> str | None:
        """
        최근 결제일
        """
        return obj.start_date.strftime("%Y-%m-%d") if obj.start_date else None

    def get_expiry_date(self, obj: Subs) -> str | None:
        """
        구독 만료일
        """
        return obj.end_date.strftime("%Y-%m-%d") if obj.end_date else None


class SubscriptionHistorySerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    plan_name = serializers.CharField(source="plan.plan_name", read_only=True)

    class Meta:
        model = SubHistories
        fields = ["id", "user_name", "plan_name", "status", "change_date"]


class SubsCancelledSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    cancelled_date = serializers.SerializerMethodField()
    refund_date = serializers.SerializerMethodField()
    refund_amount = serializers.SerializerMethodField()

    class Meta:
        model = Subs
        fields = [
            "user_name",
            "user_email",
            "user_phone",
            "cancelled_date",
            "refund_date",
            "refund_amount",
        ]

    # def get_cancelled_date(self, obj):
    #     re
