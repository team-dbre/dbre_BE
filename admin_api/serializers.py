from datetime import timedelta
from typing import Union

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from payment.models import Pays
from payment.services.payment_service import RefundService
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
            self.user = User.objects.get(email=attrs["email"])

            # staff 권한 체크
            if not self.user.is_staff:
                raise serializers.ValidationError("관리자 권한이 없습니다.")

            # is_active 체크
            if not self.user.is_active:
                raise serializers.ValidationError("비활성화된 계정입니다.")

            # 비밀번호 검증
            if not self.user.check_password(attrs["password"]):
                raise serializers.ValidationError("비밀번호를 다시 확인해주세요.")

        except ObjectDoesNotExist:
            raise serializers.ValidationError("존재하지 않는 관리자 계정입니다.")

        data = super().validate(attrs)

        return {
            "message": "관리자 로그인이 완료되었습니다.",
            "access_token": data["access"],
            "refresh_token": data["refresh"],
            "is_superuser": self.user.is_superuser,
        }


class SubsCancelSerializer(TokenObtainPairSerializer):
    user_name = serializers.CharField(source="user.name", read_only=True)
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    cancelled_date = serializers.SerializerMethodField()
    cancelled_reason = serializers.SerializerMethodField()
    refund_date = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    refund_amount = serializers.SerializerMethodField()
    expected_refund_amount = serializers.SerializerMethodField()

    class Meta:
        model = SubHistories
        fields = [
            "user_name",
            "user_email",
            "user_phone",
            "cancelled_date",
            "cancelled_reason",
            "refund_date",
            "refund_amount",
            "get_expected_refund_amount",
        ]

    def get_cancelled_date(self, obj: SubHistories) -> str | None:
        """구독 취소 일자(환불 일자랑 다름)"""
        cancelled_data = SubHistories.objects.filter(
            sub=obj.sub, status="refund_pending"
        ).latest("change_date")

        return (
            cancelled_data.change_date.strftime("%Y-%m-%d") if cancelled_data else None
        )

    def get_cancelled_reason(self, obj: SubHistories) -> str | None:
        """취소 사유"""

        reason = obj.cancelled_reason if obj.cancelled_reason else "UnKnown"
        return (
            f"기타 사유: {obj.other_reason}"
            if reason == "other" and obj.other_reason
            else reason
        )

    def get_refund_date(self, obj: SubHistories) -> str | None:
        """환불 일자"""
        if obj.status == "refund_pending":
            return None

        refund = Pays.objects.filter(subs=obj.sub, status="REFUNDED").latest(
            "refund_at"
        )
        return refund.paid_at.strftime("%Y-%m-%d") if refund else None

    def get_refund_status(self, obj: SubHistories) -> str | None:
        """sub_status 상태"""
        if obj.status in ["cancelled", "refund_pending"]:
            return obj.status
        return None

    def get_refund_amount(self, obj: SubHistories) -> str | None:
        """환불 금액"""
        if obj.status == "refund_pending":
            return "0"

        refund = Pays.objects.filter(subs=obj.sub, status="REFUNDED").latest(
            "refund_at"
        )
        return str(refund.refund_amount) if refund else "0"

    def get_expected_refund_amount(self, obj: SubHistories) -> str:
        """환불 예정 금액"""
        subscription = obj.sub
        payment = (
            Pays.objects.filter(user=subscription.user, subs=subscription)
            .order_by("-id")
            .first()
        )

        if not payment:
            return "0"

        refund_service = RefundService(
            user=subscription.user,
            subscription=subscription,
            cancel_reason="환불 예정 금액 계산",
            other_reason="",
        )

        refund_amount = refund_service.calculate_refund_amount(payment)

        return str(refund_amount)


class AdminRefundSerializer(serializers.Serializer):
    """관리자가 환불 승인 요청 시 직접 입력한 환불 금액을 검증"""

    subscription_id = serializers.IntegerField(help_text="환불할 구독 ID")
    refund_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, help_text="관리자가 입력한 환불 금액"
    )

    def validate_subscription_id(self, value: int) -> int:
        """구독 ID 검증 (사용자의 sub_status가 refund_pending인지 확인)"""
        try:
            subscription = Subs.objects.get(id=value)
            if subscription.user.sub_status != "refund_pending":
                raise serializers.ValidationError(
                    "해당 구독의 사용자가 환불 대기 상태가 아닙니다."
                )
        except Subs.DoesNotExist:
            raise serializers.ValidationError("해당 구독이 존재하지 않습니다.")
        return value

    def validate_refund_amount(self, data: dict) -> dict:
        """ " 환불 금액이 결제 금액 초과하지 않도로 검증"""
        subscription_id = data["subscription_id"]
        refund_amount = data["refund_amount"]

        try:
            subscription = Subs.objects.get(id=subscription_id)
        except Subs.DoesNotExist:
            raise serializers.ValidationError(
                {"subscription_id": "해당 구독이 존재하지 않습니다."}
            )

        payment = (
            Pays.objects.filter(subs=subscription, status="PAID")
            .order_by("-paid_at")
            .first()
        )

        if not payment:
            raise serializers.ValidationError(
                {"refund_amount": "결제 내역이 없습니다. 환불할 수 없습니다."}
            )

        total_paid_amount = payment.amount

        if total_paid_amount < refund_amount:
            raise serializers.ValidationError(
                {
                    "refund_amount": f"환불 금액은 결제 금액({total_paid_amount})을 초과할 수 없습니다."
                }
            )
        return data
