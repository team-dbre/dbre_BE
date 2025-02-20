from typing import Union

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

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


class DashboardSerializer(serializers.Serializer):
    total_subscriptions = serializers.IntegerField(help_text="전체 구독")
    new_subscriptions_today = serializers.IntegerField(help_text="신규 구독")
    paused_subscriptions = serializers.IntegerField(help_text="오늘 구독 일시정지")


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


class AdminLoginSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(
        required=True, help_text="관리자 이메일 (예: admin@example.com)"
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        help_text="관리자 비밀번호",
    )

    class Meta:
        fields = ("email", "password")

    def validate(self, attrs: dict[str, str]) -> dict[str, Union[str, bool]]:  # type: ignore
        User = get_user_model()
        try:
            user = User.objects.get(email=attrs["email"])

            # staff 권한 체크
            if not user.is_staff:
                raise serializers.ValidationError("관리자 권한이 없습니다.")

            # is_active 체크
            if not user.is_active:
                raise serializers.ValidationError("비활성화된 계정입니다.")

            # 비밀번호 검증
            if not user.check_password(attrs["password"]):
                raise serializers.ValidationError("비밀번호를 다시 확인해주세요.")

        except ObjectDoesNotExist:
            raise serializers.ValidationError("존재하지 않는 관리자 계정입니다.")

        data = super().validate(attrs)

        return {
            "message": "관리자 로그인이 완료되었습니다.",
            "access_token": data["access"],
            "refresh_token": data["refresh"],
            "is_superuser": user.is_superuser,
        }
