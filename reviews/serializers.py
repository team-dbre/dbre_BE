from typing import Any, Dict

from rest_framework import serializers

from reviews.models import Review
from subscription.models import Subs


class ReviewSerializer(serializers.ModelSerializer):

    class Meta:
        model = Review
        fields = ["id", "user", "subs", "rating", "content", "created_at"]
        read_only_fields = ["id", "user", "subs", "created_at"]

    def validate_rating(self, value: int) -> int:
        # 별점 유효성 검사
        if value < 0 or value > 5:
            raise serializers.ValidationError("별점은 1~5 사이여야 합니다")
        return value

    def validate(self, data: str) -> str:
        user = self.context["request"].user
        if user.sub_status != "active":
            raise serializers.ValidationError(
                "구독이 활성화된 사용자만 리뷰 작성이 가능합니다"
            )
        return data

    def create(self, validated_data: Dict[str, Any]) -> Review:
        request = self.context.get("request")
        validated_data["user"] = request.user

        subs = Subs.objects.filter(user=request.user).first()
        validated_data["subs"] = subs

        review: Review = Review.objects.create(**validated_data)
        return review
