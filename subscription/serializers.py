from rest_framework import serializers

from .models import SubHistories, Subs


class SubsSerializer(serializers.ModelSerializer):
    sub_status = serializers.SerializerMethodField()
    remaining_days = serializers.SerializerMethodField()

    class Meta:
        model = Subs
        fields = "__all__"

    def get_sub_status(self, obj: Subs) -> str:
        return obj.user.sub_status

    def get_remaining_days(self, obj: Subs) -> int:
        return obj.remaining_days


class SubHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubHistories
        fields = "__all__"
