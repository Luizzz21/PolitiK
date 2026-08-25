"""
PolitiK - Django Admin Configuration
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import (
    Politico, Mandato, Fornecedor, Despesa, Alerta, Usuario, Assinatura,
    Configuracao
)


@admin.register(Politico)
class PoliticoAdmin(admin.ModelAdmin):
    list_display = ['nome_civil', 'nome_social', 'partido', 'uf', 'municipio', 'mandatos_count', 'criado_em']
    list_filter = ['partido', 'uf', 'sexo', 'grau_instrucao']
    search_fields = ['nome_civil', 'nome_social', 'partido', 'uf', 'municipio']
    readonly_fields = ['criado_em', 'atualizado_em']
    ordering = ['nome_civil']

    def mandatos_count(self, obj):
        return obj.mandatos.count()
    mandatos_count.short_description = 'Mandatos'


@admin.register(Mandato)
class MandatoAdmin(admin.ModelAdmin):
    list_display = ['politico', 'cargo', 'esfera', 'estado_uf', 'municipio', 'ano_inicio', 'ano_fim', 'despesas_count']
    list_filter = ['cargo', 'esfera', 'estado_uf', 'ano_inicio', 'ano_fim']
    search_fields = ['politico__nome_civil', 'cargo', 'municipio']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-ano_inicio', 'politico__nome_civil']

    def despesas_count(self, obj):
        return obj.despesas.count()
    despesas_count.short_description = 'Despesas'


@admin.register(Fornecedor)
class FornecedorAdmin(admin.ModelAdmin):
    list_display = ['cnpj', 'razao_social', 'nome_fantasia', 'situacao_cadastral', 'municipio', 'uf', 'despesas_count', 'is_suspicious']
    list_filter = ['situacao_cadastral', 'uf', 'municipio']
    search_fields = ['cnpj', 'razao_social', 'nome_fantasia']
    readonly_fields = ['criado_em', 'atualizado_em']
    ordering = ['-criado_em']

    def despesas_count(self, obj):
        return obj.despesas.count()
    despesas_count.short_description = 'Despesas'

    def is_suspicious(self, obj):
        if obj.situacao_cadastral in ['BAIXADA', 'INAPTA', 'SUSPENSA']:
            return format_html('<span style="color: red;">⚠ Suspeito</span>')
        return format_html('<span style="color: green;">✓ OK</span>')
    is_suspicious.short_description = 'Status'


@admin.register(Despesa)
class DespesaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'politico_nome', 'cargo', 'categoria', 'tipo_verba',
        'fornecedor_info', 'valor_liquidado', 'data_emissao', 'fonte', 'ano'
    ]
    list_filter = [
        'categoria', 'fonte', 'ano', 'mes',
        'mandato__cargo', 'mandato__esfera', 'mandato__estado_uf'
    ]
    search_fields = [
        'mandato__politico__nome_civil',
        'tipo_verba', 'descricao_despesa',
        'fornecedor__razao_social', 'fornecedor__cnpj'
    ]
    readonly_fields = ['criado_em', 'atualizado_em']
    ordering = ['-data_emissao', '-criado_em']
    list_per_page = 50

    def politico_nome(self, obj):
        return obj.mandato.politico.nome_civil
    politico_nome.short_description = 'Político'
    politico_nome.admin_order_field = 'mandato__politico__nome_civil'

    def cargo(self, obj):
        return obj.mandato.cargo
    cargo.short_description = 'Cargo'
    cargo.admin_order_field = 'mandato__cargo'

    def fornecedor_info(self, obj):
        if obj.fornecedor:
            return f"{obj.fornecedor.razao_social[:30]} ({obj.fornecedor.cnpj})"
        return obj.fornecedor_cnpj or '-'
    fornecedor_info.short_description = 'Fornecedor'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'mandato', 'mandato__politico', 'fornecedor'
        )


@admin.register(Alerta)
class AlertaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'politico_nome', 'cargo', 'tipo', 'severidade',
        'titulo', 'valor_real', 'criado_em', 'resolvido'
    ]
    list_filter = ['tipo', 'severidade', 'resolvido', 'mandato__cargo', 'mandato__esfera']
    search_fields = [
        'mandato__politico__nome_civil', 'titulo', 'descricao',
        'referencia_cnpj'
    ]
    readonly_fields = ['criado_em', 'resolvido_em']
    ordering = ['-criado_em']
    list_editable = ['resolvido']
    list_per_page = 50

    def politico_nome(self, obj):
        return obj.mandato.politico.nome_civil
    politico_nome.short_description = 'Político'

    def cargo(self, obj):
        return obj.mandato.cargo
    cargo.short_description = 'Cargo'

    actions = ['marcar_resolvido', 'marcar_nao_resolvido']

    def marcar_resolvido(self, request, queryset):
        updated = queryset.update(resolvido=True, resolvido_em=timezone.now())
        self.message_user(request, f'{updated} alertas marcados como resolvidos.')
    marcar_resolvido.short_description = 'Marcar selecionados como resolvidos'

    def marcar_nao_resolvido(self, request, queryset):
        updated = queryset.update(resolvido=False, resolvido_em=None)
        self.message_user(request, f'{updated} alertas marcados como não resolvidos.')
    marcar_nao_resolvido.short_description = 'Marcar selecionados como não resolvidos'


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'get_full_name', 'anonimo', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['anonimo', 'is_staff', 'is_active', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    readonly_fields = ['date_joined', 'last_login', 'ultimo_login']
    ordering = ['-date_joined']


@admin.register(Assinatura)
class AssinaturaAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'politico_nome', 'cargo', 'tipo_notificacao', 'frequencia', 'ativo']
    list_filter = ['tipo_notificacao', 'frequencia', 'ativo', 'mandato__cargo']
    search_fields = ['usuario__username', 'mandato__politico__nome_civil']
    readonly_fields = ['criado_em', 'atualizado_em']
    ordering = ['-criado_em']

    def politico_nome(self, obj):
        return obj.mandato.politico.nome_civil
    politico_nome.short_description = 'Político'

    def cargo(self, obj):
        return obj.mandato.cargo
    cargo.short_description = 'Cargo'


@admin.register(Configuracao)
class ConfiguracaoAdmin(admin.ModelAdmin):
    list_display = ['chave', 'valor', 'tipo', 'descricao', 'atualizado_em']
    list_editable = ['valor']
    readonly_fields = ['criado_em', 'atualizado_em']
    search_fields = ['chave', 'descricao']


# Custom admin site configuration
admin.site.site_header = 'PolitiK - Administração'
admin.site.site_title = 'PolitiK Admin'
admin.site.index_title = 'Painel de Administração da Plataforma de Transparência'