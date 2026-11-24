# Office Hours Scheduling

## Run locally

Use Python 3.12 or newer. From the repository root:

```sh
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
cd OfficeHoursScheduling
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/courses/` and log in with the superuser's username
and password. Django's standard login is provided at `/login/` until the team's
account/login stories are implemented. `/admin/` remains available for account
management.

Set `DJANGO_SECRET_KEY` to a private, stable value for a shared deployment.
Development generates a temporary key when it is unset, so sessions reset on
server restart. The repository's previous hard-coded development key has been
removed from settings.

## Accounts and roles

Migrations create the `Administrator`, `Instructor`, `TA`, and `Student` groups.
In Django admin, create the existing staff accounts and assign the relevant
group before creating a course. A superuser or an active user in
`Administrator` can manage courses. `is_staff` alone does not grant this access:
instructors and TAs may be staff without being administrators. An account must
be active and in the exact `Instructor` or `TA` group to fill that position.
No custom user model or duplicate account table is introduced.

## Course workflows

- `/courses/`: list and search by course number or name.
- `/courses/create/`: required course number (20 characters maximum), course
  name (120), one instructor, two distinct TAs, and at least one availability
  range per person. Each range has a required location (120), date, start, and
  end. End must be later than start on the same date. Add multiple ranges with
  the button; check Delete to omit a range. At most 50 ranges per person are
  accepted. Course numbers are trimmed and unique with the database's default
  case-sensitive comparison; names are trimmed and cannot be whitespace only.
- `/courses/<id>/`: staff and availability, with a Delete course action.
- `/courses/<id>/delete/`: confirmation with the number/name and a permanent
  deletion warning. GET never deletes; POST requires `confirm=yes` and CSRF.
  Cancel returns to the detail page. Creation Cancel returns to the course list.
- `/courses/office-hours/`: upcoming office hours for the signed-in user's
  assigned staff or enrolled student courses. Staff can cancel their own
  upcoming hours; enrolled students see canceled status and reservations are
  retained as canceled.

Creation and deletion are transactional. Validation and database failures keep
the submitted form available and roll back partial changes. Creation rechecks
staff accounts/roles before saving. Course deletion cascades through
`StaffAssignment -> Availability` and `StaffAssignment -> OfficeHour ->
Reservation`, and removes the course's `Enrollment` records. All account rows
and other courses' records remain. `Enrollment` makes new courses available
for the team's future student-assignment workflow. Office-hour/reservation
models support course deletion and office-hour cancellation; booking and
reservation-creation UI are outside this story.

The repository's `main` branch contained a project configured for the missing
`OfficeHourSchedulingApp`; this implementation supplies that app. The existing
`Tests/` files are draft stories for other features and include undefined
fixtures (`OfficeHourTestBase`, `Course`) and routes that are not implemented.
They are preserved. The executable tests for these course stories live in the
new app and run in GitHub Actions.

## Verify

From `OfficeHoursScheduling/`:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test OfficeHourSchedulingApp --verbosity 2
```

The tests cover successful creation, duplicate/blank/overlength information,
staff counts/roles/distinctness, availability validation and multiple ranges,
permissions, CSRF, cancellations, missing courses, account/other-course
preservation, and rollback when a write or cascade fails.
