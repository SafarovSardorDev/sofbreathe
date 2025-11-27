# backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

class CustomAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Username, employee_id yoki stir_number orqali qidirish
            user = User.objects.get(
                Q(username=username) | 
                Q(employee_id=username) | 
                Q(stir_number=username)
            )
            
            if user.check_password(password):
                return user
                
        except User.DoesNotExist:
            return None
        
        return None