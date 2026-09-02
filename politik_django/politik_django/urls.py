"""
URL configuration for politik_django project.
"""
from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Frontend pages
    path('', views.index, name='index'),
    path('politico/<int:politico_id>/', views.pagina_politico, name='pagina_politico'),
    path('ranking/', views.ranking_view, name='ranking'),
    path('despesas/', views.despesas_view, name='despesas'),
    path('presidencia/', views.presidencia_view, name='presidencia'),
    path('fornecedores/', views.fornecedores_view, name='fornecedores'),
    path('fornecedor/<str:cnpj>/', views.fornecedor_detail, name='fornecedor_detail'),
    path('alertas/', views.pagina_alertas, name='pagina_alertas'),
    path('minha-conta/', views.pagina_minha_conta, name='pagina_minha_conta'),
    path('comunidade/', views.comunidade_view, name='comunidade'),
    path('privacidade/', views.privacidade_view, name='privacidade'),
    path('termos/', views.termos_view, name='termos'),
    path('sobre/', views.sobre_view, name='sobre'),

    # API Endpoints - Consultas
    path('api/politicos/', views.api_buscar_politicos, name='api_buscar_politicos'),
    path('api/export/despesas/csv/', views.api_exportar_despesas_csv, name='api_export_despesas_csv'),
    path('api/despesas/', views.api_buscar_despesas, name='api_buscar_despesas'),
    path('api/estatisticas/', views.api_estatisticas, name='api_estatisticas'),
    
    # API Endpoints - Utilitários
    path('api/categorias/', views.api_categorias, name='api_categorias'),
    path('api/fontes/', views.api_fontes, name='api_fontes'),
    path('api/anos/', views.api_anos, name='api_anos'),
    path('api/health/', views.api_health, name='api_health'),

    # API Endpoints - Ações e Vínculos
    path('api/alerta/atualizar/', views.api_atualizar_alerta, name='api_atualizar_alerta'),
    path('api/politico/acompanhar/', views.api_acompanhar_politico, name='api_acompanhar_politico'),
    path('api/notificacoes/', views.api_notificacoes, name='api_notificacoes'),
    path('api/assinaturas/', views.api_assinaturas, name='api_assinaturas'),
    path('api/assinatura/<int:assinatura_id>/remover/', views.api_remover_assinatura, name='api_remover_assinatura'),

    # API Endpoints - Autenticação JWT
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/auth/logout/', views.api_logout, name='api_logout'),
    path('api/auth/express/', views.api_express_auth, name='api_express_auth'),
    path('api/auth/reset/', views.api_reset_password, name='api_reset_password'),
    path('api/v1/fornecedor-risco/<str:cnpj>/', views.api_b2b_fornecedor_risk, name='api_b2b_fornecedor_risk'),
]