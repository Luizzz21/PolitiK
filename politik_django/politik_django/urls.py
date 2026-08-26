"""
PolitiK - URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from . import views

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),

    # Home page
    path('', views.index, name='index'),
    path('politico/<int:politico_id>/', views.pagina_politico, name='politico_detail'),
    path('alertas/', views.pagina_alertas, name='alertas'),

    # API endpoints
    path('api/auth/express/', views.api_express_auth, name='api_express_auth'),
    path('api/', include([
        # Auth JWT
        path('auth/login/', views.api_login, name='api_login'),
        path('auth/logout/', views.api_logout, name='api_logout'),
        # Political data
        path('politicos/', views.api_buscar_politicos, name='api_buscar_politicos'),
        path('despesas/', views.api_buscar_despesas, name='api_buscar_despesas'),
        path('estatisticas/', views.api_estatisticas, name='api_estatisticas'),
        path('categorias/', views.api_categorias, name='api_categorias'),
        path('fontes/', views.api_fontes, name='api_fontes'),
        path('anos/', views.api_anos, name='api_anos'),
        path('health/', views.api_health, name='api_health'),

        # Alert management
        path('alerta/atualizar/', views.api_atualizar_alerta, name='api_atualizar_alerta'),
    ])),

    # Health check (alternative)
    path('health/', views.api_health, name='health_check'),

    # Django auth URLs (for login/logout)
    path('accounts/', include('django.contrib.auth.urls')),
]