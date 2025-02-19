import logging
import uuid

from datetime import timedelta
from typing import Any, cast
from urllib.parse import urlencode

import boto3

from botocore.exceptions import ClientError
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import get_random_string
from django_redis import get_redis_connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import serializers, status
from rest_framework.generics import CreateAPIView, GenericAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from term.models import Terms
from user.models import Agreements, CustomUser
from user.serializers import (
    AuthUrlResponseSerializer,
    EmailCheckSerializer,
    GoogleCallbackResponseSerializer,
    GoogleLoginRequestSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordChangeResponseSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetResponseSerializer,
    PhoneCheckRequestSerializer,
    PhoneCheckResponseSerializer,
    PhoneNumberSerializer,
    PhoneVerificationConfirmSerializer,
    PhoneVerificationRequestSerializer,
    RefreshTokenSerializer,
    TokenResponseSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    UserUpdateResponseSerializer,
    UserUpdateSerializer,
)
from user.utils import (
    format_phone_for_twilio,
    get_google_access_token,
    get_google_user_info,
    normalize_phone_number,
)


logger = logging.getLogger(__name__)


@extend_schema_view(
    post=extend_schema(
        tags=["user"],
        summary="회원가입",
        description="Register a new user with terms agreements.",
        request=UserRegistrationSerializer,
        responses={201: UserRegistrationSerializer},
    )
)
class UserRegistrationView(CreateAPIView):
    serializer_class = UserRegistrationSerializer

    def create(
        self, request: UserRegistrationSerializer, *args: Any, **kwargs: Any
    ) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Cache에서 전화번호 인증 여부 확인
        phone_verified = cache.get(
            f'phone_verified:{serializer.validated_data["phone"]}'
        )

        if not phone_verified:
            return Response(
                {"error": "전화번호 인증이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = CustomUser.objects.create_user(
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
            name=serializer.validated_data["name"],
            phone=serializer.validated_data["phone"],
        )

        # 최신 약관 정보 가져오기
        latest_terms = Terms.objects.latest("created_at")

        # 하나의 약관 동의 레코드 생성
        Agreements.objects.create(
            user=user,
            terms_url=f"/terms/{latest_terms.id}",
            agreed_at=timezone.now(),
            marketing=serializer.validated_data.get("marketing_agreement", False),
        )

        return Response(
            {
                "message": "회원가입이 완료되었습니다.",
                "email": user.email,
                "name": user.name,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema_view(
    post=extend_schema(
        tags=["user"],
        summary="Email 사용 가능 여부(회원가입)",
        description="기존에 존재하는 이메일인지 확인하여 사용가능 여부를 반환합니다.",
        request=EmailCheckSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "available": {"type": "boolean"},
                    "message": {"type": "string"},
                },
            }
        },
    )
)
class EmailCheckView(GenericAPIView):
    serializer_class = EmailCheckSerializer

    def post(self, request: EmailCheckSerializer) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        exists = CustomUser.objects.filter(email=email).exists()

        if exists:
            return Response(
                {"available": False, "message": "이미 가입된 이메일입니다."},
                status=status.HTTP_200_OK,
            )

        return Response(
            {"available": True, "message": "가입 가능한 이메일입니다."},
            status=status.HTTP_200_OK,
        )


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer  # type: ignore

    @extend_schema(
        tags=["user"],
        summary="User Login",
        description="Login with email and password to get access and refresh tokens",
        request=LoginSerializer,
        examples=[
            OpenApiExample(
                "Login Example",
                value={"email": "user@example.com", "password": "string"},
                request_only=True,
            )
        ],
        responses={
            200: {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                },
            }
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            response = super().post(request, *args, **kwargs)

            if response.status_code == 200:
                # 토큰 정보 가져오기
                access_token = response.data.get("access_token")
                refresh_token = response.data.get("refresh_token")

                # Authorization 헤더 설정
                response["Authorization"] = f"Bearer {access_token}"

                # 시리얼라이저에서 사용자 정보 가져오기
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                user = serializer.user  # 인증된 사용자

                # 수동으로 user_logged_in 시그널 발생
                user_logged_in.send(sender=user.__class__, request=request, user=user)

                # Redis에 토큰 저장
                cache.set(
                    f"user_token:{user.id}",
                    {"access_token": access_token, "refresh_token": refresh_token},
                    timeout=cast(
                        timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
                    ).total_seconds(),
                )

            return response

        except serializers.ValidationError as e:

            error_message = e.detail

            if isinstance(error_message, dict) and "non_field_errors" in error_message:
                error_message = error_message["non_field_errors"][0]

            return Response(
                {"message": error_message}, status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(tags=["user"])
class LogoutView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request: Request) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            refresh_token = serializer.validated_data["refresh_token"]
            RefreshToken(refresh_token).blacklist()

            # Redis에서 토큰 삭제
            cache.delete(f"user_token:{request.user.id}")

            response = Response(
                {"message": "로그아웃이 완료되었습니다."}, status=status.HTTP_200_OK
            )
            response["Authorization"] = ""
            response.delete_cookie("refresh_token")

            return response
        except TokenError:
            return Response(
                {"message": "유효하지 않은 리프레쉬 토큰입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            return Response(
                {"message": "로그아웃에 실패했습니다.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GoogleLoginView(GenericAPIView):
    renderer_classes = [JSONRenderer]

    @staticmethod
    def get_redirect_uri(environment: str) -> str | None:
        redirects = {
            "backend_local": settings.GOOGLE_REDIRECT_URI,
            "frontend_local": settings.FLOCAL_GOOGLE_REDIRECT_URI,
            "frontend_prod": settings.FPROD_GOOGLE_REDIRECT_URI,
        }
        return redirects.get(environment, redirects["backend_local"])

    @extend_schema(
        tags=["user"],
        parameters=[
            OpenApiParameter(
                name="env",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="환경 설정 (backend_local, frontend_local, frontend_prod)",
                required=False,
                default="backend_local",
            )
        ],
        responses={200: AuthUrlResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        environment = request.query_params.get("env", "backend_local")

        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": self.get_redirect_uri(environment),
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }

        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return Response({"auth_url": auth_url})

    @extend_schema(
        tags=["user"],
        parameters=[
            OpenApiParameter(
                name="env",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="환경 설정 (backend_local, frontend_local, frontend_prod)",
                required=False,
                default="backend_local",
            )
        ],
        request=GoogleLoginRequestSerializer,
        responses={
            200: OpenApiResponse(
                response=TokenResponseSerializer, description="구글 로그인 처리"
            )
        },
    )
    def post(self, request: Request) -> Response:
        serializer = GoogleLoginRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data["code"]
        environment = request.query_params.get("env", "backend_local")
        redirect_uri = self.get_redirect_uri(environment)

        if redirect_uri is None:
            return Response(
                {"message": "잘못된 환경 설정입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not code:
            return Response(
                {"message": "인증 코드가 없습니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            access_token = get_google_access_token(code=code, redirect_uri=redirect_uri)
            if access_token is None:
                raise ValueError("Failed to get access token")

            user_info = get_google_user_info(access_token)

            try:
                user = CustomUser.objects.get(email=user_info["email"])

                # is_active 체크 추가
                if not user.is_active:
                    return Response(
                        {
                            "message": "비활성화된 계정입니다. 관리자나 고객센터에 문의해주세요."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if user.provider != "google":
                    return Response(
                        {
                            "message": "이미 일반 회원으로 가입된 이메일입니다. 일반 로그인을 이용해주세요."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except CustomUser.DoesNotExist:
                user = CustomUser.objects.create_user(
                    email=user_info["email"],
                    name=user_info.get("name", ""),
                    provider="google",
                    img_url=user_info.get("picture"),
                )

                latest_terms = Terms.objects.latest("created_at")
                Agreements.objects.create(
                    user=user,
                    terms_url=f"/terms/{latest_terms.id}",
                    agreed_at=timezone.now(),
                    marketing=False,
                )

            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)

            # 수동으로 user_logged_in 시그널 발생
            user_logged_in.send(sender=user.__class__, request=request, user=user)

            cache.set(
                f"user_token:{user.id}",
                {"access_token": access_token, "refresh_token": refresh_token},
                timeout=cast(
                    timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
                ).total_seconds(),
            )

            response = Response(
                {
                    "message": "구글 로그인이 완료되었습니다.",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "phone": bool(user.phone),
                },
                status=status.HTTP_200_OK,
            )

            # Authorization 헤더 설정
            response["Authorization"] = f"Bearer {access_token}"

            return response

        except Exception as e:
            return Response(
                {"message": "구글 로그인에 실패했습니다.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GoogleCallbackView(GenericAPIView):
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["user"],
        responses={
            200: OpenApiResponse(
                response=GoogleCallbackResponseSerializer,
                description="구글 인증 코드 반환",
            )
        },
    )
    def get(self, request: Request) -> Response:
        code = request.GET.get("code")
        if not code:
            return Response(
                {"message": "인증 코드가 없습니다."}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({"code": code})


class RequestVerificationView(APIView):
    serializer_class = PhoneVerificationRequestSerializer

    @extend_schema(
        tags=["user"],
        summary="전화번호 인증번호 요청",
        description="전화번호를 입력받아 인증번호를 SMS로 발송합니다.",
        request=PhoneVerificationRequestSerializer,
        responses={
            200: OpenApiResponse(
                description="인증번호 발송 성공",
                response={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            ),
            400: OpenApiResponse(
                description="잘못된 요청",
                response={
                    "type": "object",
                    "properties": {"error": {"type": "string"}},
                },
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            # 에러 메시지 형식 변경
            if (
                "phone" in serializer.errors
                and "올바른 휴대폰 번호 형식이 아닙니다."
                in str(serializer.errors["phone"])
            ):
                return Response(
                    {"error": "올바른 휴대폰 번호 형식이 아닙니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                "phone" in serializer.errors
                and "동일한 휴대폰번호로 가입된 계정이 있습니다."
                in str(serializer.errors["phone"])
            ):
                return Response(
                    {"error": "동일한 전화번호로 가입된 계정이 있습니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone = serializer.validated_data["phone"]
        formatted_phone = format_phone_for_twilio(phone)

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            client.verify.v2.services(
                settings.TWILIO_VERIFY_SERVICE_SID
            ).verifications.create(
                to=formatted_phone, channel="sms", locale="ko"  # 한국어 메시지 설정
            )

            return Response({"message": "인증번호가 발송되었습니다."})
        except TwilioRestException as e:
            print(f"Twilio Error: {str(e)}")
            error_message = "인증번호 발송에 실패했습니다. 잠시 후 다시 시도해주세요."
            if "60238" in str(e):  # Verify 서비스 블록 에러
                error_message = "Verify 서비스 블록 에러입니다. 관리자에게 문의해주세요"

            return Response(
                {"error": error_message}, status=status.HTTP_400_BAD_REQUEST
            )


class VerifyPhoneView(APIView):
    serializer_class = PhoneVerificationConfirmSerializer

    @extend_schema(
        tags=["user"],
        summary="전화번호 인증번호 확인",
        description="전화번호와 인증번호를 입력받아 인증을 진행합니다.",
        request=PhoneVerificationConfirmSerializer,
        responses={
            200: OpenApiResponse(
                description="인증 성공",
                response={
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                },
            ),
            400: OpenApiResponse(
                description="잘못된 요청",
                response={
                    "type": "object",
                    "properties": {"error": {"type": "string"}},
                },
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone = serializer.validated_data["phone"]
        code = serializer.validated_data["code"]
        formatted_phone = format_phone_for_twilio(phone)

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            verification_check = client.verify.v2.services(
                settings.TWILIO_VERIFY_SERVICE_SID
            ).verification_checks.create(to=formatted_phone, code=code)

            if verification_check.status == "approved":
                cache.set(f"phone_verified:{phone}", "true", timeout=300)
                return Response(
                    {"message": "인증이 완료되었습니다."}, status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {"error": "잘못된 인증번호입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except TwilioRestException as e:
            return Response(
                {"error": f"인증 실패: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST
            )


class SavePhoneNumberView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PhoneNumberSerializer

    @extend_schema(
        tags=["user"],
        summary="구글 소셜 로그인 유저 인증된 전화번호 저장",
        request=PhoneNumberSerializer,
        responses={200: TokenResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            phone = normalize_phone_number(serializer.validated_data["phone"])

            # 전화번호 중복 검사
            if CustomUser.objects.filter(phone=phone).exists():
                # 현재 사용자의 계정 삭제
                request.user.delete()

                # Redis에 저장된 토큰 삭제
                cache.delete(f"user_token:{request.user.id}")

                return Response(
                    {
                        "error": "이미 사용 중인 전화번호입니다. 새로 생성된 계정이 삭제되었습니다.",
                        "action": "account_deleted",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 인증된 전화번호인지 확인
            if not cache.get(f"phone_verified:{phone}"):
                return Response(
                    {"error": "인증되지 않은 전화번호입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # 사용자 전화번호 업데이트
            request.user.phone = phone
            request.user.save()

            return Response({"message": "전화번호가 저장되었습니다."})

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    get=extend_schema(
        tags=["user"],
        summary="내 정보 조회",
        description="로그인된 사용자의 프로필 정보를 조회합니다.",
        responses={
            200: OpenApiResponse(
                response=UserProfileSerializer, description="사용자 정보 조회 성공"
            ),
            401: OpenApiResponse(description="인증되지 않은 사용자"),
        },
    ),
    patch=extend_schema(
        tags=["user"],
        summary="사용자 정보 수정",
        description="사용자의 이름과 프로필 이미지를 수정합니다.",
        request=UserUpdateSerializer,
        responses={
            200: UserUpdateResponseSerializer,
            400: OpenApiResponse(description="잘못된 요청"),
            401: OpenApiResponse(description="인증 실패"),
        },
    ),
)
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def get(self, request: Request) -> Response:
        user = request.user
        serializer = UserProfileSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _is_ncp_image(self, img_url: str | None) -> bool:
        """이미지 URL이 NCP 버킷의 이미지인지 확인"""
        if not img_url:
            return False
        return settings.NCP_BUCKET_URL in img_url

    def _upload_to_ncp(self, image_file: UploadedFile, key_prefix: str) -> str:
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.NCP_ACCESS_KEY,
            aws_secret_access_key=settings.NCP_SECRET_KEY,
            endpoint_url=settings.NCP_ENDPOINT_URL,
        )

        if not image_file.name:
            raise serializers.ValidationError("파일 이름이 없습니다.")

        file_extension = image_file.name.split(".")[-1]
        key = f"{key_prefix}/{uuid.uuid4()}.{file_extension}"

        try:
            s3_client.upload_fileobj(
                image_file,
                settings.NCP_BUCKET_NAME,
                key,
                ExtraArgs={"ACL": "public-read"},
            )
            return f"{settings.NCP_BUCKET_URL}/{key}"
        except ClientError as e:
            logger.error(f"NCP upload error: {str(e)}")
            raise serializers.ValidationError("이미지 업로드에 실패했습니다.")

    def _delete_from_ncp(self, img_url: str | None) -> None:
        if not img_url:
            return

        try:
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.NCP_ACCESS_KEY,
                aws_secret_access_key=settings.NCP_SECRET_KEY,
                endpoint_url=settings.NCP_ENDPOINT_URL,
            )

            key = img_url.replace(f"{settings.NCP_BUCKET_URL}/", "")
            s3_client.delete_object(Bucket=settings.NCP_BUCKET_NAME, Key=key)
        except ClientError as e:
            logger.error(f"NCP delete error: {str(e)}")

    def patch(self, request: Request) -> Response:
        serializer = UserUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        old_img_url = user.img_url

        try:
            if "name" in serializer.validated_data:
                user.name = serializer.validated_data["name"]

            if "image" in serializer.validated_data:
                new_img_url = self._upload_to_ncp(
                    serializer.validated_data["image"], "profile-images"
                )
                user.img_url = new_img_url

                if old_img_url and self._is_ncp_image(old_img_url):
                    self._delete_from_ncp(old_img_url)

            user.save()

            return Response(
                {
                    "message": "프로필이 성공적으로 수정되었습니다.",
                    "name": user.name,
                    "img_url": user.img_url,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"message": f"프로필 수정 중 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # def delete(self, request: Request) -> Response:


class TokenRefreshView(GenericAPIView):
    serializer_class = RefreshTokenSerializer

    @extend_schema(
        tags=["user"],
        summary="액세스 토큰 갱신",
        description="리프레시 토큰을 사용하여 새로운 액세스 토큰을 발급합니다.",
        request=RefreshTokenSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string"},
                    "refresh_token": {"type": "string"},
                    "message": {"type": "string"},
                },
            }
        },
    )
    def post(self, request: Request) -> Response:
        # Redis를 이용한 동시성 제어
        redis_client = get_redis_connection("default")

        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            refresh_token = serializer.validated_data["refresh_token"]
            token = RefreshToken(refresh_token)

            # 새로운 액세스 토큰과 리프레시 토큰 생성
            access_token = str(token.access_token)
            new_refresh_token = str(token)

            # Redis에 새로운 토큰 정보 업데이트
            user_id = token.payload.get("user_id")
            cache.set(
                f"user_token:{user_id}",
                {"access_token": access_token, "refresh_token": new_refresh_token},
                timeout=cast(
                    timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
                ).total_seconds(),
            )

            response = Response(
                {
                    "access_token": access_token,
                    "refresh_token": new_refresh_token,
                    "message": "토큰이 성공적으로 갱신되었습니다.",
                },
                status=status.HTTP_200_OK,
            )

            # Authorization 헤더 설정
            response["Authorization"] = f"Bearer {access_token}"

            return response

        except TokenError:
            return Response(
                {"error": "유효하지 않은 리프레시 토큰입니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception as e:
            logger.error(f"Token blacklist failed: {str(e)}")
            return Response(
                {"error": f"토큰 갱신 중 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserPhoneCheckView(APIView):
    @extend_schema(
        tags=["user"],
        summary="휴대폰 번호로 계정 확인(계정찾기)",
        description="휴대폰 번호로 가입된 계정이 있는지 확인하고 가입 방식을 반환합니다.",
        request=PhoneCheckRequestSerializer,
        responses={200: PhoneCheckResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = PhoneCheckRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone = serializer.validated_data["phone"]

        try:
            user = CustomUser.objects.get(phone=phone)

            # provider가 없는 경우는 일반 회원가입 유저
            provider = user.provider if user.provider else "desub"

            return Response(
                {
                    "message": "현재 번호로 가입된 계정을 찾았습니다.",
                    "email": user.email,
                    "provider": provider,
                },
                status=status.HTTP_200_OK,
            )

        except CustomUser.DoesNotExist:
            return Response(
                {"message": "현재 번호로 가입된 계정이 없습니다."},
                status=status.HTTP_200_OK,
            )


class PasswordResetView(APIView):
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(
        tags=["user"],
        summary="비밀번호 초기화 요청(메일 발송)",
        description="이메일을 입력받아 임시 비밀번호를 생성하고 메일로 발송합니다.",
        request=PasswordResetRequestSerializer,
        responses={200: PasswordResetResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]

        try:
            user = CustomUser.objects.get(email=email)

            # 임시 비밀번호 생성 (12자리)
            temp_password = get_random_string(12)

            # 사용자 비밀번호 업데이트
            user.set_password(temp_password)
            user.save()

            # 이메일 내용 구성
            subject = "[DeSub] 임시 비밀번호가 발급되었습니다"
            html_message = render_to_string(
                "password_reset_email.html",  # 이메일 템플릿
                {"user": user, "temp_password": temp_password},
            )

            # 이메일 발송
            send_mail(
                subject=subject,
                message="",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=False,
            )

            return Response(
                {"message": "임시 비밀번호가 이메일로 발송되었습니다."},
                status=status.HTTP_200_OK,
            )

        except CustomUser.DoesNotExist:
            return Response(
                {"message": "등록되지 않은 이메일입니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"message": f"비밀번호 초기화 중 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    @extend_schema(
        tags=["user"],
        summary="비밀번호 변경",
        description="현재 비밀번호를 확인하고 새로운 비밀번호로 변경합니다.",
        request=PasswordChangeSerializer,
        responses={
            200: PasswordChangeResponseSerializer,
            400: OpenApiResponse(description="잘못된 요청"),
            401: OpenApiResponse(description="인증 실패"),
            500: OpenApiResponse(description="서버 오류"),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        # 현재 비밀번호 확인
        if not user.check_password(current_password):
            return Response(
                {"current_password": "현재 비밀번호가 일치하지 않습니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 새 비밀번호가 현재 비밀번호와 같은지 확인
        if current_password == new_password:
            return Response(
                {"new_password": "새 비밀번호는 현재 비밀번호와 달라야 합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 비밀번호 변경
            user.set_password(new_password)
            user.save()

            # # 선택사항: 비밀번호 변경 알림 이메일 발송
            # send_mail(
            #     subject="[DeSub] 비밀번호가 변경되었습니다",
            #     message=f"{user.name}님의 비밀번호가 변경되었습니다. 본인이 아닌 경우 즉시 고객센터로 문의해주세요.",
            #     from_email=settings.EMAIL_HOST_USER,
            #     recipient_list=[user.email],
            #     fail_silently=True,
            # )

            # 토큰 재발급 (선택사항)
            refresh = RefreshToken.for_user(user)

            return Response(
                {
                    "message": "비밀번호가 성공적으로 변경되었습니다.",
                    "access_token": str(refresh.access_token),
                    "refresh_token": str(refresh),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"message": f"비밀번호 변경 중 오류가 발생했습니다: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
