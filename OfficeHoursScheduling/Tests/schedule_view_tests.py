# PB-08: View office-hour schedules by course or staff member (design B03 P03, B10 P10)
from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone




class ScheduleTestCase(TestCase):
    password = "A-strong-test-password-42!"

    def setUp(self):
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_superuser(
            username="administrator",
            email="admin@example.test",
            password=self.password,
        )
        self.client.force_login(self.admin)

        self.instructor_group, _ = Group.objects.get_or_create(name="Instructor")
        self.ta_group, _ = Group.objects.get_or_create(name="TA")
        self.student_group, _ = Group.objects.get_or_create(name="Student")

        self.instructor = self.user_model.objects.create_user(
            username="ada-staff",
            first_name="John Compsci",
            email="ada@example.test",
            password=self.password,
            is_staff=True,
        )
        self.instructor.groups.add(self.instructor_group)
        self.ta = self.user_model.objects.create_user(
            username="grace-staff",
            first_name="Greg Compsci",
            email="grace@example.test",
            password=self.password,
            is_staff=True,
        )
        self.ta.groups.add(self.ta_group)
        self.student = self.user_model.objects.create_user(
            username="target-student",
            first_name="Charlie Compsci",
            email="charlie@example.test",
            password=self.password,
        )
        self.student.groups.add(self.student_group)

        self.course = Course.objects.create(number="CS361", name="Software Engineering")
        self.other_course = Course.objects.create(
            number="CS337", name="System Programming"
        )
        self.section = Section.objects.create(
            course=self.course, number="801", kind="LEC"
        )
        self.other_section = Section.objects.create(
            course=self.other_course, number="801", kind="LAB"
        )

    def course_url(self, course_id=None):
        course_id = course_id or self.course.pk
        try:
            return reverse("course_schedule", args=[course_id])
        except NoReverseMatch:
            return f"/courses/{course_id}/"

    def assignments_url(self, course_id=None):
        course_id = course_id or self.course.pk
        try:
            return reverse("staff_assignments", args=[course_id])
        except NoReverseMatch:
            return f"/courses/{course_id}/assignments/"

    def staff_url(self, staff_id):
        try:
            return reverse("staff_schedule", args=[staff_id])
        except NoReverseMatch:
            return f"/staff/{staff_id}/schedule/"

    def assign(self, staff, section):
        return StaffAssignment.objects.create(staff=staff, section=section)

    def meeting(self, section, weekday=0, location="Room 101"):
        today = timezone.localdate()
        return SectionMeeting.objects.create(
            section=section,
            weekday=weekday,
            start_time=time(10, 0),
            end_time=time(11, 0),
            valid_from=today,
            valid_until=today + timedelta(days=90),
            location=location,
        )

    def office_hour(self, staff, course, *, days_out=3, status="APPR", hour=14):
        day = timezone.localdate() + timedelta(days=days_out)
        start = timezone.make_aware(datetime.combine(day, time(hour, 0)))
        return OfficeHour.objects.create(
            staff=staff,
            course=course,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            status=status,
            meeting_url="https://example.test/meet",
        )

    def date_param(self, days_from_today):
        return (timezone.localdate() + timedelta(days=days_from_today)).isoformat()

    def assert_redirects_to_login(self, url):
        self.client.logout()

        response = self.client.get(url)

        self.assertRedirects(
            response, f"/login/?next={url}", fetch_redirect_response=False
        )


class CourseScheduleTests(ScheduleTestCase):
    def test_administrator_sees_sections_meeting_times_staff_and_approved_hours(self):
        self.assign(self.instructor, self.section)
        self.meeting(self.section, weekday=0, location="Room 101")
        self.office_hour(self.instructor, self.course, status="APPR")

        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["course"]["number"], "CS361")
        section = response.context["sections"][0]
        self.assertEqual(section["number"], "801")
        self.assertEqual(section["staff_names"], ["John Compsci"])
        self.assertEqual(len(section["meetings"]), 1)
        self.assertContains(response, "Room 101")
        self.assertEqual(len(response.context["hours"]), 1)

    def test_schedule_only_shows_data_from_the_selected_course(self):
        self.assign(self.instructor, self.section)
        self.assign(self.ta, self.other_section)
        self.office_hour(self.ta, self.other_course, status="APPR")

        response = self.client.get(self.course_url())

        self.assertNotContains(response, "Greg Compsci")
        self.assertEqual(len(response.context["hours"]), 0)

    def test_administrator_can_open_every_course_schedule(self):
        for course in (self.course, self.other_course):
            with self.subTest(course=course.number):
                response = self.client.get(self.course_url(course.pk))
                self.assertEqual(response.status_code, 200)

    def test_student_sees_approved_hours_but_not_pending_or_rejected_hours(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.assign(self.instructor, self.section)
        self.office_hour(
            self.instructor, self.course, days_out=2, status="APPR", hour=9
        )
        self.office_hour(
            self.instructor, self.course, days_out=3, status="PEND", hour=10
        )
        self.office_hour(
            self.instructor, self.course, days_out=4, status="REJ", hour=11
        )
        self.client.force_login(self.student)

        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["hours"]), 1)

    def test_approved_hours_include_whether_each_slot_is_available(self):
        self.assign(self.instructor, self.section)
        hour = self.office_hour(self.instructor, self.course, status="APPR")
        TimeSlot.objects.create(
            office_hour=hour,
            starts_at=hour.starts_at,
            ends_at=hour.starts_at + timedelta(minutes=15),
            is_open=True,
        )
        TimeSlot.objects.create(
            office_hour=hour,
            starts_at=hour.starts_at + timedelta(minutes=15),
            ends_at=hour.starts_at + timedelta(minutes=30),
            is_open=False,
        )

        response = self.client.get(self.course_url())

        slots = response.context["hours"][0]["slots"]
        self.assertEqual([slot["available"] for slot in slots], [True, False])

    def test_assigned_staff_and_enrolled_student_can_view_their_course(self):
        Enrollment.objects.create(student=self.student, course=self.course)
        self.assign(self.instructor, self.section)
        self.assign(self.ta, self.section)
        users = [
            ("instructor", self.instructor),
            ("ta", self.ta),
            ("student", self.student),
        ]

        for role, user in users:
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.course_url())
                self.assertEqual(response.status_code, 200)

    def test_users_unrelated_to_the_course_cannot_view_its_schedule(self):
        other_instructor = self.user_model.objects.create_user(
            username="alan-staff",
            first_name="Alan Turing",
            email="alan@example.test",
            password=self.password,
            is_staff=True,
        )
        other_instructor.groups.add(self.instructor_group)
        self.assign(other_instructor, self.other_section)
        Enrollment.objects.create(student=self.student, course=self.other_course)
        users = [
            ("instructor", other_instructor),
            ("ta", self.ta),
            ("student", self.student),
        ]

        for role, user in users:
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.course_url())
                self.assertEqual(response.status_code, 403)

    def test_nonexistent_course_returns_not_found(self):
        response = self.client.get(self.course_url(999999))

        self.assertEqual(response.status_code, 404)

    def test_anonymous_user_is_redirected_to_login(self):
        self.assert_redirects_to_login(self.course_url())

    def test_course_without_sections_or_hours_shows_empty_state(self):
        response = self.client.get(self.course_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["sections"]), 0)
        self.assertEqual(len(response.context["hours"]), 0)
        text = response.content.decode(errors="replace").lower()
        self.assertTrue(
            any(
                term in text
                for term in ("no sections", "no office hours", "nothing scheduled")
            )
        )

    def test_staff_filter_limits_office_hours_to_one_staff_member(self):
        self.assign(self.instructor, self.section)
        self.assign(self.ta, self.section)
        self.office_hour(self.instructor, self.course, days_out=2, hour=9)
        self.office_hour(self.ta, self.course, days_out=3, hour=10)

        response = self.client.get(self.course_url(), {"staff_id": self.ta.pk})

        self.assertEqual(response.status_code, 200)
        staff_names = {hour["staff_name"] for hour in response.context["hours"]}
        self.assertEqual(staff_names, {"Greg Compsci"})

    def test_staff_filter_options_only_include_staff_assigned_to_the_course(self):
        self.assign(self.instructor, self.section)
        self.assign(self.ta, self.other_section)

        response = self.client.get(self.course_url())

        option_names = [
            staff["full_name"] for staff in response.context["staff_options"]
        ]
        self.assertEqual(option_names, ["John Compsci"])

    def test_date_filter_limits_displayed_office_hours(self):
        self.assign(self.instructor, self.section)
        self.office_hour(self.instructor, self.course, days_out=2, hour=9)
        self.office_hour(self.instructor, self.course, days_out=20, hour=9)

        response = self.client.get(
            self.course_url(),
            {"from_date": self.date_param(0), "to_date": self.date_param(7)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["hours"]), 1)

    def test_invalid_filters_stay_on_page_and_report_errors(self):
        self.assign(self.instructor, self.section)
        bad_filters = [
            {"from_date": self.date_param(10), "to_date": self.date_param(1)},
            {"from_date": "not-a-date"},
            {"staff_id": "abc"},
            {"staff_id": self.ta.pk},
        ]

        for params in bad_filters:
            with self.subTest(params=params):
                response = self.client.get(self.course_url(), params)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form_errors"])

    def test_administrator_sees_assign_staff_link_but_students_do_not(self):
        Enrollment.objects.create(student=self.student, course=self.course)

        admin_response = self.client.get(self.course_url())
        self.assertContains(admin_response, self.assignments_url())

        self.client.force_login(self.student)
        student_response = self.client.get(self.course_url())
        self.assertNotContains(student_response, self.assignments_url())


class StaffScheduleTests(ScheduleTestCase):
    def test_administrator_sees_staff_section_times_across_all_courses(self):
        self.assign(self.instructor, self.section)
        self.assign(self.instructor, self.other_section)
        self.meeting(self.section, weekday=0, location="Room 101")
        self.meeting(self.other_section, weekday=2, location="Lab 7")

        response = self.client.get(self.staff_url(self.instructor.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["staff"]["full_name"], "John Compsci")
        self.assertEqual(len(response.context["meetings"]), 2)
        self.assertContains(response, "Room 101")
        self.assertContains(response, "Lab 7")

    def test_office_hours_of_every_status_are_listed_with_their_status(self):
        self.assign(self.instructor, self.section)
        self.office_hour(
            self.instructor, self.course, days_out=2, status="APPR", hour=9
        )
        self.office_hour(
            self.instructor, self.course, days_out=3, status="PEND", hour=10
        )
        self.office_hour(
            self.instructor, self.course, days_out=4, status="REJ", hour=11
        )

        response = self.client.get(self.staff_url(self.instructor.pk))

        self.assertEqual(len(response.context["hours"]), 3)
        statuses = " ".join(
            hour["status"].lower() for hour in response.context["hours"]
        )
        for label in ("approv", "pend", "rej"):
            self.assertIn(label, statuses)

    def test_only_the_selected_staff_members_data_is_shown(self):
        self.assign(self.instructor, self.section)
        self.assign(self.ta, self.section)
        self.office_hour(self.ta, self.course)

        response = self.client.get(self.staff_url(self.instructor.pk))

        self.assertEqual(len(response.context["hours"]), 0)
        self.assertNotContains(response, "Greg Compsci")

    def test_office_hours_are_sorted_by_course_then_start_time(self):
        self.assign(self.instructor, self.section)
        self.assign(self.instructor, self.other_section)
        self.office_hour(self.instructor, self.other_course, days_out=2, hour=9)
        self.office_hour(self.instructor, self.course, days_out=5, hour=9)
        self.office_hour(self.instructor, self.course, days_out=3, hour=9)

        response = self.client.get(self.staff_url(self.instructor.pk))

        keys = [(hour["course"], hour["start"]) for hour in response.context["hours"]]
        self.assertEqual(keys, sorted(keys))

    def test_staff_member_without_sections_or_hours_shows_empty_state(self):
        response = self.client.get(self.staff_url(self.ta.pk))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["meetings"]), 0)
        self.assertEqual(len(response.context["hours"]), 0)
        text = response.content.decode(errors="replace").lower()
        self.assertTrue(
            any(
                term in text
                for term in ("no sections", "no office hours", "nothing scheduled")
            )
        )

    def test_date_range_filter_limits_displayed_office_hours(self):
        self.assign(self.instructor, self.section)
        self.office_hour(self.instructor, self.course, days_out=2, hour=9)
        self.office_hour(self.instructor, self.course, days_out=20, hour=9)

        response = self.client.get(
            self.staff_url(self.instructor.pk),
            {"from_date": self.date_param(0), "to_date": self.date_param(7)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["hours"]), 1)

    def test_invalid_date_range_stays_on_page_and_reports_errors(self):
        bad_ranges = [
            {"from_date": self.date_param(10), "to_date": self.date_param(1)},
            {"from_date": "not-a-date", "to_date": self.date_param(1)},
        ]

        for params in bad_ranges:
            with self.subTest(params=params):
                response = self.client.get(self.staff_url(self.instructor.pk), params)

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form_errors"])

    def test_unknown_staff_member_returns_not_found(self):
        response = self.client.get(self.staff_url(999999))

        self.assertEqual(response.status_code, 404)

    def test_non_staff_account_cannot_be_viewed_as_a_staff_schedule(self):
        response = self.client.get(self.staff_url(self.student.pk))

        self.assertIn(response.status_code, (403, 404))

    def test_unauthorized_users_cannot_view_a_staff_schedule(self):
        non_admins = [
            ("instructor", self.instructor),
            ("ta", self.ta),
            ("student", self.student),
        ]

        for role, user in non_admins:
            with self.subTest(role=role):
                self.client.force_login(user)
                response = self.client.get(self.staff_url(self.instructor.pk))
                self.assertEqual(response.status_code, 403)

    def test_anonymous_user_is_redirected_to_login(self):
        self.assert_redirects_to_login(self.staff_url(self.instructor.pk))