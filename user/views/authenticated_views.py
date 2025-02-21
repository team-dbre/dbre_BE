import logging
import uuid

import boto3

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from user.models import Agreements, CustomUser
from user.serializers import (
    LogoutSerializer,
    PasswordChangeResponseSerializer,
    PasswordChangeSerializer,
    PhoneNumberSerializer,
    TokenResponseSerializer,
    UserProfileSerializer,
    UserUpdateResponseSerializer,
    UserUpdateSerializer,
)
from user.utils import normalize_phone_number


logger = logging.getLogger(__name__)


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
            marketing_agreement = serializer.validated_data.get(
                "marketing_agreement", False
            )

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

            # 마케팅 동의 정보 업데이트
            agreement = Agreements.objects.filter(user=request.user).first()
            if agreement and marketing_agreement:
                agreement.marketing = marketing_agreement
                agreement.save()

            return Response(
                {"message": "전화번호가 저장되었습니다."}, status=status.HTTP_200_OK
            )

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
