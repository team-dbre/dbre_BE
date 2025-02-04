from rest_framework import serializers

from .models import SubHistories, Subs


class SubsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subs
        fields = "__all__"


class SubHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubHistories
        fields = "__all__"
