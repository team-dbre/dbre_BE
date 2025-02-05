from typing import Any

from django.http.request import HttpRequest
from django.shortcuts import render
from django.utils.decorators import method_decorator
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import GenericAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Terms
from .serializers import TermsModelSerializer


@extend_schema_view(
    get=extend_schema(
        tags=["term"],
        summary="List all Terms",
        description="Retrieve a list of all Terms entries.",
        responses=TermsModelSerializer,
    ),
    post=extend_schema(
        tags=["term"],
        summary="Create a new Term",
        description="Create a new Terms entry by providing 'use' and 'privacy_policy' fields.",
        request=TermsModelSerializer,
        responses=TermsModelSerializer,
    ),
)
class CreateTermAPI(ListCreateAPIView):
    queryset = Terms.objects.all()
    serializer_class = TermsModelSerializer


class LatestTermsAPI(GenericAPIView):
    serializer_class = TermsModelSerializer
    queryset = Terms.objects.all()

    @extend_schema(
        tags=["term"],
        summary="Get the latest Terms",
        description="Fetch the most recently created Terms entry.",
        responses={200: TermsModelSerializer},  # 상태 코드와 함께 응답 타입 지정
    )
    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        latest_term = Terms.objects.latest("created_at")
        serializer = self.get_serializer(latest_term)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(
        tags=["term"],
        summary="Get Terms by ID",
        description="Fetch a specific Terms entry by its ID.",
    )
)
class TermsDetailAPI(RetrieveAPIView):
    queryset = Terms.objects.all()
    serializer_class = TermsModelSerializer
    lookup_field = "id"  # URL에서 id를 기준으로 조회
