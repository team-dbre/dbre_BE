from typing import Any, Dict

from rest_framework import serializers

from tally.models import Tally


class TallyWebhookSerializer(serializers.Serializer):
    class Meta:
        model = Tally
        fields = "__all__"
