from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import *

# Custom User Admin
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'user_type', 'employee_id', 'stir_number', 'company', 'is_active', 'is_staff')
    list_filter = ('user_type', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('username', 'email', 'employee_id', 'stir_number', 'company__name')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Qo`shimcha Ma\'lumotlar', {
            'fields': ('user_type', 'employee_id', 'stir_number', 'company', 'phone_number')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Qo`shimcha M\'alumotlar', {
            'fields': ('user_type', 'employee_id', 'stir_number', 'company', 'phone_number')
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')

# Region Admin
class RegionAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_count')
    search_fields = ('name',)
    
    def company_count(self, obj):
        return obj.company_set.count()
    company_count.short_description = 'Korxonalar soni'

# Industry Type Admin
class IndustryTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_count')
    search_fields = ('name',)
    
    def company_count(self, obj):
        return obj.company_set.count()
    company_count.short_description = 'Korxonalar soni'

# Company Admin
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'stir_number', 'region', 'industry_type', 'current_gas_amount', 
                   'max_allowed_gas', 'status_badge', 'sensor_active', 'created_at')
    list_filter = ('status', 'sensor_active', 'region', 'industry_type', 'created_at')
    search_fields = ('name', 'stir_number', 'region__name')
    readonly_fields = ('created_at', 'updated_at', 'status')
    list_editable = ('sensor_active',)
    list_per_page = 25
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('name', 'stir_number', 'region', 'industry_type')
        }),
        ('Lokatsiya', {
            'fields': ('latitude', 'longitude')
        }),
        ('Gaz Monitoring', {
            'fields': ('max_allowed_gas', 'current_gas_amount', 'status', 'sensor_active')
        }),
        ('Qo`shimcha', {
            'fields': ('created_at', 'updated_at')
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'good': 'green',
            'moderate': 'orange',
            'bad': 'red'
        }
        status_text = {
            'good': 'Yaxshi',
            'moderate': 'O\'rtacha',
            'bad': 'Xavfli'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            colors.get(obj.status, 'gray'),
            status_text.get(obj.status, 'Noma\'lum')
        )
    status_badge.short_description = 'Holat'
    status_badge.admin_order_field = 'status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('region', 'industry_type')
    
    actions = ['activate_sensors', 'deactivate_sensors', 'calculate_status']
    
    def activate_sensors(self, request, queryset):
        updated = queryset.update(sensor_active=True)
        self.message_user(request, f'{updated} ta korxonaning sensori faollashtirildi')
    activate_sensors.short_description = "Tanlangan korxonalar sensorlarini faollashtirish"
    
    def deactivate_sensors(self, request, queryset):
        updated = queryset.update(sensor_active=False)
        self.message_user(request, f'{updated} ta korxonaning sensori o`chirildi')
    deactivate_sensors.short_description = "Tanlangan korxonalar sensorlarini o'chirish"
    
    def calculate_status(self, request, queryset):
        for company in queryset:
            company.status = company.calculate_status()
            company.save()
        self.message_user(request, f'{queryset.count()} ta korxonaning holati yangilandi')
    calculate_status.short_description = "Tanlangan korxonalar holatini yangilash"

# Penalty Inline for Company
class PenaltyInline(admin.TabularInline):
    model = Penalty
    extra = 0
    readonly_fields = ('penalty_number', 'excess_amount', 'trees_required', 'status', 'created_at')
    fields = ('penalty_number', 'excess_amount', 'trees_required', 'status', 'deadline', 'created_at')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False

# Sensor Data Inline for Company
class SensorDataInline(admin.TabularInline):
    model = SensorData
    extra = 0
    readonly_fields = ('recorded_at',)
    fields = ('gas_amount', 'recorded_at')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False

# Notification Inline for Company
class NotificationInline(admin.TabularInline):
    model = Notification
    extra = 0
    readonly_fields = ('created_at',)
    fields = ('message', 'is_read', 'created_at')
    can_delete = False
    
    def has_add_permission(self, request, obj):
        return False

# Penalty Admin
class PenaltyAdmin(admin.ModelAdmin):
    list_display = ('penalty_number', 'company', 'excess_amount', 'trees_required', 
                   'status_badge', 'status', 'deadline', 'created_at')
    list_filter = ('status', 'created_at', 'deadline', 'company__region')
    search_fields = ('penalty_number', 'company__name', 'company__stir_number')
    readonly_fields = ('penalty_number', 'excess_amount', 'trees_required', 'created_at')
    list_editable = ('status', 'deadline')
    list_per_page = 25
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('penalty_number', 'company', 'excess_amount', 'trees_required')
        }),
        ('Holat va Muddat', {
            'fields': ('status', 'deadline')
        }),
        ('Qo`shimcha', {
            'fields': ('created_at',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'active': 'orange',
            'completed': 'green',
            'cancelled': 'red'
        }
        status_text = {
            'active': 'Faol',
            'completed': 'Bajarilgan',
            'cancelled': 'Bekor qilingan'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px;">{}</span>',
            colors.get(obj.status, 'gray'),
            status_text.get(obj.status, 'Noma\'lum')
        )
    status_badge.short_description = 'Holat'
    status_badge.admin_order_field = 'status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')
    
    actions = ['mark_as_completed', 'mark_as_cancelled']
    
    def mark_as_completed(self, request, queryset):
        updated = queryset.update(status='completed')
        self.message_user(request, f'{updated} ta jarima bajarilgan deb belgilandi')
    mark_as_completed.short_description = "Tanlangan jarimalarni bajarilgan deb belgilash"
    
    def mark_as_cancelled(self, request, queryset):
        updated = queryset.update(status='cancelled')
        self.message_user(request, f'{updated} ta jarima bekor qilingan deb belgilandi')
    mark_as_cancelled.short_description = "Tanlangan jarimalarni bekor qilingan deb belgilash"

# Penalty Response Admin
class PenaltyResponseAdmin(admin.ModelAdmin):
    list_display = ('penalty', 'submitted_at', 'comment_preview')
    list_filter = ('submitted_at', 'penalty__status')
    search_fields = ('penalty__penalty_number', 'penalty__company__name', 'comment')
    readonly_fields = ('submitted_at',)
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('penalty', 'comment', 'files')
        }),
        ('Qo`shimcha', {
            'fields': ('submitted_at',)
        }),
    )
    
    def comment_preview(self, obj):
        if len(obj.comment) > 50:
            return obj.comment[:50] + '...'
        return obj.comment
    comment_preview.short_description = 'Izoh'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('penalty__company')

# Sensor Data Admin
class SensorDataAdmin(admin.ModelAdmin):
    list_display = ('company', 'gas_amount', 'recorded_at')
    list_filter = ('recorded_at', 'company__region', 'company__industry_type')
    search_fields = ('company__name', 'company__stir_number')
    readonly_fields = ('recorded_at',)
    list_per_page = 50
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('company', 'gas_amount')
        }),
        ('Qo`shimcha', {
            'fields': ('recorded_at',)
        }),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')

# Notification Admin
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('company', 'message_preview', 'is_read', 'created_at')
    list_filter = ('is_read', 'created_at', 'company__region')
    search_fields = ('company__name', 'message')
    list_editable = ('is_read',)
    list_per_page = 25
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('company', 'message', 'is_read')
        }),
        ('Qo`shimcha', {
            'fields': ('created_at',)
        }),
    )
    
    def message_preview(self, obj):
        if len(obj.message) > 50:
            return obj.message[:50] + '...'
        return obj.message
    message_preview.short_description = 'Xabar'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'{updated} ta bildirishnoma o`qilgan deb belgilandi')
    mark_as_read.short_description = "Tanlangan bildirishnomalarni o'qilgan deb belgilash"
    
    def mark_as_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f'{updated} ta bildirishnoma o`qilmagan deb belgilandi')
    mark_as_unread.short_description = "Tanlangan bildirishnomalarni o'qilmagan deb belgilash"

# Report Admin
class ReportAdmin(admin.ModelAdmin):
    list_display = ('company', 'report_type', 'period', 'created_at', 'file_preview')
    list_filter = ('report_type', 'created_at', 'company__region')
    search_fields = ('company__name', 'period')
    readonly_fields = ('created_at',)
    
    fieldsets = (
        ('Asosiy Ma\'lumotlar', {
            'fields': ('company', 'report_type', 'period', 'file_path')
        }),
        ('Qo`shimcha', {
            'fields': ('created_at',)
        }),
    )
    
    def file_preview(self, obj):
        if obj.file_path:
            return format_html(
                '<a href="{}" target="_blank">Yuklab olish</a>',
                obj.file_path.url
            )
        return '-'
    file_preview.short_description = 'Fayl'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('company')

# Detailed Company Admin with inlines
class DetailedCompanyAdmin(CompanyAdmin):
    inlines = [PenaltyInline, SensorDataInline, NotificationInline]

# Admin site customization
admin.site.site_header = "Toshkent Shahri Ekologiya Monitoring Tizimi"
admin.site.site_title = "Ekologiya Admin"
admin.site.index_title = "Boshqaruv Paneli"

# Model registrations
admin.site.register(User, CustomUserAdmin)
admin.site.register(Region, RegionAdmin)
admin.site.register(IndustryType, IndustryTypeAdmin)
admin.site.register(Company, DetailedCompanyAdmin)
admin.site.register(Penalty, PenaltyAdmin)
admin.site.register(SensorData, SensorDataAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Report, ReportAdmin)

# Alternative simple registration for quick setup
# admin.site.register(User)
# admin.site.register(Region)
# admin.site.register(IndustryType)
# admin.site.register(Company)
# admin.site.register(Penalty)
# admin.site.register(PenaltyResponse)
# admin.site.register(SensorData)
# admin.site.register(Notification)
# admin.site.register(Report)

# admin.py ga qo'shing
from django.urls import path
from django.template.response import TemplateResponse

class CustomAdminSite(admin.AdminSite):
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('dashboard/', self.admin_view(self.dashboard_view), name='dashboard'),
        ]
        return custom_urls + urls
    
    def dashboard_view(self, request):
        # Dashboard statistikalarini hisoblash
        total_companies = Company.objects.count()
        total_penalties = Penalty.objects.count()
        active_penalties = Penalty.objects.filter(status='active').count()
        total_users = User.objects.count()
        
        context = {
            **self.each_context(request),
            'total_companies': total_companies,
            'total_penalties': total_penalties,
            'active_penalties': active_penalties,
            'total_users': total_users,
            'title': 'Dashboard',
        }
        return TemplateResponse(request, 'admin/dashboard.html', context)

# Oddiy admin.site o'rniga CustomAdminSite dan foydalaning
# admin_site = CustomAdminSite(name='custom_admin')

# admin.py ga qo'shing
import csv
from django.http import HttpResponse

class ExportMixin:
    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename={meta}.csv'
        
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field) for field in field_names])
        
        return response
    export_as_csv.short_description = "Tanlanganlarini CSV faylga eksport qilish"

# CompanyAdmin classiga ExportMixin ni qo'shing
class CompanyAdmin(admin.ModelAdmin, ExportMixin):
    actions = ['export_as_csv'] + CompanyAdmin.actions