from django.urls import path
from . import views

urlpatterns = [
    # Public landing page
    path('', views.landing_view, name='landing'),

    # Authenticated application
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('upload/', views.upload_view, name='upload'),
    path('quiz/<int:pk>/', views.quiz_view, name='quiz'),
    path('quiz/result/<int:attempt_id>/', views.quiz_result_view, name='quiz_result'),
    path('material/<int:pk>/', views.material_detail_view, name='material_detail'),
    path('material/<int:pk>/edit/', views.edit_material_view, name='edit_material'),
    path('material/<int:pk>/delete/', views.delete_material_view, name='delete_material'),

    # Auth
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
