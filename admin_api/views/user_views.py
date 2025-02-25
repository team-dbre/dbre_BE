from django.db.models import Case, CharField, Count, OuterRef, Q, Subquery, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status

# from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.serializers import (
    ConfirmUserDeletionRequestSerializer,
    ConfirmUserDeletionResponseSerializer,
    DeletedUserSerializer,
    ErrorResponseSerializer,
    UserManagementResponseSerializer,
    UserManagementSerializer,
    UserRecoveryRequestSerializer,
    UserRecoveryResponseSerializer,
)
from payment.models import Pays
from subscription.models import Subs
from user.models import Agreements, CustomUser, WithdrawalReason


# 현재 pagination 프론트에서 관리
# class CustomPagination(PageNumberPagination):
#     page_size = 10
#     page_size_query_param = "page_size"
#     max_page_size = 100


class UserManagementView(APIView):
    permission_classes = [IsAdminUser]
    # pagination_class = CustomPagination

    @extend_schema(
        tags=["admin"],
        summary="Admin page 고객관리 고객목록",
        description="고객목록 정렬기준 (name, email, phone, is_subscribed (구독여부), sub_status (구독현황), created_at (가입일), last_login (마지막 방문일), marketing_consent (마케팅 수신동의), start_date (최초결제일), latest_paid_at (최근결제일), end_date (구독만료일)",
        # parameters=[
        #     OpenApiParameter(
        #         name="order_by", description="정렬 기준 필드", type=OpenApiTypes.STR
        #     ),
        #     OpenApiParameter(
        #         name="order_direction",
        #         description="정렬 순서 (asc 또는 desc)",
        #         type=OpenApiTypes.STR,
        #     ),
        #     OpenApiParameter(
        #         name="page", description="페이지 번호", type=OpenApiTypes.INT
        #     ),
        #     OpenApiParameter(
        #         name="page_size", description="페이지당 항목 수", type=OpenApiTypes.INT
        #     ),
        # ],
        responses={200: UserManagementResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        # order_by = request.query_params.get("order_by", "name")
        # order_direction = request.query_params.get("order_direction", "asc")
        #
        # valid_order_fields = {
        #     "name": "name",
        #     "email": "email",
        #     "phone": "phone",
        #     "sub_status": "sub_status",
        #     "created_at": "created_at",
        #     "last_login": "last_login",
        #     "marketing": "marketing_consent",
        #     "start_date": "start_date",
        #     "paid_at": "latest_paid_at",
        #     "end_date": "end_date",
        # }
        #
        # if order_by not in valid_order_fields:
        #     order_by = "name"
        #
        # order_prefix = "-" if order_direction == "desc" else ""
        # order_field = f"{order_prefix}{valid_order_fields[order_by]}"

        today = timezone.now().date()

        # 서브쿼리 최적화
        latest_sub = Subs.objects.filter(user=OuterRef("pk")).order_by("-start_date")
        latest_payment = Pays.objects.filter(user=OuterRef("pk")).order_by("-paid_at")

        users = (
            CustomUser.objects.filter(is_active=True, is_staff=False)
            .annotate(
                is_subscribed=Case(
                    When(sub_status__in=["active", "paused"], then=Value("구독중")),
                    default=Value("미구독"),
                    output_field=CharField(),
                ),
                marketing_consent=Coalesce(
                    Subquery(
                        Agreements.objects.filter(user=OuterRef("pk")).values(
                            "marketing"
                        )[:1]
                    ),
                    Value(False),
                ),
                start_date=Subquery(latest_sub.values("start_date")[:1]),
                end_date=Subquery(latest_sub.values("end_date")[:1]),
                latest_paid_at=Subquery(latest_payment.values("paid_at")[:1]),
            )
            .prefetch_related("agreements_set")  # agreements_set으로 변경
            # .order_by(order_field)
        )

        # paginator = self.pagination_class()
        # paginated_users = paginator.paginate_queryset(users, request)
        # serializer = UserManagementSerializer(paginated_users, many=True)
        serializer = UserManagementSerializer(users, many=True)

        # 통계 쿼리 최적화
        user_stats = CustomUser.objects.aggregate(
            total_users=Count("id", filter=Q(is_staff=False)),
            new_users_today=Count(
                "id", filter=Q(created_at__date=today, is_active=True, is_staff=False)
            ),
            deleted_users_today=Count("id", filter=Q(deleted_at__date=today)),
        )

        response_data = {
            # "count": paginator.page.paginator.count,
            # "next": paginator.get_next_link(),
            # "previous": paginator.get_previous_link(),
            "statistics": user_stats,
            "users": serializer.data,
        }

        return Response(response_data)


class DeleteUserMangementView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["admin"],
        summary="Admin page 탈퇴 요청 회원 목록",
        description="is_deletion_confirmed로 관리자가 탈퇴 요청을 승낙했는지 거부했는지 확인해야합니다.",
        responses={200: DeletedUserSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        # Subquery for withdrawal reason
        reason_subquery = WithdrawalReason.objects.filter(user=OuterRef("pk")).values(
            "reason"
        )[:1]

        deleted_users = (
            CustomUser.objects.filter(deleted_at__isnull=False)
            .annotate(reason=Subquery(reason_subquery))
            .values(
                "id",
                "deleted_at",
                "name",
                "email",
                "phone",
                "reason",
                "is_deletion_confirmed",
            )
        )

        serializer = DeletedUserSerializer(deleted_users, many=True)
        return Response(serializer.data)

    @extend_schema(
        tags=["admin"],
        summary="Admin page 탈퇴 요청 승인",
        description="특정 유저의 탈퇴 요청을 승인합니다. is_deletion_confirmed를 True로 변경합니다.",
        request=ConfirmUserDeletionRequestSerializer,
        responses={
            200: ConfirmUserDeletionResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ConfirmUserDeletionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({"error": serializer.errors}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = serializer.validated_data["user_id"]

        try:
            user = CustomUser.objects.get(id=user_id, deleted_at__isnull=False)
            if user.is_deletion_confirmed:
                return Response(
                    {"message": "이미 탈퇴 처리된 회원입니다."},
                    status=status.HTTP_200_OK,
                )

            user.is_deletion_confirmed = True
            user.save()
            return Response(
                {"message": f"회원 {user_id} 탈퇴 처리를 성공적으로 마쳤습니다."},
                status=status.HTTP_200_OK,
            )
        except CustomUser.DoesNotExist:
            return Response(
                {
                    "error": f"회원 {user_id} 을 찾을 수 없거나 탈퇴를 요청한 회원이 아닙니다."
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class UserRecoveryView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        tags=["admin"],
        summary="탈퇴 처리된 회원 복구",
        description="탈퇴 처리된 회원을 복구합니다.",
        request=UserRecoveryRequestSerializer,
        responses={
            200: UserRecoveryResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = UserRecoveryRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                ErrorResponseSerializer({"error": serializer.errors}).data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_id = serializer.validated_data["user_id"]

        try:
            user = CustomUser.objects.get(id=user_id, deleted_at__isnull=False)

            if not user.id_active:
                return Response(
                    {"error": "아직 탈퇴 처리되지 않은 회원입니다."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.is_deletion_confirmed = False
            user.is_active = True
            user.deleted_at = None
            user.save()

            response_serializer = UserRecoveryResponseSerializer(user)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "해당 사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
