import datetime
import decimal

from typing import Optional, Union

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from admin_api.models import AdminLoginLog
from payment.models import Pays
from payment.services.payment_service import RefundService
from subscription.models import SubHistories, Subs
from tally.models import Tally
from user.models import CustomUser


class UserInfoSerializer(serializers.ModelSerializer):
    """프론트 공통 컴포넌트를 위한 name, email, phone 분리"""

    class Meta:
        model = CustomUser
        fields = ("name", "email", "phone")


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
    # 작업 요청 현황
    new_request_today = serializers.IntegerField()
    request_incomplete = serializers.IntegerField()
    request_complete = serializers.IntegerField()
    # 온라인 미팅 현황
    # 구독 현황
    total_subscriptions = serializers.IntegerField(help_text="전체 구독")
    new_subscriptions_today = serializers.IntegerField(help_text="신규 구독")
    paused_subscriptions = serializers.IntegerField(help_text="오늘 구독 일시정지")
    # 구독 취소 현황
    subs_cancel_all = serializers.IntegerField()
    subs_cancel_today = serializers.IntegerField()
    # 리뷰 현황
    all_reviews = serializers.IntegerField()
    new_reviews = serializers.IntegerField()
    # 고객 현황
    total_customers = serializers.IntegerField(help_text="전체 고객 수")
    new_customers_today = serializers.IntegerField(help_text="오늘 가입한 고객 수")
    deleted_customers_today = serializers.IntegerField(
        help_text="오늘 탈퇴 요청한 고객 수"
    )
    # 매출 현황
    monthly_sales = serializers.IntegerField()
    monthly_refunds = serializers.IntegerField()
    monthly_total_sales = serializers.IntegerField()


class UserSubscriptionSerializer(serializers.ModelSerializer):
    """사용자 정보 직렬화"""

    class Meta:
        model = CustomUser
        fields = ["name", "email", "phone", "sub_status"]


class SubscriptionSerializer(serializers.ModelSerializer):
    user = UserSubscriptionSerializer(read_only=True)
    plan_name = serializers.CharField(source="plan.plan_name", read_only=True)
    first_payment_date = serializers.SerializerMethodField()
    last_payment_date = serializers.SerializerMethodField()
    expiry_date = serializers.SerializerMethodField()

    class Meta:
        model = Subs
        fields = [
            "id",
            "user",
            "plan_name",
            "first_payment_date",
            "last_payment_date",
            "expiry_date",
            "auto_renew",
        ]

    def get_first_payment_date(self, obj: Subs) -> str | None:
        """최초 결제일 (subhistory에서 첫 구독 날짜 가져오기)"""
        history = SubHistories.objects.filter(sub=obj).order_by("change_date").first()
        return history.change_date.strftime("%Y-%m-%d") if history else None

    def get_last_payment_date(self, obj: Subs) -> str | None:
        """최근 결제일"""
        return obj.start_date.strftime("%Y-%m-%d") if obj.start_date else None

    def get_expiry_date(self, obj: Subs) -> str | None:
        """구독 만료일"""
        return obj.end_date.strftime("%Y-%m-%d") if obj.end_date else None


class SubscriptionHistorySerializer(serializers.ModelSerializer):

    change_date = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = SubHistories
        fields = ["change_date", "status", "amount"]

    def get_change_date(self, obj: SubHistories) -> str:
        """YYYY-MM-DD 형식으로 변환"""
        return obj.change_date.strftime("%Y-%m-%d")

    def get_status(self, obj: SubHistories) -> str:
        """변경 상태를 한글로 변환"""
        status_mapping = {
            "renewal": "결제",
            "cancel": "구독 취소",
            "pause": "일시 정지",
            "restart": "재개",
            "refund_pending": "환불 대기",
        }
        return status_mapping.get(obj.status, "기타")

    def get_amount(self, obj: SubHistories) -> str:
        """해당 변경 상태에 따라 결제 금액 반환"""
        payment = Pays.objects.filter(subs=obj.sub).order_by("-paid_at").first()
        refund = (
            Pays.objects.filter(subs=obj.sub, status="REFUNDED")
            .order_by("-refund_at")
            .first()
        )

        if obj.status == "renewal" and payment:
            return f"{int(payment.amount):,}원"
        elif obj.status == "cancel" and refund:
            return f"-{int(refund.refund_amount):,}원"  # type: ignore
        return "-"


# class SubsCancelledSerializer(serializers.ModelSerializer):
#     user_name = serializers.CharField(source="user.name", read_only=True)
#     user_email = serializers.CharField(source="user.email", read_only=True)
#     user_phone = serializers.CharField(source="user.phone", read_only=True)
#     cancelled_date = serializers.SerializerMethodField()
#     refund_date = serializers.SerializerMethodField()
#     refund_amount = serializers.SerializerMethodField()
#
#     class Meta:
#         model = Subs
#         fields = [
#             "user_name",
#             "user_email",
#             "user_phone",
#             "cancelled_date",
#             "refund_date",
#             "refund_amount",
#         ]

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
    user = serializers.SerializerMethodField()
    subs_id = serializers.SerializerMethodField()
    cancelled_date = serializers.SerializerMethodField()
    cancelled_reason = serializers.SerializerMethodField()
    refund_date = serializers.SerializerMethodField()
    refund_status = serializers.SerializerMethodField()
    refund_amount = serializers.SerializerMethodField()
    expected_refund_amount = serializers.SerializerMethodField()

    class Meta:
        model = SubHistories
        fields = [
            "user",
            "subs_id",
            "cancelled_date",
            "cancelled_reason",
            "refund_date",
            "refund_amount",
            "get_expected_refund_amount",
        ]

    def get_user(self, obj: SubHistories) -> dict:
        if obj.user:
            return {
                "name": obj.user.name,
                "email": obj.user.email,
                "phone": obj.user.phone,
            }
        return {"name": None, "email": None, "phone": None}

    def get_subs_id(self, obj: SubHistories) -> Optional[int]:
        return obj.sub.id if obj.sub else None

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
        cancel = (
            SubHistories.objects.filter(sub=obj.sub, status="refund_pending")
            .order_by("-change_date")
            .first()
        )
        if not cancel:
            return "UnKnown"

        reason = cancel.cancelled_reason
        if isinstance(reason, str):
            reason = reason.strip("[]'")  # Remove brackets and quotes if present
        elif isinstance(reason, list):
            reason = reason[0] if reason else "UnKnown"

        if reason.lower() == "other" and cancel.other_reason:  # type: ignore
            return f"기타 : {cancel.other_reason}"
        return reason or "UnKnown"

    def get_refund_date(self, obj: SubHistories) -> str | None:
        """환불 일자"""
        if obj.status == "refund_pending":
            return None

        refund = Pays.objects.filter(subs=obj.sub, status="REFUNDED").latest(
            "refund_at"
        )
        return refund.refund_at.strftime("%Y-%m-%d") if refund.refund_at else None

    def get_refund_status(self, obj: SubHistories) -> str | None:
        """sub_status 상태"""
        if obj.status in ["cancel", "refund_pending"]:
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
        if not subscription:
            return "None"
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

    def validate_refund_amount(self, refund_amount: decimal.Decimal) -> decimal.Decimal:
        """환불 금액이 결제 금액을 초과하지 않도록 검증"""
        subscription_id = self.initial_data.get("subscription_id")

        if not subscription_id:
            raise serializers.ValidationError(
                {"subscription_id": "구독 ID가 필요합니다."}
            )

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

        total_paid_amount = payment.amount  # 사용자가 결제한 금액

        if refund_amount > total_paid_amount:
            raise serializers.ValidationError(
                {
                    "refund_amount": f"환불 금액은 결제 금액({total_paid_amount})을 초과할 수 없습니다."
                }
            )

        return refund_amount


class AdminCancelReasonSerializer(serializers.Serializer):
    cancelled_reason = serializers.CharField()
    count = serializers.IntegerField()


class AdminTallySerializer(serializers.Serializer):

    user = serializers.SerializerMethodField()
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    form_name = serializers.CharField(read_only=True)
    form_data = serializers.JSONField(read_only=True)
    complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tally
        fields = [
            "submitted_at",
            "user",
            "complete",
            "form_name",
            "form_data",
        ]

    def get_user(self, obj: Tally) -> dict:
        """사용자 정보를 객체로 반환"""
        if obj.user:
            return {
                "name": obj.user.name,
                "email": obj.user.email,
                "phone": obj.user.phone,
            }
        return {"name": None, "email": None, "phone": None}


class AdminTallyCompleteSerializer(serializers.Serializer):
    tally_id = serializers.IntegerField()


class AdminSalesSerializer(serializers.ModelSerializer):
    """결제 및 환불 내역 직렬화"""

    transaction_date = serializers.SerializerMethodField()
    transaction_amount = serializers.SerializerMethodField()
    transaction_type = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()

    class Meta:
        model = Pays
        fields = [
            "id",
            "transaction_date",
            "transaction_amount",
            "transaction_type",
            "user",
        ]

    def get_transaction_date(self, obj: Pays) -> datetime.date:
        return (
            obj.refund_at.date()  # type: ignore
            if self.context.get("is_refund")
            else obj.paid_at.date()
        )

    def get_transaction_amount(self, obj: Pays) -> str:
        if self.context.get("is_refund"):  # 환불 내역일 경우
            return f"-{int(obj.refund_amount):,} 원"  # type: ignore
        return f"{int(obj.amount):,} 원"  # 결제 내역일 경우

    def get_transaction_type(self, obj: Pays) -> str:
        if self.context.get("is_refund"):
            return "구독취소"  # 환불이 있는 경우에만 "구독취소"
        return "결제"  # 결제 내역은 항상 "결제"로 표시

    def get_user(self, obj: Pays) -> dict:
        if obj.user:
            return {
                "id": obj.user.id,
                "name": obj.user.name,
                "email": obj.user.email,
                "phone": obj.user.phone,
            }
        return {"id": None, "name": None, "email": None, "phone": None}


class AdminPasswordChangeSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value: str) -> str:
        # 추가적인 비밀번호 강도 검증
        if len(value) < 10:
            raise serializers.ValidationError("비밀번호는 최소 10자 이상이어야 합니다.")
        if not any(char.isdigit() for char in value):
            raise serializers.ValidationError(
                "비밀번호는 최소 1개의 숫자를 포함해야 합니다."
            )
        if not any(char.isupper() for char in value):
            raise serializers.ValidationError(
                "비밀번호는 최소 1개의 대문자를 포함해야 합니다."
            )
        if not any(char.islower() for char in value):
            raise serializers.ValidationError(
                "비밀번호는 최소 1개의 소문자를 포함해야 합니다."
            )
        if not any(char in '!@#$%^&*(),.?":{}|<>' for char in value):
            raise serializers.ValidationError(
                "비밀번호는 최소 1개의 특수문자를 포함해야 합니다."
            )

        return value

    def validate_user_id(self, value: str) -> str:
        try:
            user = CustomUser.objects.get(id=value, is_staff=True)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError(
                "해당 ID의 관리자 계정이 존재하지 않습니다."
            )
        return value


class StatisticsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    new_users_today = serializers.IntegerField()
    deleted_users_today = serializers.IntegerField()


class UserManagementSerializer(serializers.ModelSerializer):
    user = UserInfoSerializer(source="*")
    is_subscribed = serializers.CharField()
    marketing_consent = serializers.CharField()
    start_date = serializers.DateTimeField()
    end_date = serializers.DateTimeField()
    latest_paid_at = serializers.DateTimeField()

    class Meta:
        model = CustomUser
        fields = (
            "id",
            "user",
            "is_subscribed",
            "sub_status",
            "created_at",
            "last_login",
            "marketing_consent",
            "start_date",
            "latest_paid_at",
            "end_date",
        )


class UserManagementResponseSerializer(serializers.Serializer):
    # count = serializers.IntegerField()
    # next = serializers.URLField(allow_null=True)
    # previous = serializers.URLField(allow_null=True)
    statistics = StatisticsSerializer()
    users = UserManagementSerializer(many=True)


class AdminRefundInfoSerializer(serializers.Serializer):
    """환불 승인 전 결제 정보 직렬화"""

    user_name = serializers.CharField(source="user.name")
    paid_at = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    refund_amount = serializers.SerializerMethodField()

    def get_paid_at(self, obj: Subs) -> str:
        """결제 일자"""
        payment = (
            Pays.objects.filter(user=obj.user, subs=obj, status="PAID")
            .order_by("-paid_at")
            .first()
        )
        return payment.paid_at.strftime("%Y/%m/%d %H:%M:%S") if payment else "정보 없음"

    def get_paid_amount(self, obj: Subs) -> str:
        """결제 금액"""
        payment = (
            Pays.objects.filter(user=obj.user, subs=obj, status="PAID")
            .order_by("-paid_at")
            .first()
        )
        return f"{int(payment.amount):,} 원" if payment else "0 원"

    def get_refund_amount(self, obj: Subs) -> str:
        """환불 예정 금액"""
        payment = (
            Pays.objects.filter(user=obj.user, subs=obj, status="PAID")
            .order_by("-paid_at")
            .first()
        )
        if not payment:
            return "0 원"

        refund_service = RefundService(
            user=obj.user,
            subscription=obj,
            cancel_reason="환불 예정 금액 계산",
            other_reason="",
        )
        refund_amount = refund_service.calculate_refund_amount(payment)
        return f"{int(refund_amount):,} 원" if refund_amount else "0 원"


class DeletedUserSerializer(serializers.ModelSerializer):
    user = UserInfoSerializer(source="*")
    reason = serializers.CharField()
    is_deletion_confirmed = serializers.BooleanField()

    class Meta:
        model = CustomUser
        fields = ("id", "deleted_at", "user", "reason", "is_deletion_confirmed")


class AdminUserListSerializer(serializers.ModelSerializer):
    user = UserInfoSerializer(source="*")
    classification = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "classification", "user", "created_at"]

    @extend_schema_field(serializers.CharField())
    def get_classification(self, obj: CustomUser) -> str:
        return "Master" if obj.is_superuser else "Admin"


# 요청을 위한 시리얼라이저
class ConfirmUserDeletionRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)


# 응답을 위한 시리얼라이저
class ConfirmUserDeletionResponseSerializer(serializers.Serializer):
    message = serializers.CharField()


# 에러 응답을 위한 시리얼라이저
class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


class UserRecoveryRequestSerializer(serializers.Serializer):
    user_id = serializers.CharField(required=True)


class UserRecoveryResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ["id", "name", "email", "is_deletion_confirmed", "deleted_at"]
        read_only_fields = [
            "id",
            "name",
            "email",
            "is_deletion_confirmed",
            "deleted_at",
        ]


class AdminLoginLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminLoginLog
        fields = "__all__"
