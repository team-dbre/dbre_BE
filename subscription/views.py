# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
#
# from subscription.models import Subs
#
#
# # Create your views here.
# @csrf_exempt
# def subscription_list(request):
#     if request.method == "GET":
#         subscriptions = list(Subs.objects.values())
#         return JsonResponse({"subscriptions": subscriptions}, safe=False)
#     return JsonResponse({"error": "Only GET method allowed"}, status=405)
