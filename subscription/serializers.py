from rest_framework import serializers

from .models import SubHistories, Subs


class SubsSerializer(serializers.ModelSerializer):
    sub_status = serializers.SerializerMethodField()

    class Meta:
        model = Subs
        fields = "__all__"

    def get_sub_status(self, obj):
        return obj.user.sub_status


class SubHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubHistories
        fields = "__all__"
