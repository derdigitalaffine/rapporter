from django.urls import path
from . import views

urlpatterns = [path("statistics/", views.overview), path("statistics/<str:domain>/", views.detail)]
