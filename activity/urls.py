"""
URL configuration for Activity module.

REST endpoints for Excel export and other utilities.
"""
from django.urls import path

from activity.views import export_ptba

urlpatterns = [
    path('export/<uuid:ptba_id>/', export_ptba, name='activity_export_ptba'),
]
