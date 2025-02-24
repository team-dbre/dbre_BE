from typing import Any, Dict

from rest_framework import serializers

from tally.models import Tally


class TallyWebhookSerializer(serializers.Serializer):
    """Tally 웹훅 데이터 직렬화"""

    form_id = serializers.CharField()
    form_name = serializers.CharField()
    response_id = serializers.CharField()
    submitted_at = serializers.DateTimeField()
    form_data = serializers.JSONField()

    def create(self, validated_data: Dict[str, Any]) -> Tally:
        """웹훅 데이터를 데이터베이스에 저장"""
        return Tally.objects.create(**validated_data)
