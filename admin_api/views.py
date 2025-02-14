from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.serializers import AdminUserSerializer


class CreateAdminView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["admin"],
        summary="Create Admin User",
        description="Create a new admin user with is_staff=True (requires superuser)",
        request=AdminUserSerializer,
        responses={
            201: OpenApiResponse(
                response=AdminUserSerializer,
                description="Admin user created successfully",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        if not request.user.is_superuser:
            return Response(
                {"message": "슈퍼유저만 관리자 계정을 생성할 수 있습니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AdminUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {"message": "관리자 계정이 생성되었습니다.", "email": user.email},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
