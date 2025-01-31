from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.generics import CreateAPIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone

from term.models import Terms
from user.models import CustomUser, Agreements
from user.serializers import UserRegistrationSerializer


@extend_schema_view(
    post=extend_schema(
        summary="User Registration",
        description="Register a new user with terms agreements.",
        request=UserRegistrationSerializer,
        responses={201: UserRegistrationSerializer}
    )
)
class UserRegistrationView(CreateAPIView):
    serializer_class = UserRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = CustomUser.objects.create_user(
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
            name=serializer.validated_data['name'],
            phone=serializer.validated_data['phone']
        )

        # 최신 약관 정보 가져오기
        latest_terms = Terms.objects.latest('created_at')

        # 하나의 약관 동의 레코드 생성
        Agreements.objects.create(
            user=user,
            terms_url=f'/terms/{latest_terms.id}',
            agreed_at=timezone.now(),
            marketing=serializer.validated_data.get('marketing_agreement', False)
        )

        return Response({
            'message': '회원가입이 완료되었습니다.',
            'email': user.email,
            'name': user.name
        }, status=status.HTTP_201_CREATED)
