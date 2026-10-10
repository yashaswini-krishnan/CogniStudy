from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_view, name='upload'),
    path('quiz/<int:pk>/', views.quiz_view, name='quiz'),
    path('quiz/result/<int:attempt_id>/', views.quiz_result_view, name='quiz_result'),
    path('material/<int:pk>/delete/', views.delete_material_view, name='delete_material'),
]
