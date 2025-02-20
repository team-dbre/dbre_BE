import logging
import uuid

from datetime import timedelta
from typing import Any, Dict

from django.utils.timezone import now
from rest_framework import serializers

from payment.models import BillingKey
from payment.utils import cancel_scheduled_payments, create_scheduled_payment
from plan.models import Plans
from subscription.models import Subs
from user.models import CustomUser


logger = logging.getLogger(__name__)


class BillingKeySerializer(serializers.ModelSerializer):
    """Billing Key 저장을 위한 시리얼라이저"""

    billing_key = serializers.CharField()

    class Meta:
        model = BillingKey
        fields = ["billing_key"]

    def validate_user_id(self, value: uuid.UUID) -> uuid.UUID:
        """유효한 사용자 ID인지 검증"""
        if not CustomUser.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")
        return value

    def create(self, validated_data: Dict[str, Any]) -> BillingKey:
        """Billing Key 저장 로직"""
        user = self.context["request"].user
        billing_key, _ = BillingKey.objects.update_or_create(
            user=user,
            defaults={
                "billing_key": validated_data["billing_key"],
            },
        )
        return billing_key


class BillingKeyDeleteSerializer(serializers.ModelSerializer):
    """Billing Key 변경을 위한 시리얼라이저"""

    # billing_key = serializers.CharField()

    class Meta:
        model = BillingKey
        fields = ["billing_key"]

    def validate_user_id(self, value: uuid.UUID) -> uuid.UUID:
        """유효한 사용자 ID인지 검증"""
        if not BillingKey.objects.filter(user_id=value).exists():
            raise serializers.ValidationError(
                "User not found or no billing key assigned"
            )
        return value


class SubscriptionPaymentSerializer(serializers.Serializer):
    """정기 결제 요청을 위한 데이터 검증"""

    plan_id = serializers.IntegerField()

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """사용자 및 요금제 검증"""
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError({"user": "User authentication required"})

        user = request.user

        # 사용자의 빌링키 자동 조회
        try:
            billing_key_obj = BillingKey.objects.get(user=user)
            billing_key = billing_key_obj.billing_key
        except BillingKey.DoesNotExist:
            raise serializers.ValidationError({"billing_key": "Billing Key not found"})

        # 플랜 확인
        try:
            plan = Plans.objects.get(id=data["plan_id"])
        except Plans.DoesNotExist:
            raise serializers.ValidationError({"plan_id": "Plan not found"})

        # # Billing Key 확인
        # try:
        #     billing_key_obj = BillingKey.objects.get(user=user)
        #     if billing_key_obj.billing_key != data["billing_key"]:
        #         raise serializers.ValidationError(
        #             {"billing_key": "Invalid billing key"}
        #         )
        # except BillingKey.DoesNotExist:
        #     raise serializers.ValidationError({"billing_key": "Billing Key not found"})

        data["user"] = user
        data["plan"] = plan
        data["billing_key"] = billing_key
        return data


class GetBillingKeySerializer(serializers.ModelSerializer):
    """Get Billing Key 직렬화 시리얼라이저"""

    billing_key = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = BillingKey
        fields = ["user_id", "billing_key", "created_at"]


class WebhookSerializer(serializers.Serializer):
    """포트원 Webhook 데이터 검증"""

    imp_uid = serializers.CharField(required=True)
    status = serializers.ChoiceField(
        choices=["paid", "failed", "cancelled"], required=True
    )
    merchant_uid = serializers.CharField(required=True)


class RefundSerializer(serializers.Serializer):
    """환불 요청 데이터 검증"""

    plan_id = serializers.IntegerField()
    cancelled_reason = serializers.ListSerializer(
        child=serializers.ChoiceField(choices=Subs.cancelled_reason_choices),
        required=True,
    )
    other_reason = serializers.CharField(
        required=False, allow_blank=True, max_length=255
    )

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """사용자 및 구독 정보 검증"""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"user_id": "로그인이 필요합니다."})
        plan_id = data.get("plan_id")

        # 사용자의 구독 정보 조회
        subscription = Subs.objects.filter(user_id=user, plan_id=plan_id).first()
        if not subscription:
            raise serializers.ValidationError(
                {"user_id": "사용자의 구독 정보가 없습니다."}
            )

        # 구독이 이미 취소된 경우
        if not subscription.auto_renew:
            raise serializers.ValidationError(
                {"subscription": "이미 취소된 구독입니다."}
            )

        if "other" in data.get("cancelled_reason", []) and not data.get("other_reason"):
            raise serializers.ValidationError(
                {"other_reason": "기타 사유를 입력해주세요"}
            )

        data["subscription"] = subscription
        return data


class RefundResponseSerializer(serializers.Serializer):
    """환불 성공/실패 응답 처리"""

    message = serializers.CharField(default="")
    refund_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False
    )
    error = serializers.CharField(required=False)


class PauseSubscriptionSerializer(serializers.ModelSerializer):
    """구독 중지 요청 시리얼라이저"""

    plan_id = serializers.IntegerField(
        required=True, help_text="구독 플랜 ID를 입력하세요."
    )
    sub_status = serializers.CharField(source="user.sub_status", read_only=True)

    class Meta:
        model = Subs
        fields = ["user", "sub_status", "remaining_bill_date", "end_date", "plan_id"]
        read_only_fields = ["user", "sub_status", "remaining_bill_date", "end_date"]

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """구독 상태 active인지 확인"""
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or user.sub_status != "active":
            raise serializers.ValidationError(
                {"error": "구독중인 사용자만 중지할 수 있습니다."}
            )

        return data

    # def update(self, instance: Subs, validated_data: Dict[str, Any]) -> Subs:
    #     """구독 중지 처리"""
    #     plan = instance.plan
    #     plan_id = validated_data.get("plan_id")
    #
    #     if instance.user.sub_status != "active":
    #         raise serializers.ValidationError("활성화된 구독만 중지할 수 있습니다.")
    #
    #     if plan_id and plan_id != plan.id:
    #         raise serializers.ValidationError(
    #             "해당 유저의 플랜과 입력된 플랜이 일치하지 않습니다."
    #         )
    #
    #     # 남은 기간 저장
    #     if instance.end_date:
    #         remaining_days = (instance.end_date - now()).days
    #         instance.remaining_bill_date = timedelta(
    #             days=max(remaining_days, 0)
    #         )  # 음수 방지
    #     else:
    #         instance.remaining_bill_date = timedelta(days=0)
    #
    #     # 구독 상태 변경
    #     instance.end_date = None  # 중지 시 만료일 초기화
    #     instance.user.sub_status = "paused"
    #     instance.auto_renew = False  # 자동 갱신 비활성화
    #     instance.user.save(update_fields=["sub_status"])
    #     instance.save(update_fields=["end_date", "auto_renew", "remaining_bill_date"])
    #
    #     # 포트원 예약 결제 취소
    #     try:
    #         if instance.billing_key is None:
    #             raise serializers.ValidationError("Billing Key가 존재하지 않습니다.")
    #         billing_key = instance.billing_key.billing_key
    #         plan_id = instance.plan.id
    #         cancel_scheduled_payments(billing_key, plan_id)
    #     except AttributeError:
    #         logger.warning(f"유저 {instance.user.id}의 빌링키가 없음")
    #
    #     return instance


class ResumeSubscriptionSerializer(serializers.ModelSerializer):
    """구독 재개 요청 시리얼라이저"""

    plan_id = serializers.IntegerField(
        required=True, help_text="구독 플랜 ID를 입력하세요."
    )
    sub_status = serializers.CharField(source="user.sub_status", read_only=True)

    class Meta:
        model = Subs
        fields = [
            "user",
            "sub_status",
            "remaining_bill_date",
            "start_date",
            "end_date",
            "plan_id",
        ]
        read_only_fields = [
            "user",
            "sub_status",
            "remaining_bill_date",
            "start_date",
            "end_date",
        ]

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """구독 상태 paused인지 확인"""
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or user.sub_status != "paused":
            raise serializers.ValidationError(
                {"error": "구독이 정지된 사용자만 재개할 수 있습니다."}
            )

        return data

    # def update(self, instance: Subs, validated_data: Dict[str, Any]) -> Subs:
    #     """구독 재개 처리"""
    #     plan_id = validated_data.get("plan_id")
    #
    #     if instance.user.sub_status != "paused":
    #         raise serializers.ValidationError(
    #             "구독이 중지된 상태에서만 재개할 수 있습니다."
    #         )
    #
    #     if plan_id and plan_id != instance.plan.id:
    #         raise serializers.ValidationError(
    #             "해당 유저의 플랜과 입력된 플랜이 일치하지 않습니다."
    #         )
    #
    #     # 구독 재개일을 새로운 구독 시작일로 설정
    #     new_start_date = now()
    #
    #     # 저장된 남은 기간을 사용하여 `end_date` 연장
    #     if instance.remaining_bill_date:
    #         remaining_days = instance.remaining_bill_date.days
    #     else:
    #         remaining_days = 0  # 예외 처리: 남은 기간이 없을 경우
    #
    #     if remaining_days <= 0:
    #         raise serializers.ValidationError(
    #             "남은 구독 기간이 없습니다. 새로 구독해야 합니다."
    #         )
    #
    #     new_end_date = new_start_date + timedelta(days=remaining_days)
    #
    #     instance.start_date = new_start_date
    #     instance.end_date = new_end_date
    #     instance.user.sub_status = "active"
    #     instance.auto_renew = True  # 자동 갱신 다시 활성화
    #     instance.user.save(update_fields=["sub_status"])
    #     instance.save(
    #         update_fields=[
    #             "start_date",
    #             "end_date",
    #             "auto_renew",
    #             "remaining_bill_date",
    #         ]
    #     )
    #
    #     # 포트원 예약 결제 다시 설정
    #     try:
    #         if instance.billing_key is None:
    #             raise serializers.ValidationError("Billing Key가 존재하지 않습니다.")
    #         billing_key = instance.billing_key.billing_key
    #         if not isinstance(plan_id, int):
    #             raise serializers.ValidationError("plan_id는 정수형이어야 합니다.")
    #         plan_price = instance.plan.price
    #         create_scheduled_payment(billing_key, plan_id, plan_price, instance.user)
    #     except AttributeError:
    #         logger.warning(f"유저 {instance.user.id}의 빌링키가 없음")
    #
    #     return instance
