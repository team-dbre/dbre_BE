import logging
import uuid

from typing import Any, Dict

from rest_framework import serializers

from payment.models import BillingKey
from plan.models import Plans
from user.models import CustomUser


logger = logging.getLogger(__name__)


class BillingKeySerializer(serializers.ModelSerializer):
    """Billing Key 저장을 위한 시리얼라이저"""

    user_id = serializers.UUIDField(write_only=True)
    billing_key = serializers.CharField()

    class Meta:
        model = BillingKey
        fields = ["user_id", "billing_key"]

    def validate_user_id(self, value: uuid.UUID) -> uuid.UUID:
        """유효한 사용자 ID인지 검증"""
        if not CustomUser.objects.filter(id=value).exists():
            raise serializers.ValidationError("User not found")
        return value

    def create(self, validated_data: Dict[str, Any]) -> BillingKey:
        """Billing Key 저장 로직"""
        user = CustomUser.objects.get(id=validated_data["user_id"])
        billing_key, _ = BillingKey.objects.update_or_create(
            user=user, defaults={"billing_key": validated_data["billing_key"]}
        )
        return billing_key


class SubscriptionPaymentSerializer(serializers.Serializer):
    """정기 결제 요청을 위한 데이터 검증"""

    user_id = serializers.UUIDField()
    plan_id = serializers.IntegerField()
    billing_key = serializers.CharField()

    def validate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """사용자 및 요금제 검증"""

        # 사용자 확인
        try:
            user = CustomUser.objects.get(id=data["user_id"])
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"user_id": "User not found"})

        # 플랜 확인
        try:
            plan = Plans.objects.get(id=data["plan_id"])
        except Plans.DoesNotExist:
            raise serializers.ValidationError({"plan_id": "Plan not found"})

        # Billing Key 확인
        try:
            billing_key_obj = BillingKey.objects.get(user=user)
            if billing_key_obj.billing_key != data["billing_key"]:
                raise serializers.ValidationError(
                    {"billing_key": "Invalid billing key"}
                )
        except BillingKey.DoesNotExist:
            raise serializers.ValidationError({"billing_key": "Billing Key not found"})

        data["user"] = user
        data["plan"] = plan
        return data


class GetBillingKeySerializer(serializers.ModelSerializer):
    """Get Billing Key 직렬화 시리얼라이저"""

    user_id = serializers.UUIDField(source="user.id", read_only=True)
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
