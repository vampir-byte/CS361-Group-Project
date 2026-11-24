from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from OfficeHourSchedulingApp.models import (
    Course,
    Enrollment,
    OfficeHour,
    Reservation,
    StaffAssignment,
)


class OfficeHourCancellationTests(TestCase):
    def setUp(self):
        users = get_user_model().objects
        self.staff = users.create_user(email="staff@example.test")
        self.other_staff = users.create_user(email="other@example.test")
        self.student = users.create_user(email="student@example.test")
        self.other_student = users.create_user(email="other-student@example.test")
        self.staff.groups.add(Group.objects.get_or_create(name="TA")[0])
        self.other_staff.groups.add(Group.objects.get_or_create(name="Instructor")[0])
        self.student.groups.add(Group.objects.get_or_create(name="Student")[0])

        self.course = Course.objects.create(course_number="CS361", course_name="Software Engineering")
        self.assignment = StaffAssignment.objects.create(
            course=self.course, user=self.staff, role=StaffAssignment.Role.TA
        )
        self.other_assignment = StaffAssignment.objects.create(
            course=self.course, user=self.other_staff, role=StaffAssignment.Role.INSTRUCTOR
        )
        self.office_hour = self.make_office_hour(self.assignment)
        self.reservation = Reservation.objects.create(
            office_hour=self.office_hour, student=self.student
        )
        Enrollment.objects.create(course=self.course, student=self.student)
        self.url = reverse("courses:cancel_office_hour", args=[self.office_hour.pk])

    def make_office_hour(self, assignment, day=None):
        return OfficeHour.objects.create(
            assignment=assignment,
            date=day or timezone.localdate() + timedelta(days=1),
            start_time=time(13),
            end_time=time(14),
            location="Room 101",
        )

    def test_staff_cancellation_marks_hour_and_reservations_canceled(self):
        self.client.force_login(self.staff)

        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("courses:office_hours"))
        self.office_hour.refresh_from_db()
        self.reservation.refresh_from_db()
        self.assertEqual(self.office_hour.status, OfficeHour.Status.CANCELED)
        self.assertEqual(self.reservation.status, Reservation.Status.CANCELED)

    def test_canceled_office_hour_cannot_accept_new_reservations(self):
        self.office_hour.status = OfficeHour.Status.CANCELED
        self.office_hour.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            Reservation.objects.create(
                office_hour=self.office_hour, student=self.other_student
            )

    def test_student_sees_canceled_status_for_enrolled_course(self):
        self.office_hour.status = OfficeHour.Status.CANCELED
        self.office_hour.save(update_fields=["status"])
        self.client.force_login(self.student)

        response = self.client.get(reverse("courses:office_hours"))

        self.assertContains(response, "Canceled")
        self.assertContains(response, "CS361")

    def test_student_cannot_cancel_office_hour(self):
        self.client.force_login(self.student)

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        self.office_hour.refresh_from_db()
        self.assertEqual(self.office_hour.status, OfficeHour.Status.SCHEDULED)

    def test_staff_cannot_cancel_another_staff_members_hour(self):
        other_hour = self.make_office_hour(self.other_assignment)
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("courses:cancel_office_hour", args=[other_hour.pk])
        )

        self.assertEqual(response.status_code, 404)
        other_hour.refresh_from_db()
        self.assertEqual(other_hour.status, OfficeHour.Status.SCHEDULED)

    def test_past_office_hour_cannot_be_canceled(self):
        past_hour = self.make_office_hour(
            self.assignment, day=timezone.localdate() - timedelta(days=1)
        )
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("courses:cancel_office_hour", args=[past_hour.pk])
        )

        self.assertRedirects(response, reverse("courses:office_hours"))
        past_hour.refresh_from_db()
        self.assertEqual(past_hour.status, OfficeHour.Status.SCHEDULED)
