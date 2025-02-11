from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

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
        return {
            "message": "로그인이 완료되었습니다.",
            "access_token": data["access"],
            "refresh_token": data["refresh"],
        }


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=True)


# GET 요청용 시리얼라이저 (응답 스키마)
class AuthUrlResponseSerializer(serializers.Serializer):
    auth_url = serializers.URLField()


# POST 요청용 시리얼라이저
class TokenResponseSerializer(serializers.Serializer):
    message = serializers.CharField()
    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    phone = serializers.BooleanField()


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
