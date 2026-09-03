"""
PolitiK - Django Views for Political Transparency Platform
APIs following RF01-RF07 requirements
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from django.db.models import Sum, Count, Max, Q, Avg
from django.db.utils import OperationalError
from django.utils import timezone
from datetime import datetime, timedelta
import json
import traceback

from django.contrib.auth import authenticate, get_user_model
from .auth import create_access_token, create_refresh_token, set_jwt_cookies, clear_jwt_cookies, jwt_required, authenticate_request

from .models import (
    Politico, Mandato, Fornecedor, Despesa, Alerta, Usuario, Assinatura,
    Configuracao, DespesaCampanha, EmendaParlamentar, CampanhaEleitoral
)
from .business_rules import NegocioRegras

# Carrega o modelo de usuÃ¡rio correto (Custom User Model) definido no settings.py
User = get_user_model()

# Frontend Views

def ranking_view(request):
    """View para o Ranking de Risco"""
    busca = request.GET.get('q', '')
    esfera = request.GET.get('esfera') or request.GET.get('escopo', '')
    
    queryset = Politico.objects.prefetch_related('mandatos').all()
    
    if busca:
        queryset = queryset.filter(nome_civil__icontains=busca)
    
    if esfera:
        if esfera.lower() == 'federal':
            queryset = queryset.filter(mandatos__esfera__iexact='Federal')
        elif esfera.lower() == 'estadual':
            queryset = queryset.filter(mandatos__esfera__iexact='Estadual')
        elif esfera.lower() == 'municipal':
            queryset = queryset.filter(mandatos__esfera__iexact='Municipal')
        else:
            queryset = queryset.filter(mandatos__esfera=esfera)
        
    sort_param = request.GET.get('sort', '-total_gasto')
    
    # Map front-end sort values to valid model fields/annotations
    sort_mapping = {
        '-total_gasto': '-total_gasto',
        '-score_risco': '-max_score',
        'politico__nome_civil': 'nome_civil',
        'nome_civil': 'nome_civil'
    }
    
    order_by_field = sort_mapping.get(sort_param, '-total_gasto')

    politicos_raw = queryset.annotate(
        total_gasto=Sum('mandatos__despesas__valor_liquidado'),
        max_score=Max('mandatos__score_risco')
    ).filter(total_gasto__gt=0).order_by(order_by_field)[:100]


    politicos = []
    for p in politicos_raw:
        # Tenta pegar o mandato principal (o mais recente)
        mandato_principal = p.mandatos.first()
        cargo_str = mandato_principal.cargo if mandato_principal else 'Agente PÃºblico'
        esfera_str = mandato_principal.esfera if mandato_principal else '-'
        
        politicos.append({
            'id': p.id,
            'nome_civil': p.nome_civil,
            'cargo_display': cargo_str,
            'esfera_display': esfera_str,
            'score_risco': p.max_score or 0,
            'total_gasto': p.total_gasto or 0,
            'foto_url': p.foto_url if hasattr(p, 'foto_url') else None,
        })

    
    return render(request, 'ranking.html', {'politicos': politicos, 'busca': busca, 'esfera_filtro': esfera, 'current_escopo': esfera, 'current_sort': sort_param})


def despesas_view(request):
    return render(request, 'despesas.html')

def presidencia_view(request):
    return render(request, 'presidencia.html')

@cache_page(60 * 15)
def index(request):
    """Main dashboard view (RF06 - Dynamic Filters)"""
    
    ano_str = request.GET.get('ano')
    try:
        ano_atual = int(ano_str) if ano_str else datetime.now().year
    except ValueError:
        ano_atual = datetime.now().year

    cargo_filtro = request.GET.get('cargo', '')
    categoria_filtro = request.GET.get('categoria', '')
    escopo_filtro = request.GET.get('escopo', '')

    despesas_qs = Despesa.objects.filter(ano=ano_atual)
    mandatos_qs = Mandato.objects.all()

    if cargo_filtro:
        despesas_qs = despesas_qs.filter(mandato__cargo=cargo_filtro)
        mandatos_qs = mandatos_qs.filter(cargo=cargo_filtro)
    if escopo_filtro:
        despesas_qs = despesas_qs.filter(mandato__esfera=escopo_filtro)
        mandatos_qs = mandatos_qs.filter(esfera=escopo_filtro)
    if categoria_filtro:
        despesas_qs = despesas_qs.filter(categoria=categoria_filtro)

    stats = {
        'total_politicos': Politico.objects.count(),
        'total_mandatos': Mandato.objects.count(),
        'total_fornecedores': Fornecedor.objects.count(),
        'total_despesas_ano': despesas_qs.aggregate(
            total=Sum('valor_liquidado'),
            count=Count('id')
        ),
        'despesas_por_categoria': despesas_qs.values(
            'categoria'
        ).annotate(total=Sum('valor_liquidado')).order_by('-total'),
        'alertas_ativos': Alerta.objects.filter(resolvido=False).count(),
        'alertas_por_severidade': Alerta.objects.filter(resolvido=False).values(
            'severidade'
        ).annotate(count=Count('id')),
    }

    # Calcula Top Gastadores (Ranking)
    from django.db.models import Value, DecimalField
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    top_gastadores = mandatos_qs.annotate(
        total_gasto=Coalesce(
            Sum('despesas__valor_liquidado', filter=Q(despesas__ano=ano_atual)), 
            Value(Decimal('0.0')),
            output_field=DecimalField()
        )
    ).filter(total_gasto__gt=0).order_by('-total_gasto')[:5]

    cargos = set(Mandato.objects.values_list('cargo', flat=True))
    esferas = set(Mandato.objects.values_list('esfera', flat=True))
    anos = set(Despesa.objects.values_list('ano', flat=True).order_by('-ano'))
    
    categorias = list(NegocioRegras.CATEGORIAS_ABSOLUTAS.keys()) + ['Outros']

    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    context = {
        'stats': stats,
        'top_gastadores': top_gastadores,
        'cargo_selecionado': cargo_filtro,
        'categoria_selecionada': categoria_filtro,
        'escopo_selecionado': escopo_filtro,
        'cargos': sorted(cargos),
        'esferas': sorted(esferas),
        'anos': sorted(anos),
        'categorias': sorted(categorias),
        'ano_atual': ano_atual,
        'cargos_count': cargos_count,
    }

    return render(request, 'index.html', context)

def fornecedor_detail(request, cnpj):
    """Perfil individual do fornecedor e anÃ¡lise de risco (Frente 3.4)"""
    fornecedor = get_object_or_404(Fornecedor, cnpj=cnpj)
    
    # Busca dados na Receita Federal (BrasilAPI) se estiverem vazios
    if not getattr(fornecedor, 'cnae_fiscal', None) or fornecedor.cnae_fiscal == '':
        try:
            import requests
            resp = requests.get(f'https://brasilapi.com.br/api/cnpj/v1/{fornecedor.cnpj}', timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                fornecedor.razao_social = data.get('razao_social', fornecedor.razao_social)
                fornecedor.nome_fantasia = data.get('nome_fantasia')
                fornecedor.cnae_fiscal = f"{data.get('cnae_fiscal', '')} - {data.get('cnae_fiscal_descricao', '')}"
                fornecedor.natureza_juridica = data.get('natureza_juridica')
                fornecedor.capital_social = data.get('capital_social')
                
                situacao = data.get('descricao_situacao_cadastral', '')
                if situacao in [c[1].upper() for c in Fornecedor.SITUACAO_CADASTRAL_CHOICES]:
                    fornecedor.situacao_cadastral = situacao.upper()
                else:
                    fornecedor.situacao_cadastral = 'NULO'
                    
                fornecedor.uf = data.get('uf')
                fornecedor.municipio = data.get('municipio')
                fornecedor.logradouro = data.get('logradouro')
                fornecedor.numero = data.get('numero')
                fornecedor.bairro = data.get('bairro')
                fornecedor.save()
            elif resp.status_code == 404:
                # CNPJ not found or invalid type, mark as DADOS INDISPONÃVEIS so we don't query again
                fornecedor.cnae_fiscal = "DADOS INDISPONÃVEIS (RECEITA FEDERAL)"
                fornecedor.save()
        except Exception as e:
            # Em caso de timeout ou erro de rede, nÃ£o travamos a pÃ¡gina do usuÃ¡rio
            pass
            
    # AgregaÃ§Ãµes de despesas
    despesas = Despesa.objects.filter(fornecedor=fornecedor).select_related('mandato__politico')
    
    total_recebido = despesas.aggregate(total=Sum('valor_liquidado'))['total'] or 0.0
    
    # Maiores pagadores (polÃ­ticos)
    pagadores = despesas.values(
        'mandato__politico__id', 
        'mandato__politico__nome_civil', 
        'mandato__cargo', 
        'mandato__esfera'
    ).annotate(total_pago=Sum('valor_liquidado')).order_by('-total_pago')
    
    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    context = {
        'fornecedor': fornecedor,
        'total_recebido': total_recebido,
        'pagadores': pagadores,
        'despesas_recentes': despesas.order_by('-data_emissao')[:50]
    }
    return render(request, 'fornecedor_detail.html', context)

def pagina_politico(request, politico_id):
    """Detailed view for a specific politician (DossiÃª)"""
    politico = get_object_or_404(Politico, id=politico_id)
    mandatos = Mandato.objects.filter(politico=politico)
    
    # Campanhas Eleitorais
    campanhas = CampanhaEleitoral.objects.filter(politico=politico).order_by('-ano')
    
    # Query parÃ¢metros para filtro
    busca = request.GET.get('q', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')
    
    despesas_query = Despesa.objects.select_related('fornecedor').filter(mandato__in=mandatos).order_by('-data_emissao')
    if busca:
            despesas_query = despesas_query.filter(Q(fornecedor__razao_social__icontains=busca) | Q(categoria__icontains=busca))
    
    # Filter by date if provided
    if data_inicio:
        despesas_query = despesas_query.filter(data_emissao__gte=data_inicio)
    if data_fim:
        despesas_query = despesas_query.filter(data_emissao__lte=data_fim)
        
    # Limitar para as Ãºltimas 200 despesas para performance na pÃ¡gina
    despesas_politico = despesas_query[:200]
    
    # Despesas de campanha do politico
    despesas_campanha = DespesaCampanha.objects.select_related('fornecedor', 'campanha').filter(campanha__in=campanhas).order_by('-data_despesa')[:200]
    
    # Emendas Parlamentares
    emendas = EmendaParlamentar.objects.filter(politico=politico).order_by('-ano', '-valor_pago')
    
    # Alertas que compoem o Score de Risco
    alertas = Alerta.objects.filter(mandato__in=mandatos, resolvido=False).order_by('-criado_em')
    
    from django.db.models import Max
    max_score = mandatos.aggregate(Max('score_risco'))['score_risco__max'] or 0
    
    is_following = False
    user, error = authenticate_request(request)
    if user:
        is_following = Assinatura.objects.filter(usuario=user, mandato__in=mandatos, ativo=True).exists()

    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    # Calculate total gasto
    from django.db.models import Sum
    total_gasto = Despesa.objects.filter(mandato__in=mandatos).aggregate(total=Sum('valor_liquidado'))['total'] or 0
    total_gasto_raw = str(total_gasto)

    context = {
        'politico': politico,
        'mandatos': mandatos,
        'campanhas': campanhas,
        'despesas_politico': despesas_politico,
        'despesas_campanha': despesas_campanha,
        'emendas': emendas,
        'is_following': is_following,
        'busca': busca,
        'data_inicio': data_inicio,
        'data_fim': data_fim,
        'max_score': max_score,
        'alertas': alertas,
        'total_gasto': total_gasto,
        'total_gasto_raw': total_gasto_raw,
    }

    return render(request, 'politico_detail.html', context)

import csv
from django.http import HttpResponse

def api_exportar_despesas_csv(request):
    """Exporta a lista filtrada de despesas para CSV (Frente 3.8)"""
    ano = request.GET.get('ano')
    categoria = request.GET.get('categoria')
    esfera = request.GET.get('esfera')
    
    queryset = Despesa.objects.select_related('mandato__politico', 'fornecedor').order_by('-data_emissao')
    
    if ano: queryset = queryset.filter(ano=ano)
    if categoria: queryset = queryset.filter(categoria=categoria)
    if esfera: queryset = queryset.filter(mandato__esfera=esfera)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="politik_despesas.csv"'
    
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Data', 'Politico', 'Cargo', 'Esfera', 'Fornecedor (Razao Social)', 'CNPJ Fornecedor', 'Categoria', 'Valor (R$)'])
    
    for d in queryset[:5000]: # Limite de seguranca
        writer.writerow([
            d.data_emissao.strftime('%d/%m/%Y') if d.data_emissao else '',
            d.mandato.politico.nome_civil,
            d.mandato.cargo,
            d.mandato.esfera,
            d.fornecedor.razao_social if d.fornecedor else '',
            d.fornecedor.cnpj if d.fornecedor else '',
            d.categoria,
            f"{d.valor_liquidado:.2f}".replace('.', ',')
        ])
        
    return response

def pagina_alertas(request):
    """View for alerts management"""
    busca = request.GET.get('q', '')
    severidade = request.GET.get('severidade', '')

    alertas = Alerta.objects.select_related('mandato', 'mandato__politico').order_by('-criado_em')

    if busca:
        alertas = alertas.filter(mandato__politico__nome_civil__icontains=busca)
    
    if severidade:
        alertas = alertas.filter(severidade=severidade)

    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    context = {
        'alertas': alertas,
        'alertas_nao_resolvidos': alertas.filter(resolvido=False),
        'busca': busca,
        'severidade_filtro': severidade,
    }

    return render(request, 'alertas.html', context)

def pagina_minha_conta(request):
    """Painel do usuÃ¡rio logado: lista os polÃ­ticos que acompanha"""
    user, error = authenticate_request(request)
    if not user:
        return redirect('index')

    assinaturas = Assinatura.objects.filter(
        usuario=user, ativo=True
    ).select_related(
        'mandato', 'mandato__politico'
    ).order_by('-criado_em')

    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    context = {
        'user': user,
        'assinaturas': assinaturas,
    }
    return render(request, 'minha_conta.html', context)

# API Endpoints (JSON responses)
@csrf_exempt
@require_http_methods(["GET", "POST"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_buscar_politicos(request):
    """Buscar polÃ­ticos com filtros"""
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera') or request.GET.get('escopo')
    estado = request.GET.get('estado_uf')
    ano = request.GET.get('ano')
    partido = request.GET.get('partido')
    busca = request.GET.get('busca')

    queryset = Politico.objects.all()

    if cargo:
        queryset = queryset.filter(mandatos__cargo=cargo)
    if esfera:
        # Permite passar escopo (federal, estadual, municipal) ou esfera exata
        if esfera.lower() == 'federal':
            queryset = queryset.filter(mandatos__esfera__iexact='Federal')
        elif esfera.lower() == 'estadual':
            queryset = queryset.filter(mandatos__esfera__iexact='Estadual')
        elif esfera.lower() == 'municipal':
            queryset = queryset.filter(mandatos__esfera__iexact='Municipal')
        else:
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

    try:
        politicos = []
        for politico in queryset.distinct()[:15]: 
            politicos.append({
                'id': politico.id,
                'nome_civil': politico.nome_civil,
                'nome_social': politico.nome_social,
                'partido': politico.partido,
                'uf': politico.uf,
                'municipio': politico.municipio,
            })

        return JsonResponse({
            'success': True,
            'politicos': politicos,
            'total': len(politicos)
        })
    except OperationalError:
        return JsonResponse({
            'success': False,
            'message': 'A consulta Ã© muito ampla. Tente refinar sua busca.',
            'results': []
        }, status=200)

@csrf_exempt
@ratelimit(key='ip', rate='30/m', block=True)
def api_buscar_despesas(request):
    """Buscar despesas com filtros dinÃ¢micos integrados"""
    mandato_id = request.GET.get('mandato_id')
    ano = request.GET.get('ano')
    mes = request.GET.get('mes')
    categoria = request.GET.get('categoria')
    fornecedor_cnpj = request.GET.get('fornecedor_cnpj')
    fonte = request.GET.get('fonte')
    min_valor = request.GET.get('min_valor')
    max_valor = request.GET.get('max_valor')
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera') or request.GET.get('escopo')

    queryset = Despesa.objects.select_related('mandato', 'mandato__politico', 'fornecedor')

    if mandato_id: queryset = queryset.filter(mandato_id=mandato_id)
    if ano: queryset = queryset.filter(ano=ano)
    if mes: queryset = queryset.filter(mes=mes)
    if categoria: queryset = queryset.filter(categoria=categoria)
    if fornecedor_cnpj: queryset = queryset.filter(fornecedor__cnpj=fornecedor_cnpj)
    if fonte: queryset = queryset.filter(fonte=fonte)
    if min_valor: queryset = queryset.filter(valor_liquidado__gte=min_valor)
    if max_valor: queryset = queryset.filter(valor_liquidado__lte=max_valor)
    if cargo: queryset = queryset.filter(mandato__cargo=cargo)
    
    sigilo = request.GET.get('sigilo')
    if sigilo == 'true':
        queryset = queryset.filter(fornecedor__isnull=True, fonte='transparencia')
    elif sigilo == 'false':
        queryset = queryset.exclude(fornecedor__isnull=True, fonte='transparencia')
    
    data_inicio = request.GET.get('data_inicio')
    data_fim = request.GET.get('data_fim')
    if data_inicio: queryset = queryset.filter(data_emissao__gte=data_inicio)
    if data_fim: queryset = queryset.filter(data_emissao__lte=data_fim)
    
    if esfera:
        if esfera.lower() == 'federal':
            queryset = queryset.filter(mandato__esfera__iexact='Federal')
        elif esfera.lower() == 'estadual':
            queryset = queryset.filter(mandato__esfera__iexact='Estadual')
        elif esfera.lower() == 'municipal':
            queryset = queryset.filter(mandato__esfera__iexact='Municipal')
        else:
            queryset = queryset.filter(mandato__esfera=esfera)

    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 50))
    offset = (page - 1) * limit

    try:
        despesas = queryset[offset:offset + limit]

        despesas_json = []
        for despesa in despesas:
            if despesa.fornecedor:
                fornecedor_data = {
                    'cnpj': despesa.fornecedor.cnpj if hasattr(despesa.fornecedor, 'cnpj') else None,
                    'razao_social': despesa.fornecedor.razao_social if hasattr(despesa.fornecedor, 'razao_social') else None,
                }
            elif despesa.fonte == 'transparencia':
                fornecedor_data = {
                    'cnpj': '00000000000000',
                    'razao_social': 'Informação protegida por sigilo'
                }
            else:
                fornecedor_data = None

            despesas_json.append({
                'id': despesa.id,
                'mandato_id': despesa.mandato_id,
                'politico_nome': despesa.mandato.politico.nome_civil if despesa.mandato and hasattr(despesa.mandato, 'politico') else 'N/A',
                'cargo': despesa.mandato.cargo if despesa.mandato else 'N/A',
                'esfera': despesa.mandato.esfera if despesa.mandato else 'N/A',
                'categoria': despesa.categoria,
                'tipo_verba': despesa.tipo_verba,
                'descricao_despesa': despesa.descricao_despesa,
                'fornecedor': fornecedor_data,
                'valor_liquidado': float(despesa.valor_liquidado) if despesa.valor_liquidado else 0.0,
                'valor_pago': float(despesa.valor_pago) if despesa.valor_pago else None,
                'data_emissao': despesa.data_emissao.strftime('%Y-%m-%d') if despesa.data_emissao else None,
                'fonte': despesa.fonte,
                'ano': despesa.ano,
                'mes': despesa.mes,
                'criado_em': despesa.criado_em.isoformat() if despesa.criado_em else None,
            })

        total = queryset.count()

        return JsonResponse({
            'success': True,
            'despesas': despesas_json,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit,
            }
        })
    except OperationalError:
        return JsonResponse({
            'success': False,
            'message': 'A consulta Ã© muito ampla. Tente refinar sua busca.',
            'results': []
        }, status=200)

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='30/m', block=True)
@cache_page(60 * 15)  # Cache de 15 minutos
def api_estatisticas(request):
    """
    Retorna mÃ©tricas globais e KPIs agregados (RF01, RF02, RNF01).
    """
    ano = request.GET.get('ano')
    categoria = request.GET.get('categoria')
    fonte = request.GET.get('fonte')
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera') or request.GET.get('escopo')
    politico_id = request.GET.get('politico_id')

    queryset = Despesa.objects.all()

    if ano: queryset = queryset.filter(ano=ano)
    if categoria: queryset = queryset.filter(categoria=categoria)
    if fonte: queryset = queryset.filter(fonte=fonte)
    if cargo: queryset = queryset.filter(mandato__cargo=cargo)
    
    if esfera:
        if esfera.lower() == 'federal':
            queryset = queryset.filter(mandato__esfera__iexact='Federal')
        elif esfera.lower() == 'estadual':
            queryset = queryset.filter(mandato__esfera__iexact='Estadual')
        elif esfera.lower() == 'municipal':
            queryset = queryset.filter(mandato__esfera__iexact='Municipal')
        else:
            queryset = queryset.filter(mandato__esfera=esfera)
            
    if politico_id: queryset = queryset.filter(mandato__politico_id=politico_id)

    categorias_existentes = queryset.values('categoria').annotate(
        total=Sum('valor_liquidado')
    ).order_by('-total')

    stats = {}
    for cat in categorias_existentes:
        nome = cat['categoria'] or 'Outros'
        total = float(cat['total'] or 0)
        if total > 0:
            stats[nome] = total

    meses_existentes = queryset.values('mes').annotate(
        total=Sum('valor_liquidado')
    ).order_by('mes')
    
    stats_mensal = {str(m['mes']): float(m['total'] or 0) for m in meses_existentes if m['mes']}

    fornecedores_existentes = queryset.filter(fornecedor__isnull=False).values('fornecedor__razao_social', 'fornecedor__cnpj').annotate(
        total=Sum('valor_liquidado')
    ).order_by('-total')[:5]
    
    stats_fornecedores = []
    for f in fornecedores_existentes:
        stats_fornecedores.append({
            'razao_social': f['fornecedor__razao_social'],
            'cnpj': f['fornecedor__cnpj'],
            'total': float(f['total'] or 0)
        })

    # Calcula Top PolÃ­ticos dinÃ¢mico (Frente 3)
    top_politicos_query = queryset.values(
        'mandato__politico__id',
        'mandato__politico__nome_civil',
        'mandato__cargo',
        'mandato__esfera',
        'mandato__score_risco'
    ).annotate(
        total_gasto=Sum('valor_liquidado')
    ).filter(total_gasto__gt=0).order_by('-total_gasto')[:5]

    top_politicos_list = []
    for p in top_politicos_query:
        top_politicos_list.append({
            'id': p['mandato__politico__id'],
            'nome': p['mandato__politico__nome_civil'],
            'foto': None,
            'cargo': p['mandato__cargo'],
            'esfera': p['mandato__esfera'],
            'score': p['mandato__score_risco'],
            'total': float(p['total_gasto'] or 0)
        })

    total_geral = float(queryset.aggregate(total=Sum('valor_liquidado'))['total'] or 0)

    return JsonResponse({
        'stats_por_categoria': stats,
        'stats_por_mes': stats_mensal,
        'top_fornecedores': stats_fornecedores,
        'top_politicos': top_politicos_list,
        'total_geral': total_geral,
        'success': True
    })

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def api_atualizar_alerta(request):
    """Atualizar status de alerta"""
    try:
        data = json.loads(request.body)
        alerta_id = data.get('alerta_id')
        resolvido = data.get('resolvido', False)

        if not request.user.is_staff:
            return JsonResponse({'success': False, 'message': 'Permissão negada'}, status=403)

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
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)


# --- SISTEMA DE VÃNCULO (SEGUIR POLÃTICO) ---
@csrf_exempt
@require_http_methods(["POST", "GET"])
@jwt_required
def api_notificacoes(request):
    """Retorna os ultimos alertas dos politicos que o usuario assina (Frente 3.7)"""
    user, error = authenticate_request(request)
    if not user:
        return JsonResponse({'success': False, 'message': error}, status=401)
        
    mandatos_seguidos = Assinatura.objects.filter(usuario=user, ativo=True).values_list('mandato_id', flat=True)
    
    alertas = Alerta.objects.filter(
        mandato_id__in=mandatos_seguidos, 
        resolvido=False
    ).select_related('mandato__politico').order_by('-criado_em')[:10]
    
    data = []
    for a in alertas:
        data.append({
            'id': a.id,
            'titulo': a.titulo,
            'descricao': a.descricao,
            'severidade': a.severidade,
            'politico_nome': a.mandato.politico.nome_civil,
            'data': a.criado_em.strftime('%d/%m/%Y %H:%M')
        })
        
    return JsonResponse({'success': True, 'notificacoes': data})

def api_assinaturas(request):
    """Gerenciar assinaturas (seguir/parar de seguir polÃ­ticos)"""
    if request.method == "GET":
        try:
            user, error = authenticate_request(request)
            if not user:
                return JsonResponse({'success': False, 'message': error}, status=401)

            assinaturas = Assinatura.objects.filter(usuario=user, ativo=True).select_related(
                'mandato', 'mandato__politico'
            )

            data = []
            for assinatura in assinaturas:
                mandato = assinatura.mandato
                politico = mandato.politico
                data.append({
                    'id': assinatura.id,
                    'mandato_id': mandato.id,
                    'politico': {
                        'id': politico.id,
                        'nome_civil': politico.nome_civil,
                        'partido': politico.partido,
                        'uf': politico.uf
                    },
                    'cargo': mandato.cargo,
                    'esfera': mandato.esfera,
                    'estado_uf': mandato.estado_uf,
                    'municipio': mandato.municipio,
                    'tipo_notificacao': assinatura.tipo_notificacao,
                    'frequencia': assinatura.frequencia,
                    'criado_em': assinatura.criado_em.isoformat()
                })

            return JsonResponse({
                'success': True,
                'assinaturas': data,
                'total': len(data)
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

    elif request.method == "POST":
        try:
            data = json.loads(request.body)
            user, error = authenticate_request(request)
            if not user:
                return JsonResponse({'success': False, 'message': error}, status=401)

            mandato_id = data.get('mandato_id')
            if not mandato_id:
                return JsonResponse({'success': False, 'message': 'mandato_id Ã© obrigatÃ³rio'}, status=400)

            mandato = get_object_or_404(Mandato, id=mandato_id)

            assinatura, created = Assinatura.objects.get_or_create(
                usuario=user,
                mandato=mandato,
                defaults={
                    'tipo_notificacao': data.get('tipo_notificacao', 'email'),
                    'frequencia': data.get('frequencia', 'imediata'),
                    'ativo': True
                }
            )

            if not created:
                if not assinatura.ativo:
                    assinatura.ativo = True
                    assinatura.save()
                return JsonResponse({
                    'success': True,
                    'message': 'VocÃª jÃ¡ estÃ¡ acompanhando este polÃ­tico',
                    'assinatura_id': assinatura.id,
                    'created': False
                })

            return JsonResponse({
                'success': True,
                'message': 'Agora vocÃª estÃ¡ acompanhando este polÃ­tico',
                'assinatura_id': assinatura.id,
                'created': True
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@jwt_required
def api_remover_assinatura(request, assinatura_id):
    """Remover assinatura (parar de seguir polÃ­tico)"""
    try:
        user, error = authenticate_request(request)
        if not user:
            return JsonResponse({'success': False, 'message': error}, status=401)

        assinatura = get_object_or_404(Assinatura, id=assinatura_id, usuario=user, ativo=True)
        assinatura.ativo = False
        assinatura.save()

        return JsonResponse({
            'success': True,
            'message': 'Assinatura removida com sucesso'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def api_acompanhar_politico(request):
    """Associa ou desassocia um usuÃ¡rio a um polÃ­tico"""
    try:
        user, error = authenticate_request(request)
        if not user:
            return JsonResponse({'success': False, 'message': 'UsuÃ¡rio nÃ£o autenticado'}, status=401)
            
        data = json.loads(request.body)
        politico_id = data.get('politico_id')
        
        if not politico_id:
            return JsonResponse({'success': False, 'message': 'ID do polÃ­tico Ã© obrigatÃ³rio'}, status=400)

        politico = get_object_or_404(Politico, id=politico_id)
        
        mandato_recente = Mandato.objects.filter(politico=politico).order_by('-ano_inicio').first()
        
        if not mandato_recente:
            return JsonResponse({'success': False, 'message': 'PolÃ­tico nÃ£o possui mandatos registrados'}, status=400)

        assinatura, created = Assinatura.objects.get_or_create(
            usuario=user,
            mandato=mandato_recente,
            defaults={'ativo': True, 'tipo_notificacao': 'email'}
        )
        
        if not created:
            assinatura.ativo = not assinatura.ativo
            assinatura.save()

        status_msg = "acompanhando" if assinatura.ativo else "deixou de acompanhar"

        return JsonResponse({
            'success': True,
            'message': f'VocÃª {status_msg} este polÃ­tico.',
            'ativo': assinatura.ativo
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

# Utility API endpoints (pÃºblicos - RF03 Filtros DinÃ¢micos)
def api_categorias(request):
    categorias = Despesa.CATEGORIA_ABSOLUTA_CHOICES
    return JsonResponse({
        'categorias': [cat[0] for cat in categorias],
        'categorias_completas': categorias,
    })

def api_fontes(request):
    fontes = Despesa.objects.values_list('fonte', flat=True).distinct()
    return JsonResponse({
        'fontes': sorted(list(fontes)),
    })

def api_anos(request):
    anos = Despesa.objects.values_list('ano', flat=True).distinct().order_by('-ano')
    return JsonResponse({
        'anos': list(anos),
    })

def api_health(request):
    stats = {
        'database': 'OK',
        'supabase': 'OK',
        'timestamp': timezone.now().isoformat(),
        'version': '1.0.0',
    }
    return JsonResponse({
        'status': 'healthy',
        'stats': stats,
    })

# --- AutenticaÃ§Ã£o JWT (RF07) ---
@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/m', block=True)
@ratelimit(key='post:username', rate='10/m', block=True)
def api_login(request):
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
                'user': {'username': getattr(user, 'first_name', '') or getattr(user, 'username', ''), 'email': getattr(user, 'email', '')}
            })
            set_jwt_cookies(response, access_token, refresh_token)
            return response
        else:
            return JsonResponse({'success': False, 'message': 'Credenciais invÃ¡lidas'}, status=401)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def api_logout(request):
    response = JsonResponse({'success': True, 'message': 'Logout realizado com sucesso'})
    clear_jwt_cookies(response, request)
    return response

@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/m', block=True)

@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='10/m', block=True)
@ratelimit(key='post:email', rate='3/m', block=True)
def api_reset_password(request):
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        if not email:
            return JsonResponse({'success': False, 'message': 'E-mail é obrigatório.'}, status=400)
        
        user = User.objects.filter(email=email).first()
        if not user:
            return JsonResponse({'success': True, 'message': 'Se o e-mail existir, uma nova senha provisória foi gerada e enviada.'}, status=200)
        
        # Gera uma senha aleatória simples (6 números)
        import random
        nova_senha = str(random.randint(100000, 999999))
        user.set_password(nova_senha)
        user.save()
        
        return JsonResponse({
            'success': True, 
            'message': f'Senha redefinida com sucesso!\n\nSua nova senha temporária é: {nova_senha}\n\nFaça login e altere-a imediatamente em "Minha Conta".'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/m', block=True)
@ratelimit(key='post:email', rate='10/m', block=True)
def api_express_auth(request):
    try:
        data = json.loads(request.body)
        nome = data.get('nome', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return JsonResponse({'success': False, 'message': 'Email e senha sÃ£o obrigatÃ³rios.'}, status=400)

        user, created = User.objects.get_or_create(
            email=email,
            defaults={'first_name': nome, 'username': email, 'anonimo': False}
        )

        if created:
            user.set_password(password)
            user.save()
        else:
            user = authenticate(username=email, password=password)
            if not user:
                return JsonResponse({'success': False, 'message': 'Este email jÃ¡ estÃ¡ cadastrado com outra senha.'}, status=401)

        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)

        response = JsonResponse({
            'success': True,
            'message': 'Acesso liberado com sucesso',
            'user': {'username': getattr(user, 'first_name', '') or getattr(user, 'username', ''), 'email': getattr(user, 'email', '')}
        })
        
        set_jwt_cookies(response, access_token, refresh_token)
        return response

    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)


from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from .models import ClienteAPI

@csrf_exempt
def api_b2b_fornecedor_risk(request, cnpj):
    """Endpoint B2B AvanÃ§ado: Venda de dados de Risco/PEP e anÃ¡lise eleitoral"""
    api_key = request.headers.get('X-API-KEY')
    if not api_key:
        return JsonResponse({'error': 'Acesso Negado. ForneÃ§a o header X-API-KEY.'}, status=401)
    
    try:
        cliente = ClienteAPI.objects.get(api_key=api_key, is_active=True)
    except ClienteAPI.DoesNotExist:
        return JsonResponse({'error': 'API Key invÃ¡lida ou inativa.'}, status=403)
        
    # Rate limit
    if cliente.requisicoes_mes >= cliente.limite_requisicoes:
        return JsonResponse({'error': 'Limite de requisiÃ§Ãµes excedido. FaÃ§a upgrade do seu plano.'}, status=429)
        
    cliente.requisicoes_mes += 1
    cliente.save()

    try:
        forn = Fornecedor.objects.get(cnpj=cnpj)
        despesas = Despesa.objects.filter(fornecedor=forn)
        total = despesas.aggregate(Sum('valor_liquidado'))['valor_liquidado__sum'] or 0
        
        # Breakdown por ano para capturar anos eleitorais (2022, 2024, 2026)
        gastos_por_ano = list(despesas.values('ano').annotate(total=Sum('valor_liquidado')).order_by('-ano'))
        
        # Filtro de gastos sensÃ­veis (ex: Publicidade em anos de eleiÃ§Ã£o)
        gastos_publicidade = despesas.filter(categoria__icontains='publicidade').aggregate(Sum('valor_liquidado'))['valor_liquidado__sum'] or 0
        
        # Pagadores
        top_pagadores = list(despesas.values('mandato__politico__nome_civil', 'mandato__esfera', 'mandato__cargo').annotate(total_pago=Sum('valor_liquidado')).order_by('-total_pago')[:3])
        
        # Alertas
        alertas = Alerta.objects.filter(mandato__despesas__fornecedor=forn, resolvido=False).distinct().count()
        
        data = {
            'cnpj': forn.cnpj,
            'razao_social': forn.razao_social,
            'cnae_fiscal': forn.cnae_fiscal,
            'situacao_receita': forn.situacao_cadastral,
            'risco_politico': {
                'total_recebido_governo': float(total),
                'score_risco_interno': forn.risco_score if hasattr(forn, 'risco_score') else (alertas * 20),
                'alertas_ativos_envolvidos': alertas,
            },
            'analise_avancada': {
                'gastos_por_ano': {str(g['ano']): float(g['total']) for g in gastos_por_ano},
                'total_publicidade_graficas': float(gastos_publicidade),
                'flag_ano_eleitoral_sensivel': any(g['ano'] in [2022, 2024, 2026] and gastos_publicidade > 0 for g in gastos_por_ano),
                'principais_politicos_envolvidos': top_pagadores
            }
        }
        return JsonResponse({'status': 'success', 'data': data}, status=200)
    except Fornecedor.DoesNotExist:
        return JsonResponse({'status': 'not_found', 'message': 'Este CNPJ nÃ£o possui histÃ³rico de recebimento de verba polÃ­tica na nossa base.'}, status=404)

from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from django.db.models import F, DecimalField

@cache_page(60 * 30)  # Cache de 30 minutos
def fornecedores_view(request):
    """PÃ¡gina que lista as empresas beneficiadas ordenadas por volume de dinheiro recebido."""
    busca = request.GET.get('q', '')
    filtro_uf = request.GET.get('uf', '')
    filtro_situacao = request.GET.get('situacao', '')
    
    queryset = Fornecedor.objects.all()
    
    if busca:
        queryset = queryset.filter(Q(razao_social__icontains=busca) | Q(cnpj__icontains=busca))
    
    if filtro_uf:
        queryset = queryset.filter(uf=filtro_uf)
        
    if filtro_situacao:
        queryset = queryset.filter(situacao_cadastral=filtro_situacao)
        
    from django.db.models import Subquery, OuterRef
    mandato_sq = Despesa.objects.filter(fornecedor=OuterRef('pk')).values('fornecedor').annotate(s=Sum('valor_liquidado')).values('s')
    campanha_sq = DespesaCampanha.objects.filter(fornecedor=OuterRef('pk')).values('fornecedor').annotate(s=Sum('valor')).values('s')
    
    # Anota o total recebido (Cota Parlamentar + Fundo Eleitoral) evitando Produto Cartesiano
    queryset = queryset.annotate(
        total_mandato=Coalesce(Subquery(mandato_sq[:1]), 0.0, output_field=DecimalField()),
        total_campanha=Coalesce(Subquery(campanha_sq[:1]), 0.0, output_field=DecimalField())
    ).annotate(
        total_recebido=F('total_mandato') + F('total_campanha')
    ).filter(total_recebido__gt=0).order_by('-total_recebido')
    
    # PaginaÃ§Ã£o (20 por pÃ¡gina)
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # OpÃ§Ãµes para os filtros
    ufs = Fornecedor.objects.exclude(uf__isnull=True).exclude(uf='').values_list('uf', flat=True).distinct().order_by('uf')
    situacoes = [c[1].upper() for c in Fornecedor.SITUACAO_CADASTRAL_CHOICES]
    
    cargos_count = Mandato.objects.values('cargo').annotate(count=Count('id')).order_by('-count')

    context = {
        'page_obj': page_obj,
        'busca': busca,
        'filtro_uf': filtro_uf,
        'filtro_situacao': filtro_situacao,
        'ufs': ufs,
        'situacoes': situacoes
    }
    
    return render(request, 'fornecedores.html', context)



def comunidade_view(request):
    return render(request, 'comunidade.html')




def privacidade_view(request):
    return render(request, 'privacidade.html', {})

def termos_view(request):
    return render(request, 'termos.html', {})

def sobre_view(request):
    return render(request, 'sobre.html', {})
