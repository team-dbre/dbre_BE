import random

from datetime import timedelta
from typing import Any, cast
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiExample,
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
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from term.models import Terms
from user.models import Agreements, CustomUser
from user.serializers import (
    AuthUrlResponseSerializer,
    EmailCheckSerializer,
    LoginSerializer,
    LogoutSerializer,
    PhoneNumberSerializer,
    PhoneVerificationConfirmSerializer,
    PhoneVerificationRequestSerializer,
    TokenResponseSerializer,
    UserRegistrationSerializer,
)
from user.utils import (
    format_phone_for_twilio,
    get_google_access_token,
    get_google_user_info,
    normalize_phone_number,
)


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


@extend_schema(tags=["user"])
class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer  # type: ignore

    @extend_schema(
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
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # 토큰 정보 가져오기
            access_token = response.data.get("access_token")
            refresh_token = response.data.get("refresh_token")

            # 현재 사용자 정보 가져오기
            user = request.user

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

            # Redis에서 토큰 삭제
            cache.delete(f"user_token:{request.user.id}")

            refresh_token = serializer.validated_data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            response = Response(
                {"message": "로그아웃이 완료되었습니다."}, status=status.HTTP_200_OK
            )

            response.delete_cookie("refresh_token")

            return response

        except Exception as e:
            return Response(
                {"message": "로그아웃에 실패했습니다.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GoogleLoginView(GenericAPIView):
    renderer_classes = [JSONRenderer]

    @extend_schema(tags=["user"], responses={200: AuthUrlResponseSerializer})
    def get(self, request: Request) -> Response:
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "prompt": "select_account",
        }

        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        return Response({"auth_url": auth_url})


class GoogleCallbackView(GenericAPIView):
    renderer_classes = [JSONRenderer]

    @extend_schema(
        tags=["user"],
        responses={
            200: OpenApiResponse(
                response=TokenResponseSerializer, description="구글 콜백 처리"
            )
        },
    )
    def get(self, request: Request) -> Response:
        code = request.GET.get("code")
        if not code:
            return Response(
                {"message": "인증 코드가 없습니다."}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            access_token = get_google_access_token(code)
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

            # Redis에 토큰 저장
            cache.set(
                f"user_token:{user.id}",
                {"access_token": access_token, "refresh_token": refresh_token},
                timeout=cast(
                    timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
                ).total_seconds(),
            )

            return Response(
                {
                    "message": "구글 로그인이 완료되었습니다.",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "phone": bool(user.phone),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response(
                {"message": "구글 로그인에 실패했습니다.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RequestVerificationView(APIView):
    serializer_class = PhoneVerificationRequestSerializer

    def post(self, request: Request) -> Response:
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        phone = serializer.validated_data["phone"]
        formatted_phone = format_phone_for_twilio(phone)

        try:
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            verification = client.verify.v2.services(
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
                cache.set(f"phone_verified:{phone}", "true", timeout=86400)
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


# twilio active number 구매 버전
# class RequestVerificationView(APIView):
#     serializer_class = PhoneVerificationRequestSerializer
#
#     @extend_schema(
#         tags=["user"],
#         summary="전화번호 인증번호 요청",
#         description="전화번호를 입력받아 인증번호를 SMS로 발송합니다.",
#         request=PhoneVerificationRequestSerializer,
#         responses={
#             200: OpenApiResponse(
#                 description="인증번호 발송 성공",
#                 response={
#                     "type": "object",
#                     "properties": {"message": {"type": "string"}},
#                 },
#             ),
#             400: OpenApiResponse(
#                 description="잘못된 요청",
#                 response={
#                     "type": "object",
#                     "properties": {"error": {"type": "string"}},
#                 },
#             ),
#         },
#     )
#     def post(self, request: Request) -> Response:
#         serializer = self.serializer_class(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#
#         phone = serializer.validated_data["phone"]
#         formatted_phone = format_phone_for_twilio(
#             phone
#         )  # 010-xxxx-xxxx를 +8210xxxxxxxx로 변환
#         verification_code = "".join([str(random.randint(0, 9)) for _ in range(6)])
#
#         cache.set(f"phone_verification:{phone}", verification_code, timeout=300)
#
#         try:
#             client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#             client.messages.create(
#                 body=f"인증번호: {verification_code}",
#                 from_=settings.TWILIO_PHONE_NUMBER,
#                 to=formatted_phone,
#             )
#             return Response({"message": "인증번호가 발송되었습니다."})
#         except TwilioRestException as e:
#             error_message = f"SMS 발송 실패: {str(e)}"
#             return Response(
#                 {"error": error_message}, status=status.HTTP_400_BAD_REQUEST
#             )
#
#
# class VerifyPhoneView(APIView):
#     serializer_class = PhoneVerificationConfirmSerializer
#
#     @extend_schema(
#         tags=["user"],
#         summary="전화번호 인증번호 확인",
#         description="전화번호와 인증번호를 입력받아 인증을 진행합니다.",
#         request=PhoneVerificationConfirmSerializer,
#         responses={
#             200: OpenApiResponse(
#                 description="인증 성공",
#                 response={
#                     "type": "object",
#                     "properties": {"message": {"type": "string"}},
#                 },
#             ),
#             400: OpenApiResponse(
#                 description="잘못된 요청",
#                 response={
#                     "type": "object",
#                     "properties": {"error": {"type": "string"}},
#                 },
#             ),
#         },
#     )
#     def post(self, request: Request) -> Response:
#         serializer = self.serializer_class(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#
#         phone = serializer.validated_data["phone"]
#         code = serializer.validated_data["code"]
#
#         stored_code = cache.get(f"phone_verification:{phone}")
#
#         if not stored_code:
#             return Response(
#                 {"error": "인증번호가 만료되었습니다."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )
#
#         if code != stored_code:
#             return Response(
#                 {"error": "잘못된 인증번호입니다."}, status=status.HTTP_400_BAD_REQUEST
#             )
#
#         cache.set(f"phone_verified:{phone}", "true", timeout=86400)
#
#         return Response({"message": "인증이 완료되었습니다."})
