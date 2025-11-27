from django.urls import path
from . import views

urlpatterns = [
    # Asosiy sahifalar
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Admin sahifalari
    path('committee/dashboard/', views.dashboard, name='committee_dashboard'),
    path('dashboard-stats/', views.dashboard_stats, name='dashboard_stats'),
    path('companies/', views.companies, name='companies'),
    path('penalties/', views.penalties, name='penalties'),
    path('create-penalty/', views.create_penalty, name='create_penalty'),
    path('report-data/', views.report_data, name='report_data'),
    path('download-report/', views.download_report, name='download_report'),
    
    # Korxona paneli asosiy sahifasi
    path('company/dashboard/', views.company_dashboard, name='company_dashboard'),
    
    # Korxona jarimalari (AJAX)
    path('company/penalties/', views.company_penalties, name='company_penalties'),
    
    # Jarimaga javob berish
    path('company/penalties/<int:penalty_id>/response/', views.submit_penalty_response, name='submit_penalty_response'),
    
    # Sensor ma'lumotlari
    path('company/sensor-data/', views.company_sensor_data, name='company_sensor_data'),
    
    # Sensor ma'lumotlarini yangilash
    path('company/update-sensor/', views.update_sensor_data, name='update_sensor_data'),
    
    # Ogohlantirishlar
    path('company/notifications/', views.company_notifications, name='company_notifications'),
    
    # Hisobotlarni yuklab olish
    path('company/reports/<str:report_type>/', views.download_company_report, name='download_company_report'),

]