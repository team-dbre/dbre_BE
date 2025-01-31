import os
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from dotenv import load_dotenv

load_dotenv()

# def user_verify_view(request):
#     context = {
#         'STORE_ID': os.getenv('STORE_ID'),
#         'CHANNEL_KEY': os.getenv('DANAL_CHANNEL_KEY')
#     }
#     return render(request, 'user_verify.html', context)
#
# @csrf_exempt
# def verify_phone(request):
#     try:
#         # 클라이언트에서 전송된 identityVerificationId
#         identity_verification_id = request.POST.get('identityVerificationId')
#
#         # Portone API 토큰 발급
#         token_response = requests.post('https://api.portone.io/users/getToken', json={
#             'imp_key': os.getenv('IMP_API_KEY'),
#             'imp_secret': os.getenv('IMP_API_SECRET')
#         })
#         access_token = token_response.json()['response']['access_token']
#
#         # 인증 정보 조회
#         verify_response = requests.get(
#             f'https://api.portone.io/identity-verifications/{identity_verification_id}',
#             headers={'Authorization': f'Bearer {access_token}'}
#         )
#
#         verification_data = verify_response.json()['response']
#
#         # 세션에 인증 정보 임시 저장
#         request.session['phone_verified'] = {
#             'phone_number': verification_data.get('phone'),
#             'name': verification_data.get('name')
#         }
#
#         return JsonResponse({
#             'success': True,
#             'message': '인증 성공'
#         })
#
#     except Exception as e:
#         return JsonResponse({
#             'success': False,
#             'message': str(e)
#         }, status=400)
