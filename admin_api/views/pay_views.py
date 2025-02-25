from django.db.models import Q, Sum
from django.utils.timezone import now
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from admin_api.serializers import AdminSalesSerializer
from payment.models import Pays


@extend_schema(tags=["admin"])
class AdminSalesPayView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminSalesSerializer

    def get(self, request: Request) -> Response:
        """관리자 결제 및 환불 내역 조회 API"""
        monthly_sales = (
            Pays.objects.filter(paid_at__month=now().date().month).aggregate(
                total_amount=Sum("amount")
            )["total_amount"]
            or 0
        )
        monthly_refunds = (
            Pays.objects.filter(refund_at__month=now().date().month).aggregate(
                total_refund=Sum("refund_amount")
            )["total_refund"]
            or 0
        )
        monthly_total_sales = monthly_sales - monthly_refunds

        transactions = (
            Pays.objects.select_related("user")
            .filter(Q(amount__gt=0) | Q(refund_amount__gt=0))  # 결제 or 환불 내역 존재
            .order_by("-paid_at")
        )

        # 결제 & 환불 내역을 따로 처리하여 한 개의 결제 ID에서 두 개의 레코드 반환
        serialized_transactions = []
        for transaction in transactions:
            # 결제 내역 추가 (환불이 있어도 "결제"로 표시됨)
            serialized_transactions.append(
                AdminSalesSerializer(transaction, context={"is_refund": False}).data
            )

            # 환불 내역이 있으면 추가 (이때는 "구독취소"로 표시)
            if transaction.refund_amount:
                serialized_transactions.append(
                    AdminSalesSerializer(transaction, context={"is_refund": True}).data
                )

        return Response(
            {
                "dashboard": {
                    "monthly_sales": monthly_sales,
                    "monthly_refunds": monthly_refunds,
                    "monthly_total_sales": monthly_total_sales,
                },
                "transactions": serialized_transactions,
            },
            status=status.HTTP_200_OK,
        )
