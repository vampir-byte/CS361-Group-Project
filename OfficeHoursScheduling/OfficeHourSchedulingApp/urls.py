from django.urls import path

from . import views
from .views import (
    CourseCreateView,
    CourseDeleteView,
    CourseDetailView,
    CourseListView,
    OfficeHourCancelView,
    OfficeHoursView,
)

app_name = "courses"
urlpatterns = [
    path("", CourseListView.as_view(), name="list"),
    path("create/", CourseCreateView.as_view(), name="create"),
    path("staff/create/", views.create_staff_account, name="create_staff_account"),
    path("staff/<int:user_id>/delete/", views.delete_account, name="delete_account"),
    path("office-hours/", OfficeHoursView.as_view(), name="office_hours"),
    path("office-hours/<int:pk>/cancel/", OfficeHourCancelView.as_view(), name="cancel_office_hour"),
    path("<int:pk>/", CourseDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", CourseDeleteView.as_view(), name="delete"),
]
