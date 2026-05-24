from django.urls import path

from dispatch.views import weekly_report

urlpatterns = [
    path("reports/weekly/", weekly_report, name="weekly-report"),
]