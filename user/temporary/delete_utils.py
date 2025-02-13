# def format_phone_for_twilio(phone: str) -> str:
#     """전화번호를 Twilio 형식(+82xxxxxxxxxx)으로 변환"""
#     phone = phone.replace('-', '')
#     cleaned = "".join(filter(str.isdigit, phone))
#
#     # 이미 국가 코드가 있는 경우
#     if cleaned.startswith("82"):
#         print(f"+{cleaned}")
#         return f"+{cleaned}"
#
#     # 0으로 시작하는 경우 국가 코드로 변환
#     if cleaned.startswith("0"):
#         print(f"+82{cleaned[1:]}")
#         return f"+82{cleaned[1:]}"
#
#     print(f"+82{cleaned}")
#     return f"+82{cleaned}"