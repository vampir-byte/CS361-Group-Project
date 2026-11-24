# PB-07: Assign staff members (Instructor / TA) to course sections (design B09, P09)
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone




class AssignStaffToSectionTests(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_superuser(
            email="admin@example.test",
            password=self.password,
        )
        self.client.force_login(self.admin)

        self.instructor_group, _ = Group.objects.get_or_create(name="Instructor")
        self.ta_group, _ = Group.objects.get_or_create(name="TA")
        self.student_group, _ = Group.objects.get_or_create(name="Student")

        self.instructor = self.user_model.objects.create_user(
            first_name="Ada Lovelace",
            email="ada@example.test",
            password=self.password,
            is_staff=True,
        )
        self.instructor.groups.add(self.instructor_group)
        self.ta = self.user_model.objects.create_user(
            first_name="Grace Hopper",
            email="grace@example.test",
            password=self.password,
            is_staff=True,
        )
        self.ta.groups.add(self.ta_group)
        self.student = self.user_model.objects.create_user(
            first_name="Charles Babbage",
            email="charles@example.test",
            password=self.password,
        )
        self.student.groups.add(self.student_group)

        self.course = Course.objects.create(number="CS361", name="Software Engineering")
        self.other_course = Course.objects.create(
            number="CS337", name="Data Structures"
        )
        self.section = Section.objects.create(
            course=self.course, number="801", kind="LEC"
        )
        self.section_b = Section.objects.create(
            course=self.course, number="802", kind="LAB"
        )
        self.other_section = Section.objects.create(
            course=self.other_course, number="801", kind="LEC"
        )

    def assignments_url(self, course_id=None):
        course_id = course_id or self.course.pk
        try:
            return reverse("staff_assignments", args=[course_id])
        except NoReverseMatch:
            return f"/courses/{course_id}/assignments/"

    def schedule_url(self, course_id=None):
        course_id = course_id or self.course.pk
        try:
            return reverse("course_schedule", args=[course_id])
        except NoReverseMatch:
            return f"/courses/{course_id}/"

    def post_assignment(self, section_id, staff_id, *, course_id=None):
        return self.client.post(
            self.assignments_url(course_id),
            {"action": "ADD", "section_id": section_id, "staff_id": staff_id},
            follow=True,
        )

    def post_removal(self, assignment_id, *, course_id=None):
        return self.client.post(
            self.assignments_url(course_id),
            {"action": "REMOVE", "assignment_id": assignment_id},
            follow=True,
        )

    def meeting(self, section, weekday, start, end):
        today = timezone.localdate()
        return SectionMeeting.objects.create(
            section=section,
            weekday=weekday,
            start_time=start,
            end_time=end,
            valid_from=today,
            valid_until=today + timedelta(days=90),
            location="Room 101",
        )

    def future_office_hour(self, staff, course):
        start = timezone.now() + timedelta(days=3)
        return OfficeHour.objects.create(
            staff=staff,
            course=course,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status="APPR",
        )

    def next_weekday(self, weekday):
        today = timezone.localdate()
        return today + timedelta(days=((weekday - today.weekday()) % 7) or 7)

    def assert_rejected(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form_errors"])

    def test_assignment_page_lists_course_sections_and_only_instructor_and_ta_choices(
        self,
    ):
        response = self.client.get(self.assignments_url())

        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [section["number"] for section in response.context["sections"]],
            ["801", "802"],
        )
        staff_names = [staff["full_name"] for staff in response.context["staff"]]
        self.assertIn("Ada Lovelace", staff_names)
        self.assertIn("Grace Hopper", staff_names)
        self.assertNotIn("Charles Babbage", staff_names)

    def test_successfully_assign_instructor_and_ta_to_a_section(self):
        cases = [
            ("instructor", self.instructor),
            ("ta", self.ta),
        ]

        for role, staff in cases:
            with self.subTest(role=role):
                response = self.post_assignment(self.section.pk, staff.pk)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(
                    StaffAssignment.objects.filter(
                        staff=staff, section=self.section
                    ).exists()
                )

    def test_new_assignment_is_displayed_on_assignment_page_and_course_schedule(self):
        self.post_assignment(self.section.pk, self.instructor.pk)

        for url in (self.assignments_url(), self.schedule_url()):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "Ada Lovelace")

    def test_duplicate_assignment_is_not_created_and_reports_error(self):
        StaffAssignment.objects.create(staff=self.instructor, section=self.section)

        response = self.post_assignment(self.section.pk, self.instructor.pk)

        self.assertEqual(StaffAssignment.objects.count(), 1)
        self.assert_rejected(response)

    def test_student_cannot_be_assigned_and_reports_error(self):
        response = self.post_assignment(self.section.pk, self.student.pk)

        self.assertEqual(StaffAssignment.objects.count(), 0)
        self.assert_rejected(response)

    def test_missing_or_unknown_section_or_staff_does_not_create_assignment(self):
        cases = [
            (self.section.pk, ""),
            (self.section.pk, 999999),
            ("", self.instructor.pk),
            (999999, self.instructor.pk),
        ]

        for section_id, staff_id in cases:
            with self.subTest(section_id=section_id, staff_id=staff_id):
                response = self.post_assignment(section_id, staff_id)

                self.assertEqual(StaffAssignment.objects.count(), 0)
                self.assert_rejected(response)

    def test_section_from_a_different_course_is_rejected(self):
        response = self.post_assignment(self.other_section.pk, self.instructor.pk)

        self.assertEqual(StaffAssignment.objects.count(), 0)
        self.assert_rejected(response)

    def test_unknown_or_missing_action_does_not_change_assignments(self):
        existing = StaffAssignment.objects.create(staff=self.ta, section=self.section)

        for action in ("", "DELETE", "add", "UPDATE"):
            with self.subTest(action=action):
                self.client.post(
                    self.assignments_url(),
                    {
                        "action": action,
                        "section_id": self.section_b.pk,
                        "staff_id": self.instructor.pk,
                        "assignment_id": existing.pk,
                    },
                    follow=True,
                )

                self.assertEqual(StaffAssignment.objects.count(), 1)
                self.assertTrue(StaffAssignment.objects.filter(pk=existing.pk).exists())

    def test_overlapping_section_meeting_times_are_rejected(self):
        self.meeting(self.section, 0, time(10, 0), time(11, 0))
        self.meeting(self.section_b, 0, time(10, 30), time(11, 30))
        StaffAssignment.objects.create(staff=self.instructor, section=self.section)

        response = self.post_assignment(self.section_b.pk, self.instructor.pk)

        self.assertEqual(
            StaffAssignment.objects.filter(staff=self.instructor).count(), 1
        )
        self.assert_rejected(response)

    def test_non_overlapping_section_meeting_times_are_allowed(self):
        self.meeting(self.section, 0, time(10, 0), time(11, 0))
        self.meeting(self.section_b, 0, time(13, 0), time(14, 0))
        StaffAssignment.objects.create(staff=self.instructor, section=self.section)

        self.post_assignment(self.section_b.pk, self.instructor.pk)

        self.assertEqual(
            StaffAssignment.objects.filter(staff=self.instructor).count(), 2
        )

    def test_section_time_overlapping_existing_office_hours_is_rejected(self):
        monday = self.next_weekday(0)
        OfficeHour.objects.create(
            staff=self.instructor,
            course=self.other_course,
            starts_at=timezone.make_aware(datetime.combine(monday, time(10, 15))),
            ends_at=timezone.make_aware(datetime.combine(monday, time(10, 45))),
            status="APPR",
        )
        self.meeting(self.section, 0, time(10, 0), time(11, 0))

        response = self.post_assignment(self.section.pk, self.instructor.pk)

        self.assertEqual(StaffAssignment.objects.count(), 0)
        self.assert_rejected(response)

    def test_successfully_remove_assignment_and_it_disappears_from_both_views(self):
        existing = StaffAssignment.objects.create(
            staff=self.instructor, section=self.section
        )

        response = self.post_removal(existing.pk)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(StaffAssignment.objects.filter(pk=existing.pk).exists())
        for url in (self.assignments_url(), self.schedule_url()):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "Ada Lovelace")

    def test_cannot_remove_assignment_belonging_to_another_course(self):
        existing = StaffAssignment.objects.create(
            staff=self.instructor, section=self.other_section
        )

        response = self.post_removal(existing.pk)

        self.assertTrue(StaffAssignment.objects.filter(pk=existing.pk).exists())
        self.assert_rejected(response)

    def test_removing_unknown_assignment_does_not_change_anything(self):
        existing = StaffAssignment.objects.create(
            staff=self.instructor, section=self.section
        )

        response = self.post_removal(999999)

        self.assertTrue(StaffAssignment.objects.filter(pk=existing.pk).exists())
        self.assert_rejected(response)

    def test_cannot_remove_last_course_assignment_while_future_office_hours_exist(
        self,
    ):
        existing = StaffAssignment.objects.create(staff=self.ta, section=self.section)
        self.future_office_hour(self.ta, self.course)

        response = self.post_removal(existing.pk)

        self.assertTrue(StaffAssignment.objects.filter(pk=existing.pk).exists())
        self.assert_rejected(response)

    def test_can_remove_assignment_when_staff_keeps_another_assignment_in_course(self):
        existing = StaffAssignment.objects.create(staff=self.ta, section=self.section)
        StaffAssignment.objects.create(staff=self.ta, section=self.section_b)
        self.future_office_hour(self.ta, self.course)

        self.post_removal(existing.pk)

        self.assertFalse(StaffAssignment.objects.filter(pk=existing.pk).exists())

    def test_can_remove_last_assignment_when_no_future_office_hours_exist(self):
        existing = StaffAssignment.objects.create(staff=self.ta, section=self.section)

        self.post_removal(existing.pk)

        self.assertFalse(StaffAssignment.objects.filter(pk=existing.pk).exists())

    def test_unauthorized_users_cannot_access_or_change_assignments(self):
        existing = StaffAssignment.objects.create(staff=self.ta, section=self.section)
        non_admins = [
            ("instructor", self.instructor),
            ("ta", self.ta),
            ("student", self.student),
        ]

        for role, user in non_admins:
            with self.subTest(role=role):
                self.client.force_login(user)

                get_response = self.client.get(self.assignments_url())
                self.assertEqual(get_response.status_code, 403)

                add_response = self.client.post(
                    self.assignments_url(),
                    {
                        "action": "ADD",
                        "section_id": self.section_b.pk,
                        "staff_id": user.pk,
                    },
                )
                self.assertEqual(add_response.status_code, 403)

                remove_response = self.client.post(
                    self.assignments_url(),
                    {"action": "REMOVE", "assignment_id": existing.pk},
                )
                self.assertEqual(remove_response.status_code, 403)

                self.assertEqual(StaffAssignment.objects.count(), 1)

    def test_anonymous_user_is_redirected_to_login(self):
        self.client.logout()
        url = self.assignments_url()

        response = self.client.get(url)

        self.assertRedirects(
            response, f"/login/?next={url}", fetch_redirect_response=False
        )

    def test_post_without_csrf_token_is_rejected_and_creates_nothing(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)

        response = csrf_client.post(
            self.assignments_url(),
            {
                "action": "ADD",
                "section_id": self.section.pk,
                "staff_id": self.instructor.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(StaffAssignment.objects.count(), 0)

    def test_assignment_page_for_nonexistent_course_returns_not_found(self):
        response = self.client.get(self.assignments_url(course_id=999999))

        self.assertEqual(response.status_code, 404)