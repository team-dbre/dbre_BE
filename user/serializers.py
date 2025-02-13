from datetime import datetime, timedelta
from typing import Dict, Optional, Union

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from subscription.models import Subs

from .models import CustomUser
from .utils import normalize_phone_number


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    terms_agreement = serializers.BooleanField(write_only=True)
    privacy_agreement = serializers.BooleanField(write_only=True)
    marketing_agreement = serializers.BooleanField(
        write_only=True, required=False, default=False
    )

    class Meta:
        model = CustomUser
        fields = (
            "email",
            "password",
            "name",
            "phone",
            "terms_agreement",
            "privacy_agreement",
            "marketing_agreement",
        )

    def validate(self, data: dict) -> dict:
        if not data.get("terms_agreement") or not data.get("privacy_agreement"):
            raise serializers.ValidationError("필수 약관에 동의해야 합니다.")
        return data

    def validate_email(self, value: str) -> str:
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("이미 가입된 이메일입니다.")
        return value

    def validate_phone(self, value: str) -> str:
        if CustomUser.objects.filter(phone=value).exists():
            raise serializers.ValidationError("이미 가입된 전화번호입니다.")
        return value


class EmailCheckSerializer(serializers.Serializer):
    email = serializers.EmailField()


class LoginSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(
        required=True, help_text="로그인에 사용할 이메일 (예: user@example.com)"
    )
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
        help_text="로그인 비밀번호",
    )

    def validate(self, attrs: dict[str, str]) -> dict[str, str]:
        data = super().validate(attrs)
        assert self.user is not None

        return {
            "message": "로그인이 완료되었습니다.",
            "access_token": data["access"],
            "refresh_token": data["refresh"],
            "user_id": str(self.user.id),
        }


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=True)


class AuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField()


class GoogleLoginRequestSerializer(serializers.Serializer):
    code = serializers.CharField(required=True, help_text="구글 인증 코드")


class TokenResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    phone = serializers.BooleanField()
    user_id = serializers.CharField()


class GoogleCallbackResponseSerializer(serializers.Serializer):
    code = serializers.CharField(help_text="구글 인증 코드")


class PhoneVerificationRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20, help_text="전화번호 (예: 010-1234-5678 또는 +82 1012345678)"
    )

    def validate_phone(self, value: str) -> str:
        try:
            normalized = normalize_phone_number(value)
            if not normalized.startswith("010-"):
                raise serializers.ValidationError("올바른 휴대폰 번호 형식이 아닙니다.")
            return normalized
        except Exception:
            raise serializers.ValidationError("올바른 휴대폰 번호 형식이 아닙니다.")


class PhoneVerificationConfirmSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20, help_text="전화번호 (예: 010-1234-5678 또는 +82 1012345678)"
    )
    code = serializers.CharField(max_length=6, min_length=6, help_text="6자리 인증번호")

    def validate_phone(self, value: str) -> str:
        try:
            normalized = normalize_phone_number(value)
            if not normalized.startswith("010-"):
                raise serializers.ValidationError("올바른 휴대폰 번호 형식이 아닙니다.")
            return normalized
        except Exception:
            raise serializers.ValidationError("올바른 휴대폰 번호 형식이 아닙니다.")


class PhoneNumberSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class UserProfileSerializer(serializers.ModelSerializer):
    subscription_info = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "name",
            "phone",
            "img_url",
            "sub_status",
            "subscription_info",
        ]

    def get_subscription_info(
        self, obj: CustomUser
    ) -> Optional[Dict[str, Optional[Union[datetime, int]]]]:
        if obj.sub_status in ["active", "paused"]:
            try:
                subscription = Subs.objects.filter(user=obj).first()
                if subscription:
                    # UTC to KST (+9 hours)
                    end_date = (
                        subscription.end_date + timedelta(hours=9)
                        if subscription.end_date
                        else None
                    )
                    return {
                        "end_date": end_date,
                        "remaining_days": (
                            subscription.remaining_bill_date.days
                            if subscription.remaining_bill_date
                            else None
                        ),
                    }
            except Subs.DoesNotExist:
                return None
        return None


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()
