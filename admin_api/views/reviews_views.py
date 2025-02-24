# from django.utils.timezone import now
# from drf_spectacular.utils import extend_schema
# from rest_framework import status, viewsets
# from rest_framework.permissions import IsAdminUser
# from rest_framework.request import Request
# from rest_framework.response import Response
# from rest_framework.views import APIView
#
# from reviews.models import Review
#
#
# @extend_schema(tags=["admin"])
# class AdminReviewView(APIView):
#     permission_classes = [IsAdminUser]
#     serializer_class = AdminReviewSerializer
#
#     def get(self, request: Request) -> Response:
#         all_reviews = Review.objects.all().count()
#         new_reviews = Review.objects.filter(created_at__date=now().date()).count()
#
#         reviews = Review.objects.select_related("user").all()
#         serializer = AdminReviewSerializer(reviews, many=True)
#         return Response(
#             {
#                 "dashboard": {
#                     "reviews": all_reviews,
#                     "new_reviews": new_reviews,
#                 },
#                 "requests": serializer.data,
#             },
#             status=status.HTTP_200_OK,
#         )
