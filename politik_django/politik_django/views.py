"""
PolitiK - Django Views for Political Transparency Platform
APIs following RF01-RF07 requirements
"""

from django.contrib.auth import authenticate
from .auth import create_access_token, create_refresh_token, set_jwt_cookies, clear_jwt_cookies
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
import json

from .models import (
    Politico, Mandato, Fornecedor, Despesa, Alerta, Usuario, Assinatura,
    Configuracao
)
from .business_rules import NegocioRegras

# Frontend Views
def index(request):
    """Main dashboard view (RF06 - Dynamic Filters)"""
    # Get current year from config
    try:
        ano_atual_config = Configuracao.objects.get(chave='ANO_ATUAL')
        ano_atual = int(ano_atual_config.valor_numerico)
    except:
        ano_atual = datetime.now().year

    # Get statistics for dashboard
    stats = {
        'total_politicos': Politico.objects.count(),
        'total_mandatos': Mandato.objects.count(),
        'total_fornecedores': Fornecedor.objects.count(),
        'total_despesas_ano': Despesa.objects.filter(ano=ano_atual).aggregate(
            total=Sum('valor_liquidado'),
            count=Count('id')
        ),
        'despesas_por_categoria': Despesa.objects.filter(ano=ano_atual).values(
            'categoria'
        ).annotate(total=Sum('valor_liquidado')).order_by('-total'),
        'alertas_ativos': Alerta.objects.filter(resolvido=False).count(),
        'alertas_por_severidade': Alerta.objects.filter(resolvido=False).values(
            'severidade'
        ).annotate(count=Count('id')),
    }

    # Get dropdown data
    cargos = set(Mandato.objects.values_list('cargo', flat=True))
    esferas = set(Mandato.objects.values_list('esfera', flat=True))
    anos = set(Despesa.objects.values_list('ano', flat=True).order_by('-ano'))

    context = {
        'stats': stats,
        'cargos': sorted(cargos),
        'esferas': sorted(esferas),
        'anos': sorted(anos),
        'ano_atual': ano_atual,
    }

    return render(request, 'index.html', context)

def pagina_politico(request, politico_id):
    """Detailed view for a specific politician"""
    politico = get_object_or_404(Politico, id=politico_id)
    mandatos = politico.mandatos.all()

    context = {
        'politico': politico,
        'mandatos': mandatos,
    }

    return render(request, 'politico_detail.html', context)

def pagina_alertas(request):
    """View for alerts management"""
    alertas = Alerta.objects.select_related('mandato', 'mandato__politico').order_by('-criado_em')

    context = {
        'alertas': alertas,
        'alertas_nao_resolvidos': alertas.filter(resolvido=False),
    }

    return render(request, 'alertas.html', context)

# API Endpoints (JSON responses)
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_buscar_politicos(request):
    """RF06 - Dynamic Filters: Buscar políticos com filtros"""
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera')
    estado = request.GET.get('estado_uf')
    ano = request.GET.get('ano')
    partido = request.GET.get('partido')
    busca = request.GET.get('busca')

    queryset = Politico.objects.all()

    # Aplicar filtros
    if cargo:
        queryset = queryset.filter(mandatos__cargo=cargo)
    if esfera:
        queryset = queryset.filter(mandatos__esfera=esfera)
    if estado:
        queryset = queryset.filter(mandatos__estado_uf=estado)
    if partido:
        queryset = queryset.filter(partido=partido)
    if busca:
        queryset = queryset.filter(
            Q(nome_civil__icontains=busca) |
            Q(nome_social__icontains=busca)
        )

    # Converter para JSON
    politicos = []
    for politico in queryset.distinct():
        politicos.append({
            'id': politico.id,
            'nome_civil': politico.nome_civil,
            'nome_social': politico.nome_social,
            'partido': politico.partido,
            'uf': politico.uf,
            'municipio': politico.municipio,
            'mandatos': [
                {
                    'id': mandato.id,
                    'cargo': mandato.cargo,
                    'esfera': mandato.esfera,
                    'estado_uf': mandato.estado_uf,
                    'municipio': mandato.municipio,
                    'ano_inicio': mandato.ano_inicio,
                    'ano_fim': mandato.ano_fim,
                }
                for mandato in politico.mandatos.all()
            ]
        })

    return JsonResponse({
        'politicos': politicos,
        'total': len(politicos)
    })

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_buscar_despesas(request):
    """RF06 - Dynamic Filters: Buscar despesas com filtros dinâmicos"""
    mandato_id = request.GET.get('mandato_id')
    ano = request.GET.get('ano')
    mes = request.GET.get('mes')
    categoria = request.GET.get('categoria')
    fornecedor_cnpj = request.GET.get('fornecedor_cnpj')
    fonte = request.GET.get('fonte')
    min_valor = request.GET.get('min_valor')
    max_valor = request.GET.get('max_valor')

    queryset = Despesa.objects.select_related('mandato', 'mandato__politico', 'fornecedor')

    # Aplicar filtros
    if mandato_id:
        queryset = queryset.filter(mandato_id=mandato_id)
    if ano:
        queryset = queryset.filter(ano=ano)
    if mes:
        queryset = queryset.filter(mes=mes)
    if categoria:
        queryset = queryset.filter(categoria=categoria)
    if fornecedor_cnpj:
        queryset = queryset.filter(fornecedor_cnpj=fornecedor_cnpj)
    if fonte:
        queryset = queryset.filter(fonte=fonte)
    if min_valor:
        queryset = queryset.filter(valor_liquidado__gte=min_valor)
    if max_valor:
        queryset = queryset.filter(valor_liquidado__lte=max_valor)

    # Paginação simples
    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 50))
    offset = (page - 1) * limit

    despesas = queryset[offset:offset + limit]

    # Converter para JSON
    despesas_json = []
    for despesa in despesas:
        despesas_json.append({
            'id': despesa.id,
            'mandato_id': despesa.mandato_id,
            'politico_nome': despesa.mandato.politico.nome_civil,
            'cargo': despesa.mandato.cargo,
            'esfera': despesa.mandato.esfera,
            'categoria': despesa.categoria,
            'tipo_verba': despesa.tipo_verba,
            'descricao_despesa': despesa.descricao_despesa,
            'fornecedor': {
                'cnpj': despesa.fornecedor_cnpj,
                'razao_social': despesa.fornecedor.razao_social if despesa.fornecedor else None,
            } if despesa.fornecedor else None,
            'valor_liquidado': float(despesa.valor_liquidado),
            'valor_pago': float(despesa.valor_pago) if despesa.valor_pago else None,
            'data_emissao': despesa.data_emissao.strftime('%Y-%m-%d'),
            'fonte': despesa.fonte,
            'ano': despesa.ano,
            'mes': despesa.mes,
            'criado_em': despesa.criado_em.isoformat(),
        })

    total = queryset.count()

    return JsonResponse({
        'despesas': despesas_json,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit,
        }
    })

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_estatisticas(request):
    """RF06 - Dynamic Filters: Estatísticas para gráficos"""
    ano = request.GET.get('ano')
    categoria = request.GET.get('categoria')
    fonte = request.GET.get('fonte')

    queryset = Despesa.objects.all()

    if ano:
        queryset = queryset.filter(ano=ano)
    if categoria:
        queryset = queryset.filter(categoria=categoria)
    if fonte:
        queryset = queryset.filter(fonte=fonte)

    # Estatísticas por categoria
    stats = {}
    for cat in Despesa.CATEGORIA_ABSOLUTA_CHOICES:
        categoria_nome = cat[0]
        dados = queryset.filter(categoria=categoria_nome)
        stats[categoria_nome] = {
            'total': float(dados.aggregate(total=Sum('valor_liquidado'))['total'] or 0),
            'count': dados.count(),
            'media': float(dados.aggregate(media=Avg('valor_liquidado'))['media'] or 0),
        }

    # Estatísticas por ano
    anos = queryset.values_list('ano', flat=True).distinct().order_by('-ano')
    stats_por_ano = {}
    for ano in anos:
        dados_ano = queryset.filter(ano=ano)
        stats_por_ano[ano] = {
            'total': float(dados_ano.aggregate(total=Sum('valor_liquidado'))['total'] or 0),
            'count': dados_ano.count(),
        }

    # Alertas por severidade
    alertas_stats = {}
    for alerta in Alerta.objects.filter(resolvido=False):
        if alerta.tipo not in alertas_stats:
            alertas_stats[alerta.tipo] = {'count': 0, 'por_severidade': {}}
        alertas_stats[alerta.tipo]['count'] += 1

        if alerta.severidade not in alertas_stats[alerta.tipo]['por_severidade']:
            alertas_stats[alerta.tipo]['por_severidade'][alerta.severidade] = 0
            alertas_stats[alerta.tipo]['por_severidade'][alerta.severidade] += 1

    return JsonResponse({
        'stats_por_categoria': stats,
        'stats_por_ano': stats_por_ano,
        'alertas_stats': alertas_stats,
        'filtros': {
            'ano': ano,
            'categoria': categoria,
            'fonte': fonte,
        }
    })

@csrf_exempt
@require_http_methods(["POST"])
def api_atualizar_alerta(request):
    """RF06 - Dynamic Filters: Atualizar status de alerta"""
    try:
        data = json.loads(request.body)
        alerta_id = data.get('alerta_id')
        resolvido = data.get('resolvido', False)

        alerta = get_object_or_404(Alerta, id=alerta_id)
        alerta.resolvido = resolvido
        if resolvido:
            alerta.resolvido_em = timezone.now()
        alerta.save()

        return JsonResponse({
            'success': True,
            'message': 'Alerta atualizado com sucesso',
            'alerta_id': alerta.id,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

# Utility API endpoints
def api_categorias(request):
    """Get all expense categories"""
    categorias = Despesa.CATEGORIA_ABSOLUTA_CHOICES
    return JsonResponse({
        'categorias': [cat[0] for cat in categorias],
        'categorias_completas': categorias,
    })

def api_fontes(request):
    """Get all data sources (fontes)"""
    fontes = Despesa.objects.values_list('fonte', flat=True).distinct()
    return JsonResponse({
        'fontes': sorted(list(fontes)),
    })

def api_anos(request):
    """Get all years with data"""
    anos = Despesa.objects.values_list('ano', flat=True).distinct().order_by('-ano')
    return JsonResponse({
        'anos': list(anos),
    })

# Health check endpoint
def api_health(request):
    """Health check endpoint for monitoring"""
    stats = {
        'database': 'OK',
        'supabase': 'OK',  # Would check actual Supabase connection
        'timestamp': timezone.now().isoformat(),
        'version': '1.0.0',
    }

    return JsonResponse({
        'status': 'healthy',
        'stats': stats,
    })

# --- Autenticação JWT (RF07) ---
@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    """Endpoint de login gerando cookies HTTPOnly com JWT"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')

        user = authenticate(username=username, password=password)
        if user is not None:
            access_token = create_access_token(user)
            refresh_token = create_refresh_token(user)

            response = JsonResponse({
                'success': True,
                'message': 'Login realizado com sucesso',
                'user': {'username': user.username, 'email': user.email}
            })
            # A mágica acontece aqui: injeta os tokens no cookie HTTPOnly da resposta
            set_jwt_cookies(response, access_token, refresh_token)
            return response
        else:
            return JsonResponse({'success': False, 'message': 'Credenciais inválidas'}, status=401)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def api_logout(request):
    """Endpoint de logout limpando os cookies"""
    response = JsonResponse({'success': True, 'message': 'Logout realizado com sucesso'})
    clear_jwt_cookies(response)
    return response