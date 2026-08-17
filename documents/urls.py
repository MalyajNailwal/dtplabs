from django.urls import path
from . import views

urlpatterns = [
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document-upload'),
    path('documents/', views.DocumentListView.as_view(), name='document-list'),
    path('documents/<uuid:id>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('documents/<uuid:id>/status/', views.document_status_view, name='document-status'),
    path('models/free/', views.free_models_view, name='free-models'),
]
