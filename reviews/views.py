from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from reviews.models import Review
from reviews.serializers import ReviewGetSerializer, ReviewSerializer


@extend_schema(
    tags=["review"],
    responses={200: ReviewSerializer()},
    request=ReviewSerializer,
    summary="리뷰",
)
class ReviewCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        """리뷰 작성"""
        serializer = ReviewSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request: Request) -> Response:
        all_reviews = Review.objects.all().count()
        new_reviews = Review.objects.filter(created_at__date=now().date()).count()
        # 리뷰 전체 조회
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)

        reviews = Review.objects.all()
        serializer = ReviewGetSerializer(reviews, many=True)
        return Response(
            {
                "dashboard": {
                    "reviews": all_reviews,
                    "new_reviews": new_reviews,
                },
                "requests": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# @extend_schema(
#     tags=["review"],
#     responses={200: ReviewGetSerializer()},
#     request=ReviewGetSerializer,
# )
# class ReviewDetailView(APIView):
#     """
#     리뷰 상세 조회
#     """
#
#     permission_classes = [IsAdminUser]
#     serializer_class = ReviewGetSerializer
#
#     def get(self, request: Request, review_id: int) -> Response:
#         review = get_object_or_404(Review, id=review_id)
#         serializer = ReviewGetSerializer(review, context={"request": request})
#         return Response(serializer.data, status=status.HTTP_200_OK)
