from django.shortcuts import render

from dispatch.services.report_service import build_weekly_report


def weekly_report(request):
    report = build_weekly_report()
    return render(request, "dispatch/weekly_report.html", {"report": report})