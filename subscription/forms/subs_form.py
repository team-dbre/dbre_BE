from typing import Any, Dict

from django import forms

from subscription.models import Subs


class SubsForm(forms.ModelForm):
    class Meta:
        model = Subs
        fields = ["start_date", "end_date", "cancelled_reason", "other_reason"]
        widgets = {
            "other_reason": forms.TextInput(
                attrs={"placeholder": "기타 사유를 입력하세요."}
            ),
        }

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        reason = cleaned_data.get("cancelled_reason")
        other_reason = cleaned_data.get("other_reason")

        if reason == "other" and not other_reason:
            self.add_error("other_reason", "기타 사유를 입력해야 합니다.")

        return cleaned_data
