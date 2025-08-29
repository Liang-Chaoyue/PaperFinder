from django.urls import path
from . import views

app_name = "paper_finder"

urlpatterns = [
    path("", views.search_page, name="search"),
    path("jobs/", views.job_history, name="job_history"),                 # ✅ 新增
    path("jobs/<str:job_id>/", views.job_status, name="job_status"),
    path("papers/", views.paper_list, name="paper_list"),
    path("papers/<int:pk>/mark/", views.mark_paper, name="mark_paper"),
    path("export/", views.export_csv, name="export_csv"),
    path("export.csv", views.export_job_csv, name="export_csv"),
]