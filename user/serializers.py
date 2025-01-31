from rest_framework import serializers
from .models import CustomUser, Agreements

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    terms_agreement = serializers.BooleanField(write_only=True)
    privacy_agreement = serializers.BooleanField(write_only=True)
    marketing_agreement = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'name', 'phone',
                 'terms_agreement', 'privacy_agreement', 'marketing_agreement')

    def validate(self, data):
        if not data.get('terms_agreement') or not data.get('privacy_agreement'):
            raise serializers.ValidationError("필수 약관에 동의해야 합니다.")
        return data
