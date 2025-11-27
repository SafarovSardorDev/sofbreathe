from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.utils import timezone
from datetime import datetime, timedelta
import json
from .models import *

# Asosiy sahifa
def index(request):
    companies = Company.objects.all()
    
    # Statistikalar
    total_companies = companies.count()
    good_companies = companies.filter(status='good').count()
    moderate_companies = companies.filter(status='moderate').count()
    bad_companies = companies.filter(status='bad').count()
    
    # Top 10 korxonalar
    top_companies = companies.order_by('-current_gas_amount')[:10]
    
    context = {
        'total_companies': total_companies,
        'good_companies': good_companies,
        'moderate_companies': moderate_companies,
        'bad_companies': bad_companies,
        'companies': companies,
        'top_companies': top_companies,
    }
    return render(request, 'index.html', context)

# Login sahifasi
# views.py (POST qismi uchun to'liq yangilangan login_view)
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from django.contrib.auth import get_user_model

User = get_user_model()

@require_http_methods(["GET", "POST"])
@csrf_protect
def login_view(request):
    if request.user.is_authenticated:
        if request.user.user_type == 'committee':
            return redirect('admin_dashboard')
        return redirect('company_dashboard')

    if request.method == 'POST':
        username_input = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user_type = request.POST.get('user_type', 'committee')

        print(f"Login attempt: {username_input}, type: {user_type}")  # Debug

        if not username_input or not password:
            messages.error(request, "Iltimos, barcha maydonlarni to'ldiring")
            return render(request, 'login.html', {'active_tab': user_type})

        try:
            user = None

            # Agar korxona (factory) turi bo'lsa, oldin STIR bo'yicha qidiramiz,
            # keyin username bo'yicha tekshiramiz.
            if user_type == 'factory':
                # 1) STIR bo'lib qidiring
                try:
                    user = User.objects.get(stir_number=username_input)
                    print("Found by stir_number:", user.username)
                except User.DoesNotExist:
                    # 2) username bo'yicha qidiramiz
                    try:
                        user = User.objects.get(username=username_input)
                        print("Found by username:", user.username)
                    except User.DoesNotExist:
                        user = None

            # Agar Qo'mita turi bo'lsa, employee_id yoki username bo'yicha qidiring
            else:  # committee
                try:
                    user = User.objects.get(employee_id=username_input)
                    print("Found by employee_id:", user.username)
                except User.DoesNotExist:
                    try:
                        user = User.objects.get(username=username_input)
                        print("Found by username:", user.username)
                    except User.DoesNotExist:
                        user = None

            # Agar user topilsa, authenticate qilish uchun uning username'ini ishlatamiz
            if user:
                authenticated_user = authenticate(request, username=user.username, password=password)
            else:
                # Hech qanday user topilmagan — fallback: authenticate raw username bilan urinib ko'rish
                authenticated_user = authenticate(request, username=username_input, password=password)

            if authenticated_user is not None:
                # user type mosligini tekshirish
                if authenticated_user.user_type == user_type:
                    login(request, authenticated_user)
                    return redirect('committee_dashboard' if user_type == 'committee' else 'company_dashboard')
                else:
                    messages.error(request, f'Siz {authenticated_user.get_user_type_display()} sifatida kira olmaysiz. Iltimos, to\'g\'ri kirish turini tanlang.')
                    print("User type mismatch")
            else:
                messages.error(request, 'Login yoki parol noto\'g\'ri')
                print("Authentication failed")

        except Exception as e:
            messages.error(request, f'Xatolik yuz berdi: {str(e)}')
            print("Error in login_view:", e)

    active_tab = request.POST.get('user_type', 'committee') if request.method == 'POST' else 'committee'
    return render(request, 'login.html', {'active_tab': active_tab})


# Logout view
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required

@login_required
def logout_view(request):
    logout(request)
    return redirect('index')

# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
import math
import uuid
from .models import Company, Region, IndustryType, Penalty, SensorData, Notification

# --- Helper functions ---
def compute_trees_needed(excess_amount):
    """
    Daraxtlar sonini hisoblash uchun oddiy qoidalar.
    Hozirgi qoidaga ko'ra: har 1 kg/soat ortiqcha uchun 2 ta daraxt.
    (Qoida: TREES_PER_KG = 2)
    O'zgartirish uchun shu funksiyani tahrirlang.
    """
    TREES_PER_KG = 2
    if excess_amount <= 0:
        return 0
    return math.ceil(excess_amount * TREES_PER_KG)

def company_extra_info(company):
    """
    Template uchun qo'shimcha atributlar (dinamik).
    - current excess: current_gas_amount - max_allowed_gas (>=0)
    - trees_needed: compute_trees_needed(...)
    """
    excess = max(0.0, company.current_gas_amount - company.max_allowed_gas)
    trees_needed = compute_trees_needed(excess)
    return {
        'excess_amount': round(excess, 2),
        'trees_needed': trees_needed
    }

# --- Views ---
@login_required
def dashboard(request):
    """
    Asosiy admin sahifasi: ekolog.html uchun barcha kerakli context'larni taqdim etadi.
    """
    total_companies = Company.objects.count()
    dangerous_companies_qs = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas'))
    dangerous_companies_count = dangerous_companies_qs.count()

    # recent penalties
    recent_penalties = Penalty.objects.select_related('company').order_by('-created_at')[:10]

    # region stats: region name + company_count
    region_stats = Region.objects.annotate(company_count=Count('company')).order_by('-company_count')

    # tayyor dangerous list (template `dangerous_companies_list` foydalanadi)
    dangerous_list = []
    for c in dangerous_companies_qs.order_by('-current_gas_amount')[:20]:
        info = company_extra_info(c)
        # attach dynamic fields so template can use company.get_trees_needed etc.
        c.get_trees_needed = info['trees_needed']
        c.excess_amount = info['excess_amount']
        dangerous_list.append(c)

    context = {
        'total_companies': total_companies,
        'dangerous_companies': dangerous_companies_count,
        'active_penalties': Penalty.objects.filter(status='active').count(),
        'dangerous_companies_list': dangerous_list,
        'recent_penalties': recent_penalties,
        'region_stats': [{'name': r.name, 'company_count': r.company_count} for r in region_stats],
        'companies': Company.objects.select_related('region', 'industry_type').all()[:20],  # yoki paginated
        'penalties': Penalty.objects.select_related('company').all()[:20],
    }

    return render(request, 'ekolog.html', context)

@login_required
@require_GET
def dashboard_stats(request):
    """
    JSON: tezkor statistikani qaytaradi (AJAX).
    JS: updateStatistics() shu endpointga murojaat qiladi.
    """
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()

    return JsonResponse({
        'total_companies': total_companies,
        'dangerous_companies': dangerous_companies,
        'active_penalties': active_penalties,
    })

@login_required
def companies(request):
    """
    Kompaniyalar jadvalini qaytaradi (partial HTML).
    Qidiruv va status filtrlarini qo'llaydi.
    JS: fetch(`/companies/?${params}`)
    """
    search = request.GET.get('search', '').strip()
    status = request.GET.get('status', '').strip()
    page = int(request.GET.get('page', 1))

    qs = Company.objects.select_related('region', 'industry_type').order_by('name')

    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(stir_number__icontains=search))

    if status in ('good', 'moderate', 'bad'):
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 15)
    page_obj = paginator.get_page(page)

    # qo'shimcha maydonlar
    companies_list = []
    for c in page_obj.object_list:
        info = company_extra_info(c)
        c.get_trees_needed = info['trees_needed']
        c.excess_amount = info['excess_amount']
        companies_list.append(c)

    # render partial (sizda 'partials/companies_table.html' bo'lishi kerak)
    return render(request, 'partials/companies_table.html', {
        'companies': companies_list,
        'page_obj': page_obj,
        'paginator': paginator,
    })

@login_required
@require_POST
def penalties(request):
    """
    Jarimalar ro'yxatini qaytaradi (partial HTML).
    JS: loadPenalties() - POST yuboradi.
    """
    status = request.POST.get('status', '').strip()
    qs = Penalty.objects.select_related('company').order_by('-created_at')

    if status in ('active', 'completed', 'cancelled'):
        qs = qs.filter(status=status)

    penalties_list = qs[:50]

    return render(request, 'partials/penalties_table.html', {
        'penalties': penalties_list
    })

@login_required
@require_POST
def create_penalty(request):
    """
    Jarima yaratish (AJAX).
    JS: createPenalty() -> yana serverdan result JSON kutadi.
    Kutilgan POST maydonlar: company_id, deadline (YYYY-MM-DD), comment (ixtiyoriy)
    """
    company_id = request.POST.get('company_id')
    deadline = request.POST.get('deadline')
    comment = request.POST.get('comment', '')

    if not company_id or not deadline:
        return JsonResponse({'success': False, 'error': 'Kompaniya va muddat talab qilinadi.'})

    try:
        company = Company.objects.get(pk=company_id)
    except Company.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Kompaniya topilmadi.'})

    # Excess amount hisoblash
    excess = max(0.0, company.current_gas_amount - company.max_allowed_gas)
    trees_required = compute_trees_needed(excess)

    try:
        penalty = Penalty.objects.create(
            company=company,
            excess_amount=round(excess, 2),
            trees_required=trees_required,
            status='active',
            deadline=deadline,
            penalty_number=f"PEN-{uuid.uuid4().hex[:8].upper()}",
        )

        # Agar comment bo'lsa, PenaltyResponse ham yaratish mumkin

        return JsonResponse({'success': True, 'message': 'Jarima muvaffaqiyatli yaratildi.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Xatolik: {str(e)}'})


### Hisobotlar va yuklab olish qismi:


# views.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum, Max
from django.utils import timezone
from django.db import models
import datetime
import io
import pandas as pd
from django.utils.timezone import make_naive
from django.core.paginator import Paginator

from .models import Company, Region, IndustryType, Penalty, SensorData

# --- Helper for report generation ---
def _get_month_range(year, month):
    start = datetime.date(year, month, 1)
    if month == 12:
        end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        end = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    return start, end

@login_required
def dashboard_page(request):
    """
    Bosh sahifa - Dashboard
    """
    # Umumiy statistika
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()
    
    # Xavfli korxonalar ro'yxati
    dangerous_companies_list = Company.objects.filter(
        current_gas_amount__gt=models.F('max_allowed_gas')
    ).select_related('region', 'industry_type')[:10]
    
    # So'nggi jarimalar
    recent_penalties = Penalty.objects.select_related('company').order_by('-created_at')[:10]
    
    context = {
        'total_companies': total_companies,
        'dangerous_companies': dangerous_companies,
        'active_penalties': active_penalties,
        'dangerous_companies_list': dangerous_companies_list,
        'recent_penalties': recent_penalties,
    }
    return render(request, 'ekolog.html', context)

@login_required
def companies_page(request):
    """
    Korxonalar sahifasi
    """
    search = request.GET.get('search', '')
    status = request.GET.get('status', '')
    
    companies = Company.objects.select_related('region', 'industry_type').all()
    
    if search:
        companies = companies.filter(
            Q(name__icontains=search) | 
            Q(stir_number__icontains=search) |
            Q(region__name__icontains=search)
        )
    
    if status:
        companies = companies.filter(status=status)
    
    # Pagination
    paginator = Paginator(companies, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'companies': page_obj,
        'search': search,
        'status_filter': status,
    }
    return render(request, 'ekolog.html', context)

@login_required
def penalties_page(request):
    """
    Jarimalar sahifasi
    """
    status = request.GET.get('status', '')
    
    penalties = Penalty.objects.select_related('company').all()
    
    if status:
        penalties = penalties.filter(status=status)
    
    # Pagination
    paginator = Paginator(penalties, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'penalties': page_obj,
        'status_filter': status,
    }
    return render(request, 'ekolog.html', context)

@login_required
def reports_page(request):
    """
    Hisobotlar sahifasi
    """
    regions = Region.objects.all().order_by('name')
    industry_types = IndustryType.objects.all().order_by('name')
    today = timezone.localdate()
    default_year = today.year
    default_month = today.month

    # Umumiy statistika
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()

    context = {
        'regions': regions,
        'industry_types': industry_types,
        'default_year': default_year,
        'default_month': default_month,
        'total_companies': total_companies,
        'dangerous_companies': dangerous_companies,
        'active_penalties': active_penalties,
    }
    return render(request, 'ekolog.html', context)

@login_required
def report_data(request):
    """
    Chart uchun JSON agregatlarini qaytaradi.
    """
    period_type = request.GET.get('period_type', 'monthly')
    year = int(request.GET.get('year', timezone.localdate().year))
    month = request.GET.get('month')

    # Korxona holatlari bo'yicha taqsimot
    status_qs = Company.objects.values('status').annotate(cnt=Count('id'))
    status_counts = {row['status']: row['cnt'] for row in status_qs}
    
    # Holat nomlarini o'zbek tilida qaytarish
    status_mapping = {
        'good': 'Yaxshi',
        'moderate': 'Oʻrtacha', 
        'bad': 'Xavfli'
    }
    
    by_status = []
    for status_key, status_name in status_mapping.items():
        count = status_counts.get(status_key, 0)
        # Ranglar
        if status_key == 'good':
            color = '#10b981'
        elif status_key == 'moderate':
            color = '#f59e0b'
        else:  # bad
            color = '#ef4444'
            
        by_status.append({
            'status': status_name,
            'count': count,
            'color': color
        })

    # Oylik trend - har bir holat bo'yicha
    monthly_trend = []
    status_trend_data = {
        'Yaxshi': [],
        'Oʻrtacha': [],
        'Xavfli': []
    }
    
    for m in range(1, 13):
        start = datetime.date(year, m, 1)
        if m == 12:
            end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            end = datetime.date(year, m + 1, 1) - datetime.timedelta(days=1)

        # Har bir holat bo'yicha hisoblash
        good_count = Company.objects.filter(
            status='good',
            created_at__date__lte=end
        ).count()
        
        moderate_count = Company.objects.filter(
            status='moderate', 
            created_at__date__lte=end
        ).count()
        
        bad_count = Company.objects.filter(
            status='bad',
            created_at__date__lte=end
        ).count()
        
        status_trend_data['Yaxshi'].append(good_count)
        status_trend_data['Oʻrtacha'].append(moderate_count)
        status_trend_data['Xavfli'].append(bad_count)
        
        monthly_trend.append({
            'label': f"{year}-{m:02d}",
            'good_count': good_count,
            'moderate_count': moderate_count,
            'bad_count': bad_count
        })

    # Sanoat turlari bo'yicha taqsimot
    industry_qs = IndustryType.objects.annotate(
        company_count=Count('company')
    ).values('name', 'company_count').order_by('-company_count')[:10]  # Faqat top 10
    
    by_industry = []
    industry_colors = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', 
                      '#ef4444', '#6366f1', '#ec4899', '#14b8a6', '#f97316']
    
    for i, industry in enumerate(industry_qs):
        by_industry.append({
            'industry': industry['name'],
            'count': industry['company_count'],
            'color': industry_colors[i % len(industry_colors)]
        })

    # Umumiy statistika
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()

    return JsonResponse({
        'by_status': by_status,
        'monthly_trend': monthly_trend,
        'status_trend_data': status_trend_data,
        'by_industry': by_industry,
        'stats': {
            'total_companies': total_companies,
            'dangerous_companies': dangerous_companies,
            'active_penalties': active_penalties
        }
    })

@login_required
def download_report(request):
    """
    Excel hisobot yaratadi va yuboradi.
    """
    report_type = request.GET.get('report_type', 'monthly')
    year = int(request.GET.get('year', timezone.localdate().year))
    month = request.GET.get('month')
    
    if report_type == 'monthly':
        if month is None:
            return HttpResponseBadRequest("month parametri monthly hisobot uchun majburiy")
        month = int(month)
        start_date, end_date = _get_month_range(year, month)
        period_label = f"{year}-{month:02d}"
    elif report_type == 'quarterly':
        quarter = int(request.GET.get('quarter', 1))
        start_month = (quarter - 1) * 3 + 1
        start_date = datetime.date(year, start_month, 1)
        end_month = start_month + 2
        _, end_day = _get_month_range(year, end_month)
        end_date = end_day
        period_label = f"{year}-Q{quarter}"
    elif report_type == 'yearly':
        start_date = datetime.date(year, 1, 1)
        end_date = datetime.date(year, 12, 31)
        period_label = f"{year}"
    else:
        return HttpResponseBadRequest("Noto'g'ri report_type")

    # Umumiy statistika
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()

    # Korxonalar jadvali
    companies_qs = Company.objects.select_related('region', 'industry_type').all().order_by('region__name', 'name')
    companies_data = []
    for c in companies_qs:
        companies_data.append({
            'ID': c.id,
            'Korxona nomi': c.name,
            'STIR raqami': c.stir_number,
            'Hudud': c.region.name,
            'Sanoat turi': c.industry_type.name,
            'Kenglik': c.latitude,
            'Uzunlik': c.longitude,
            'Ruxsat etilgan maksimal gaz': f"{c.max_allowed_gas} kg",
            'Joriy gaz miqdori': f"{c.current_gas_amount} kg",
            'Holati': c.get_status_display(),
            'Sensor faol': "Ha" if c.sensor_active else "Yo'q",
            'Yaratilgan sana': c.created_at.strftime("%d.%m.%Y %H:%M"),
        })

    # Jarimalar davr bo'yicha
    penalties_qs = Penalty.objects.filter(
        created_at__date__gte=start_date, 
        created_at__date__lte=end_date
    ).select_related('company').order_by('-created_at')
    
    penalties_data = []
    for p in penalties_qs:
        penalties_data.append({
            'Jarima raqami': p.penalty_number,
            'Korxona': p.company.name,
            'Oshib ketgan miqdor': f"{p.excess_amount} kg",
            'Kerakli daraxtlar': f"{p.trees_required} ta",
            'Holati': p.get_status_display(),
            'Muddati': p.deadline.strftime("%d.%m.%Y"),
            'Yaratilgan sana': p.created_at.strftime("%d.%m.%Y %H:%M"),
        })

    # Oylik trend
    trend = []
    for m in range(1, 13):
        month_start = datetime.date(year, m, 1)
        if m == 12:
            month_end = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
        else:
            month_end = datetime.date(year, m + 1, 1) - datetime.timedelta(days=1)
            
        dangerous_count = Company.objects.filter(
            current_gas_amount__gt=models.F('max_allowed_gas'),
            created_at__date__lte=month_end
        ).count()
        
        trend.append({
            'Oy': f"{year}-{m:02d}", 
            'Xavfli korxonalar soni': dangerous_count
        })

    # Excel yaratish
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Overview sheet
        overview_data = [{
            'Hisobot davri': period_label,
            'Jami korxonalar': total_companies,
            'Xavfli korxonalar': dangerous_companies,
            'Faol jarimalar': active_penalties,
            'Yaratilgan sana': timezone.now().strftime("%d.%m.%Y %H:%M")
        }]
        overview_df = pd.DataFrame(overview_data)
        overview_df.to_excel(writer, sheet_name='Umumiy maʼlumot', index=False)

        # Korxonalar sheet
        if companies_data:
            companies_df = pd.DataFrame(companies_data)
            companies_df.to_excel(writer, sheet_name='Korxonalar', index=False)
        else:
            pd.DataFrame({'Maʼlumot': ['Hech qanday korxona topilmadi']}).to_excel(
                writer, sheet_name='Korxonalar', index=False
            )

        # Jarimalar sheet
        if penalties_data:
            penalties_df = pd.DataFrame(penalties_data)
            penalties_df.to_excel(writer, sheet_name='Jarimalar', index=False)
        else:
            pd.DataFrame({'Maʼlumot': [f'{period_label} davrida hech qanday jarima topilmadi']}).to_excel(
                writer, sheet_name='Jarimalar', index=False
            )

        # Trend sheet
        trend_df = pd.DataFrame(trend)
        trend_df.to_excel(writer, sheet_name='Oylik trend', index=False)

    output.seek(0)
    filename = f"ekolog_hisobot_{period_label}.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

@login_required
def dashboard_stats(request):
    """
    Dashboard uchun real-time statistika
    """
    total_companies = Company.objects.count()
    dangerous_companies = Company.objects.filter(current_gas_amount__gt=models.F('max_allowed_gas')).count()
    active_penalties = Penalty.objects.filter(status='active').count()
    
    return JsonResponse({
        'total_companies': total_companies,
        'dangerous_companies': dangerous_companies,
        'active_penalties': active_penalties,
    })


# korxona tomon

# views.py - Korxona Paneli uchun qo'shimcha views
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q
import json
import datetime
from .models import Company, Penalty, SensorData, Notification

@login_required
def company_dashboard(request):
    """
    Korxona dashboard sahifasi
    """
    if request.user.user_type != 'factory':
        return render(request, 'error.html', {'error': 'Sizga korxona paneliga kirish ruxsati yo\'q'})
    
    company = request.user.company
    if not company:
        return render(request, 'error.html', {'error': 'Sizga biriktirilgan korxona topilmadi'})
    
    # Sensor ma'lumotlari
    sensor_data = SensorData.objects.filter(company=company).order_by('-recorded_at')[:10]
    
    # Faol jarimalar
    active_penalties = Penalty.objects.filter(company=company, status='active')
    
    # So'nggi ogohlantirishlar
    recent_notifications = Notification.objects.filter(company=company).order_by('-created_at')[:5]
    
    context = {
        'company': company,
        'sensor_data': sensor_data,
        'active_penalties': active_penalties,
        'recent_notifications': recent_notifications,
    }
    
    return render(request, 'korxona.html', context)

@login_required
@csrf_exempt
def company_penalties(request):
    """
    Korxona jarimalari ro'yxati (AJAX)
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'Korxona topilmadi'}, status=404)
    
    status_filter = request.GET.get('status', '')
    
    penalties = Penalty.objects.filter(company=company)
    
    if status_filter:
        penalties = penalties.filter(status=status_filter)
    
    penalties_data = []
    for penalty in penalties.order_by('-created_at'):
        penalties_data.append({
            'id': penalty.id,
            'penalty_number': penalty.penalty_number,
            'excess_amount': float(penalty.excess_amount),
            'trees_required': penalty.trees_required,
            'status': penalty.status,
            'status_display': penalty.get_status_display(),
            'deadline': penalty.deadline.strftime('%Y-%m-%d'),
            'created_at': penalty.created_at.strftime('%Y-%m-%d'),
            'response': getattr(penalty, 'response_data', None)
        })
    
    return JsonResponse({'penalties': penalties_data})

@login_required
@csrf_exempt
def submit_penalty_response(request, penalty_id):
    """
    Jarimaga javob yuborish
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'success': False, 'error': 'Ruxsat yo\'q'})
    
    company = request.user.company
    if not company:
        return JsonResponse({'success': False, 'error': 'Korxona topilmadi'})
    
    penalty = get_object_or_404(Penalty, id=penalty_id, company=company)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            comment = data.get('comment', '')
            files = data.get('files', [])
            
            if not comment.strip():
                return JsonResponse({'success': False, 'error': 'Izoh maydoni to\'ldirilishi shart'})
            
            # Jarima javobini saqlash (Penalty modeliga response maydonini qo'shish kerak)
            # Vaqtincha Notification yaratamiz
            Notification.objects.create(
                company=company,
                message=f"Jarima #{penalty.penalty_number} uchun javob: {comment}",
                is_read=False
            )
            
            # Agar fayllar bo'lsa, ularni saqlash logikasi
            if files:
                # Fayllarni saqlash logikasi bu yerda bo'ladi
                pass
            
            # Jarimani "completed" holatiga o'tkazish
            penalty.status = 'completed'
            penalty.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Javobingiz muvaffaqiyatli yuborildi'
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Faqat POST so\'rovi qabul qilinadi'})

@login_required
def company_sensor_data(request):
    """
    Sensor ma'lumotlarini olish (real-time)
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'Korxona topilmadi'}, status=404)
    
    # Oxirgi sensor ma'lumotlari
    latest_sensor_data = SensorData.objects.filter(company=company).order_by('-recorded_at').first()
    
    data = {
        'current_gas_amount': company.current_gas_amount,
        'max_allowed_gas': company.max_allowed_gas,
        'status': company.status,
        'status_display': company.get_status_display(),
        'sensor_active': company.sensor_active,
        'last_update': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'latest_sensor_value': latest_sensor_data.gas_amount if latest_sensor_data else 0
    }
    
    return JsonResponse(data)

@login_required
def company_notifications(request):
    """
    Korxona ogohlantirishlari
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'Korxona topilmadi'}, status=404)
    
    notifications = Notification.objects.filter(company=company).order_by('-created_at')[:10]
    
    notifications_data = []
    for notification in notifications:
        notifications_data.append({
            'id': notification.id,
            'message': notification.message,
            'is_read': notification.is_read,
            'created_at': notification.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    return JsonResponse({'notifications': notifications_data})

@login_required
def download_company_report(request, report_type):
    """
    Korxona hisobotlarini yuklab olish
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'Korxona topilmadi'}, status=404)
    
    # Hisobot turi
    valid_report_types = ['monthly', 'quarterly', 'yearly']
    if report_type not in valid_report_types:
        return JsonResponse({'error': 'Noto\'g\'ri hisobot turi'}, status=400)
    
    # Hisobot yaratish va yuklab olish logikasi
    # Bu yerda Excel yoki PDF hisobot yaratish kodi bo'ladi
    
    # Vaqtincha muvaffaqiyat xabarini qaytaramiz
    return JsonResponse({
        'success': True,
        'message': f'{report_type} hisobot yuklab olindi',
        'report_type': report_type,
        'company': company.name
    })

@login_required
@csrf_exempt
def update_sensor_data(request):
    """
    Sensor ma'lumotlarini yangilash (simulyatsiya uchun)
    """
    if request.user.user_type != 'factory':
        return JsonResponse({'error': 'Ruxsat yo\'q'}, status=403)
    
    company = request.user.company
    if not company:
        return JsonResponse({'error': 'Korxona topilmadi'}, status=404)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            gas_amount = data.get('gas_amount')
            
            if gas_amount is not None:
                # Yangi sensor ma'lumotini yaratish
                SensorData.objects.create(
                    company=company,
                    gas_amount=gas_amount
                )
                
                # Kompaniyaning joriy gaz miqdorini yangilash
                company.current_gas_amount = gas_amount
                company.save()
                
                return JsonResponse({
                    'success': True,
                    'message': 'Sensor ma\'lumotlari yangilandi',
                    'new_gas_amount': gas_amount
                })
            else:
                return JsonResponse({'success': False, 'error': 'Gaz miqdori kiritilmagan'})
                
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Faqat POST so\'rovi qabul qilinadi'})



