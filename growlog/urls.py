from django.urls import path
from . import views

app_name = "growlog"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("quick/", views.quick_entry, name="quick"),
    path("cultivo/<int:pk>/timeline/", views.timeline, name="timeline"),
    path("tarea/<int:pk>/completar/", views.tarea_completar, name="tarea_completar"),
]
