from rest_framework import serializers

from plan.models import Plans


class PlanSerializer(serializers.ModelSerializer):
    """플랜 시리얼라이저"""

    class Meta:
        model = Plans
        fields = ["id", "plan_name", "price", "period", "is_active"]
        read_only_fields = ["id"]

    def validate_price(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError("가격은 0보다 커야 합니다.")
        return float(value)
