from rest_framework import serializers

from user.models import CustomUser


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
