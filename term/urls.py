# Term 관련 URL 패턴
from django.urls import path

from term.views import CreateTermAPI, LatestTermsAPI, TermsDetailAPI


term_patterns = [
    path("", CreateTermAPI.as_view(), name="create_term"),
    path("latest/", LatestTermsAPI.as_view(), name="latest_term"),
    path("<int:id>/", TermsDetailAPI.as_view(), name="term_detail"),
]
