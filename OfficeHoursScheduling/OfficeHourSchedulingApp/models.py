from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q

from .roles import INSTRUCTOR, TA


class Course(models.Model):
    course_number = models.CharField(max_length=20, unique=True)
    course_name = models.CharField(max_length=120)

    class Meta:
        ordering = ["course_number"]

    def clean(self):
        super().clean()
        self.course_number = self.course_number.strip()
        self.course_name = self.course_name.strip()
        errors = {}
        if not self.course_number:
            errors["course_number"] = "A course number is required."
        if not self.course_name:
            errors["course_name"] = "A course name is required."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.course_number} — {self.course_name}"


class StaffAssignment(models.Model):
    class Role(models.TextChoices):
        INSTRUCTOR = INSTRUCTOR, "Instructor"
        TA = TA, "TA"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="staff_assignments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_staff_assignments")
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["course", "user"], name="unique_course_staff"),
            models.UniqueConstraint(fields=["course"], condition=Q(role=INSTRUCTOR), name="one_course_instructor"),
            models.CheckConstraint(condition=Q(role__in=[INSTRUCTOR, TA]), name="valid_staff_role"),
        ]

    def clean(self):
        super().clean()
        if self.user_id and (not self.user.is_active or not self.user.groups.filter(name=self.role).exists()):
            raise ValidationError({"user": f"Select an active {self.role} account."})

    def __str__(self):
        return f"{self.course.course_number}: {self.user} ({self.role})"


class TimeRange(models.Model):
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    location = models.CharField(max_length=120)

    class Meta:
        abstract = True
        ordering = ["date", "start_time"]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "End time must be later than start time."})


class Availability(TimeRange):
    assignment = models.ForeignKey(StaffAssignment, on_delete=models.CASCADE, related_name="availability")

    class Meta(TimeRange.Meta):
        abstract = False
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="availability_positive_range")]


class Enrollment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_enrollments")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["course", "student"], name="unique_course_student")]


class OfficeHour(TimeRange):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        CANCELED = "canceled", "Canceled"

    assignment = models.ForeignKey(StaffAssignment, on_delete=models.CASCADE, related_name="office_hours")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)

    class Meta(TimeRange.Meta):
        abstract = False
        constraints = [models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="office_hour_positive_range")]


class Reservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELED = "canceled", "Canceled"

    office_hour = models.ForeignKey(OfficeHour, on_delete=models.CASCADE, related_name="reservations")
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="office_hour_reservations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["office_hour", "student"], name="unique_office_hour_student")]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self._state.adding or self.status != self.Status.CANCELED:
                office_hour = OfficeHour.objects.select_for_update().get(pk=self.office_hour_id)
                if office_hour.status == OfficeHour.Status.CANCELED:
                    raise ValidationError("Cannot create or reactivate a reservation for a canceled office hour.")
            super().save(*args, **kwargs)
from django.db import models

# Create your models here.
