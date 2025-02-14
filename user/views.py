import logging

from datetime import timedelta
from typing import Any, cast
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.utils import timezone
from django_redis import get_redis_connection
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import status
from rest_framework.generics import CreateAPIView, GenericAPIView
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
    PhoneNumberSerializer,
    PhoneVerificationConfirmSerializer,
    PhoneVerificationRequestSerializer,
    RefreshTokenSerializer,
    TokenResponseSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
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
        summary="Email 사용 가능 여부",
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
                    # "user_id": {"type": "string"},
                },
            }
        },
    )
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
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


@extend_schema(tags=["user"])
class LogoutView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request: Request) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # access token도 blacklist에 추가
            access_token = request.auth
            if access_token:
                RefreshToken(access_token).blacklist()

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
        except TokenError as e:
            return Response(
                {"message": "유효하지 않은 토큰입니다.", "detail": str(e)},
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
                    # "user_id": user.id,
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
                error_message = "잠시 후 다시 시도해주세요."

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
                return Response({"message": "인증이 완료되었습니다."})
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
    )
)
class UserProfileView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get(self, request: Request) -> Response:
        user = request.user
        serializer = self.serializer_class(user)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
                }
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
