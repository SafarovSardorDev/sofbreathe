from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('committee', 'Qo\'mita'),
        ('factory', 'Korxona'),
    )
    
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='factory')
    employee_id = models.CharField(max_length=50, blank=True, null=True)
    stir_number = models.CharField(max_length=9, blank=True, null=True)
    company = models.ForeignKey('Company', on_delete=models.CASCADE, null=True, blank=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    def __str__(self):
        return f"{self.username} - {self.get_user_type_display()}"

class Region(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name

class IndustryType(models.Model):
    name = models.CharField(max_length=100)
    
    def __str__(self):
        return self.name

class Company(models.Model):
    STATUS_CHOICES = (
        ('good', 'Yaxshi'),
        ('moderate', 'O\'rtacha'),
        ('bad', 'Xavfli'),
    )
    
    name = models.CharField(max_length=255)
    stir_number = models.CharField(max_length=9, unique=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    industry_type = models.ForeignKey(IndustryType, on_delete=models.CASCADE)
    latitude = models.FloatField()
    longitude = models.FloatField()
    max_allowed_gas = models.FloatField(default=100)  # kg/soat
    current_gas_amount = models.FloatField(default=0)  # kg/soat
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='good')
    sensor_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    def calculate_status(self):
        """
        Holatni current_gas_amount va max_allowed_gas bo'yicha aniqlaydi.
        - current_gas_amount < max_allowed_gas -> good
        - current_gas_amount == max_allowed_gas -> moderate
        - current_gas_amount > max_allowed_gas -> bad
        """
        if self.current_gas_amount < self.max_allowed_gas:
            return 'good'
        elif self.current_gas_amount == self.max_allowed_gas:
            return 'moderate'
        else:  # current_gas_amount > max_allowed_gas
            return 'bad'
    
    def save(self, *args, **kwargs):
        # saqlashdan oldin statusni avtomatik yangilash
        self.status = self.calculate_status()
        super().save(*args, **kwargs)
    


# monitoring/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal, InvalidOperation
import uuid
import math

# ... (User, Region, IndustryType, Company modelleri sizda mavjud bo'lishi kerak)

def generate_penalty_number():
    return f"PEN-{uuid.uuid4().hex[:8].upper()}"

# Har 1 kg/soat oshish uchun daraxtlar soni (Decimal ishlatamiz)
TREES_PER_KG_PER_HOUR = Decimal('10')

class Penalty(models.Model):
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('completed', 'Bajarilgan'),
        ('cancelled', 'Bekor qilingan'),
    )

    company = models.ForeignKey('Company', on_delete=models.CASCADE)

    # excess_amount avtomatik hisoblanadi — admin tomonidan tahrirlanmaydi
    excess_amount = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=Decimal('0.0'),
        validators=[MinValueValidator(Decimal('0.0'))],
        editable=False,
        help_text="Avtomatik hisoblanadi: current_gas_amount - max_allowed_gas (kg/soat)."
    )

    # trees_required avtomatik hisoblanadi, admin tahrirlay olmaydi
    trees_required = models.IntegerField(editable=False, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    deadline = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    penalty_number = models.CharField(max_length=20, unique=True, default=generate_penalty_number)

    def __str__(self):
        return f"Jarima #{self.penalty_number} - {self.company.name}"

    def compute_excess_amount(self) -> Decimal:
        """
        company.current_gas_amount - company.max_allowed_gas
        Agar natija manfiy bo'lsa -> 0
        """
        try:
            cur = Decimal(str(self.company.current_gas_amount))
            allowed = Decimal(str(self.company.max_allowed_gas))
        except (InvalidOperation, TypeError, AttributeError):
            return Decimal('0.0')
        diff = cur - allowed
        if diff <= Decimal('0'):
            return Decimal('0.0')
        # Round to the same decimal_places we use (3)
        return diff.quantize(Decimal('0.001'))

    def calculate_trees_required(self) -> int:
        """
        excess_amount * TREES_PER_KG_PER_HOUR, yuqoriga yaxlitlanadi.
        Agar excess_amount 0 bo'lsa 0 qaytaradi.
        """
        try:
            amt = Decimal(self.excess_amount)
        except (InvalidOperation, TypeError):
            return 0
        if amt <= Decimal('0'):
            return 0
        trees = math.ceil(float(amt * TREES_PER_KG_PER_HOUR))
        return max(0, int(trees))

    def save(self, *args, **kwargs):
        # 1) excess_amountni avtomatik hisoblash (company ma'lumotidan)
        if self.company_id:  # company mavjud bo'lsa
            self.excess_amount = self.compute_excess_amount()
        else:
            # Agar company tanlanmagan bo'lsa, default 0
            self.excess_amount = Decimal('0.0')

        # 2) trees_requiredni hisoblash
        self.trees_required = self.calculate_trees_required()

        # 3) penalty_number zaxira
        if not self.penalty_number:
            self.penalty_number = generate_penalty_number()

        super().save(*args, **kwargs)




class SensorData(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    gas_amount = models.FloatField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.company.name} - {self.gas_amount}kg - {self.recorded_at}"

class Notification(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Bildirishnoma - {self.company.name}"

class Report(models.Model):
    REPORT_TYPE_CHOICES = (
        ('monthly', 'Oylik'),
        ('quarterly', 'Choraklik'),
        ('yearly', 'Yillik'),
    )
    
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period = models.CharField(max_length=50)  # "2024-02", "2024-Q1", "2024"
    file_path = models.FileField(upload_to='reports/')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.get_report_type_display()} hisobot - {self.company.name} - {self.period}"