from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http.request import HttpRequest
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, extend_schema, extend_schema_view, OpenApiResponse
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.generics import CreateAPIView, GenericAPIView
from rest_framework.renderers import JSONRenderer
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from term.models import Terms
from user.models import Agreements, CustomUser
from user.serializers import (
    EmailCheckSerializer,
    LoginSerializer,
    LogoutSerializer,
    UserRegistrationSerializer, GoogleCallbackSerializer, GoogleLoginSerializer,
)
from user.utils import get_google_access_token, get_google_user_info


@extend_schema_view(
    post=extend_schema(
        summary="User Registration",
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
        summary="Check Email Availability",
        description="Check if the provided email is already registered.",
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
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        return super().post(request, *args, **kwargs)


class LogoutView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request: HttpRequest) -> Response:
        try:
            serializer = self.get_serializer(data=request.data)  # type: ignore
            serializer.is_valid(raise_exception=True)

            refresh_token = serializer.validated_data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            response = Response(
                {"message": "로그아웃이 완료되었습니다."}, status=status.HTTP_200_OK
            )

            # 쿠키 삭제를 set_cookie로 구현
            response.set_cookie(
                "refresh_token",
                value="",
                max_age=0,
                expires="Thu, 01 Jan 1970 00:00:00 GMT",
                path="/",
                secure=True,
                httponly=True,
                samesite="None",
            )

            return response

        except Exception as e:
            return Response(
                {"message": "로그아웃에 실패했습니다.", "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class GoogleLoginView(GenericAPIView):
    serializer_class = GoogleLoginSerializer
    renderer_classes = [JSONRenderer]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=GoogleLoginSerializer,
                description='구글 로그인 URL 반환'
            )
        }
    )
    def get(self, request):
        params = {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'redirect_uri': settings.GOOGLE_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'email profile',
            'access_type': 'offline',
            'prompt': 'select_account',
        }

        auth_url = f'https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}'
        return Response({'auth_url': auth_url})

    @extend_schema(
        request=GoogleLoginSerializer,
        responses={
            200: OpenApiResponse(
                response=GoogleLoginSerializer,
                description='구글 로그인 완료'
            )
        }
    )
    def post(self, request):
        try:
            code = request.data.get('code')
            access_token = get_google_access_token(code)
            user_info = get_google_user_info(access_token)

            try:
                user = CustomUser.objects.get(email=user_info['email'])
            except CustomUser.DoesNotExist:
                user = CustomUser.objects.create_user(
                    email=user_info['email'],
                    name=user_info.get('name', ''),
                    provider='google',
                    img_url=user_info.get('picture'),
                )

                latest_terms = Terms.objects.latest('created_at')
                Agreements.objects.create(
                    user=user,
                    terms_url=f'/terms/{latest_terms.id}',
                    agreed_at=timezone.now(),
                    marketing=False
                )

            refresh = RefreshToken.for_user(user)
            return Response({
                'message': '구글 로그인이 완료되었습니다.',
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                'message': '구글 로그인에 실패했습니다.',
                'detail': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class GoogleCallbackView(GenericAPIView):
    serializer_class = GoogleCallbackSerializer
    renderer_classes = [JSONRenderer]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=GoogleCallbackSerializer,
                description='구글 콜백 처리'
            )
        }
    )
    def get(self, request):
        code = request.GET.get('code')
        if not code:
            return Response({
                'message': '인증 코드가 없습니다.'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'code': code
        }, status=status.HTTP_200_OK)