# twilio active number 구매 버전
# class RequestVerificationView(APIView):
#     serializer_class = PhoneVerificationRequestSerializer
#
#     @extend_schema(
#         tags=["user"],
#         summary="전화번호 인증번호 요청",
#         description="전화번호를 입력받아 인증번호를 SMS로 발송합니다.",
#         request=PhoneVerificationRequestSerializer,
#         responses={
#             200: OpenApiResponse(
#                 description="인증번호 발송 성공",
#                 response={
#                     "type": "object",
#                     "properties": {"message": {"type": "string"}},
#                 },
#             ),
#             400: OpenApiResponse(
#                 description="잘못된 요청",
#                 response={
#                     "type": "object",
#                     "properties": {"error": {"type": "string"}},
#                 },
#             ),
#         },
#     )
#     def post(self, request: Request) -> Response:
#         serializer = self.serializer_class(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#
#         phone = serializer.validated_data["phone"]
#         formatted_phone = format_phone_for_twilio(
#             phone
#         )  # 010-xxxx-xxxx를 +8210xxxxxxxx로 변환
#         verification_code = "".join([str(random.randint(0, 9)) for _ in range(6)])
#
#         cache.set(f"phone_verification:{phone}", verification_code, timeout=300)
#
#         try:
#             client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#             client.messages.create(
#                 body=f"인증번호: {verification_code}",
#                 from_=settings.TWILIO_PHONE_NUMBER,
#                 to=formatted_phone,
#             )
#             return Response({"message": "인증번호가 발송되었습니다."})
#         except TwilioRestException as e:
#             error_message = f"SMS 발송 실패: {str(e)}"
#             return Response(
#                 {"error": error_message}, status=status.HTTP_400_BAD_REQUEST
#             )
#
#
# class VerifyPhoneView(APIView):
#     serializer_class = PhoneVerificationConfirmSerializer
#
#     @extend_schema(
#         tags=["user"],
#         summary="전화번호 인증번호 확인",
#         description="전화번호와 인증번호를 입력받아 인증을 진행합니다.",
#         request=PhoneVerificationConfirmSerializer,
#         responses={
#             200: OpenApiResponse(
#                 description="인증 성공",
#                 response={
#                     "type": "object",
#                     "properties": {"message": {"type": "string"}},
#                 },
#             ),
#             400: OpenApiResponse(
#                 description="잘못된 요청",
#                 response={
#                     "type": "object",
#                     "properties": {"error": {"type": "string"}},
#                 },
#             ),
#         },
#     )
#     def post(self, request: Request) -> Response:
#         serializer = self.serializer_class(data=request.data)
#         if not serializer.is_valid():
#             return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
#
#         phone = serializer.validated_data["phone"]
#         code = serializer.validated_data["code"]
#
#         stored_code = cache.get(f"phone_verification:{phone}")
#
#         if not stored_code:
#             return Response(
#                 {"error": "인증번호가 만료되었습니다."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )
#
#         if code != stored_code:
#             return Response(
#                 {"error": "잘못된 인증번호입니다."}, status=status.HTTP_400_BAD_REQUEST
#             )
#
#         cache.set(f"phone_verified:{phone}", "true", timeout=86400)
#
#         return Response({"message": "인증이 완료되었습니다."})