from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.forms import formset_factory

from .models import Course
from .roles import INSTRUCTOR, TA


class StaffChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        name = user.get_full_name() or user.get_username()
        return f"{name} ({user.email or user.get_username()})"


class CourseForm(forms.ModelForm):
    instructor = StaffChoiceField(queryset=None, label="Instructor")
    ta1 = StaffChoiceField(queryset=None, label="TA 1")
    ta2 = StaffChoiceField(queryset=None, label="TA 2")

    class Meta:
        model = Course
        fields = ["course_number", "course_name"]
        error_messages = {"course_number": {"unique": "A course with this course number already exists."}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        users = get_user_model().objects.filter(is_active=True)
        for field, role in (("instructor", INSTRUCTOR), ("ta1", TA), ("ta2", TA)):
            self.fields[field].queryset = users.filter(groups__name=role).order_by("first_name", "last_name", "pk").distinct()
            self.fields[field].error_messages.update({
                "required": "Exactly one instructor and two TAs are required; select this person.",
                "invalid_choice": f"Select an existing active {role} account for this position.",
            })

    def clean(self):
        data = super().clean()
        staff = [data[key].pk for key in ("instructor", "ta1", "ta2") if key in data]
        if len(staff) != len(set(staff)):
            raise forms.ValidationError("All three staff assignments must be different people.")
        return data


class AvailabilityForm(forms.Form):
    location = forms.CharField(max_length=120)
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    start_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    def clean(self):
        data = super().clean()
        if data.get("start_time") and data.get("end_time") and data["end_time"] <= data["start_time"]:
            self.add_error("end_time", "End time must be later than start time.")
        return data


AvailabilityFormSet = formset_factory(
    AvailabilityForm, extra=0, min_num=1, validate_min=True,
    max_num=50, validate_max=True, absolute_max=50, can_delete=True,
)


ROLE_TO_GROUP_NAME = {
    "instructor": "Instructor",
    "ta": "TA",
}


class CreateStaffAccountForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        required=True,
        error_messages={"required": "Name is required."},
    )
    email = forms.EmailField(
        required=True,
        error_messages={
            "required": "A valid email address is required.",
            "invalid": "Enter a valid email address.",
        },
    )
    role = forms.ChoiceField(
        choices=[("instructor", "Instructor"), ("ta", "TA")],
        required=True,
        error_messages={
            "required": "Role is required.",
            "invalid_choice": "Select a valid role (Instructor or TA).",
        },
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_role(self):
        role = self.cleaned_data["role"].strip().lower()
        group_name = ROLE_TO_GROUP_NAME.get(role)
        if not group_name:
            raise forms.ValidationError("Invalid role selected.")
        group, _ = Group.objects.get_or_create(name=group_name)
        return group


class EditAccountForm(forms.Form):
    name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(
        choices=[("instructor", "Instructor"), ("ta", "TA")],
        required=True,
    )

    def __init__(self, *args, target_user=None, **kwargs):
        self.target_user = target_user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        user_model = get_user_model()
        qs = user_model.objects.filter(email__iexact=email)
        if self.target_user is not None:
            qs = qs.exclude(pk=self.target_user.pk)
        if qs.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_role(self):
        role = self.cleaned_data["role"].strip().lower()
        group_name = ROLE_TO_GROUP_NAME.get(role)
        if not group_name:
            raise forms.ValidationError("Invalid role selected.")
        group, _ = Group.objects.get_or_create(name=group_name)
        return group
