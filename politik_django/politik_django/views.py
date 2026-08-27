"""
PolitiK - Django Views for Political Transparency Platform
APIs following RF01-RF07 requirements
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from django.db.models import Sum, Count, Q, Avg
from django.utils import timezone
from datetime import datetime, timedelta
import json
import traceback

from django.contrib.auth import authenticate, get_user_model
from .auth import create_access_token, create_refresh_token, set_jwt_cookies, clear_jwt_cookies, jwt_required, authenticate_request

from .models import (
    Politico, Mandato, Fornecedor, Despesa, Alerta, Usuario, Assinatura,
    Configuracao
)
from .business_rules import NegocioRegras

# Carrega o modelo de usuário correto (Custom User Model) definido no settings.py
User = get_user_model()

# Frontend Views

def ranking_view(request):
    sort_by = request.GET.get('sort', '-score_risco')
    allowed_sorts = ['-score_risco', '-total_gasto', 'politico__nome_civil']
    if sort_by not in allowed_sorts:
        sort_by = '-score_risco'
        
    mandatos = Mandato.objects.select_related('politico').all()
    
    # Calculate sum if needed, but we already have total_gasto property possibly? Wait, models.py has a field or property?
    # Let's annotate total_gasto if it's not a field.
    from django.db.models import Sum, F, DecimalField, Value
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    mandatos = mandatos.annotate(
        total_gasto=Coalesce(Sum('despesas__valor_liquidado'), Value(Decimal('0.00')), output_field=DecimalField())
    ).order_by(sort_by)[:100]
    
    context = {
        'mandatos': mandatos,
        'current_sort': sort_by
    }
    return render(request, 'ranking.html', context)


def despesas_view(request):
    return render(request, 'despesas.html')

def index(request):
    """Main dashboard view (RF06 - Dynamic Filters)"""
    try:
        ano_atual_config = Configuracao.objects.get(chave='ANO_ATUAL')
        ano_atual = int(ano_atual_config.valor_numerico)
    except:
        ano_atual = datetime.now().year

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

    # Calcula Top Gastadores (Ranking)
    top_gastadores = Mandato.objects.annotate(
        total_gasto=Sum('despesas__valor_liquidado')
    ).filter(total_gasto__gt=0).order_by('-total_gasto')[:5]

    cargos = set(Mandato.objects.values_list('cargo', flat=True))
    esferas = set(Mandato.objects.values_list('esfera', flat=True))
    anos = set(Despesa.objects.values_list('ano', flat=True).order_by('-ano'))
    
    categorias = list(NegocioRegras.CATEGORIAS_ABSOLUTAS.keys()) + ['Outros']

    context = {
        'stats': stats,
        'top_gastadores': top_gastadores,
        'cargos': sorted(cargos),
        'esferas': sorted(esferas),
        'anos': sorted(anos),
        'categorias': sorted(categorias),
        'ano_atual': ano_atual,
    }

    return render(request, 'index.html', context)

def fornecedor_detail(request, cnpj):
    """Perfil individual do fornecedor e análise de risco (Frente 3.4)"""
    fornecedor = get_object_or_404(Fornecedor, cnpj=cnpj)
    
    # Agregações de despesas
    despesas = Despesa.objects.filter(fornecedor=fornecedor).select_related('mandato__politico')
    
    total_recebido = despesas.aggregate(total=Sum('valor_liquidado'))['total'] or 0.0
    
    # Maiores pagadores (políticos)
    pagadores = despesas.values(
        'mandato__politico__id', 
        'mandato__politico__nome_civil', 
        'mandato__cargo', 
        'mandato__esfera'
    ).annotate(total_pago=Sum('valor_liquidado')).order_by('-total_pago')
    
    context = {
        'fornecedor': fornecedor,
        'total_recebido': total_recebido,
        'pagadores': pagadores,
        'despesas_recentes': despesas.order_by('-data_emissao')[:50]
    }
    return render(request, 'fornecedor_detail.html', context)

def pagina_politico(request, politico_id):
    """Detailed view for a specific politician (Dossiê)"""
    politico = get_object_or_404(Politico, id=politico_id)
    mandatos = Mandato.objects.filter(politico=politico)
    
    despesas_politico = (
        Despesa.objects
        .select_related('fornecedor')
        .filter(mandato__in=mandatos)
        .order_by('-data_emissao')
    )
    
    is_following = False
    user, error = authenticate_request(request)
    if user:
        is_following = Assinatura.objects.filter(usuario=user, mandato__in=mandatos, ativo=True).exists()

    context = {
        'politico': politico,
        'mandatos': mandatos,
        'despesas_politico': despesas_politico,
        'is_following': is_following,
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
    alertas = Alerta.objects.select_related('mandato', 'mandato__politico').order_by('-criado_em')

    context = {
        'alertas': alertas,
        'alertas_nao_resolvidos': alertas.filter(resolvido=False),
    }

    return render(request, 'alertas.html', context)

def pagina_minha_conta(request):
    """Painel do usuário logado: lista os políticos que acompanha"""
    user, error = authenticate_request(request)
    if not user:
        return redirect('index')

    assinaturas = Assinatura.objects.filter(
        usuario=user, ativo=True
    ).select_related(
        'mandato', 'mandato__politico'
    ).order_by('-criado_em')

    context = {
        'user': user,
        'assinaturas': assinaturas,
    }
    return render(request, 'minha_conta.html', context)

# API Endpoints (JSON responses)
@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_buscar_politicos(request):
    """Buscar políticos com filtros"""
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera')
    estado = request.GET.get('estado_uf')
    ano = request.GET.get('ano')
    partido = request.GET.get('partido')
    busca = request.GET.get('busca')

    queryset = Politico.objects.all()

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
        'politicos': politicos,
        'total': len(politicos)
    })

@csrf_exempt
@require_http_methods(["GET", "POST"])
def api_buscar_despesas(request):
    """Buscar despesas com filtros dinâmicos integrados"""
    mandato_id = request.GET.get('mandato_id')
    ano = request.GET.get('ano')
    mes = request.GET.get('mes')
    categoria = request.GET.get('categoria')
    fornecedor_cnpj = request.GET.get('fornecedor_cnpj')
    fonte = request.GET.get('fonte')
    min_valor = request.GET.get('min_valor')
    max_valor = request.GET.get('max_valor')
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera')

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
    if esfera: queryset = queryset.filter(mandato__esfera=esfera)

    page = int(request.GET.get('page', 1))
    limit = int(request.GET.get('limit', 50))
    offset = (page - 1) * limit

    despesas = queryset[offset:offset + limit]

    despesas_json = []
    for despesa in despesas:
        despesas_json.append({
            'id': despesa.id,
            'mandato_id': despesa.mandato_id,
            'politico_nome': despesa.mandato.politico.nome_civil if despesa.mandato and hasattr(despesa.mandato, 'politico') else 'N/A',
            'cargo': despesa.mandato.cargo if despesa.mandato else 'N/A',
            'esfera': despesa.mandato.esfera if despesa.mandato else 'N/A',
            'categoria': despesa.categoria,
            'tipo_verba': despesa.tipo_verba,
            'descricao_despesa': despesa.descricao_despesa,
            'fornecedor': {
                'cnpj': despesa.fornecedor.cnpj if hasattr(despesa.fornecedor, 'cnpj') else None,
                'razao_social': despesa.fornecedor.razao_social if hasattr(despesa.fornecedor, 'razao_social') else None,
            } if despesa.fornecedor else None,
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
        'despesas': despesas_json,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit,
        }
    })

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='10/s', block=True)
def api_estatisticas(request):
    """
    Retorna métricas globais e KPIs agregados (RF01, RF02, RNF01).
    """
    ano = request.GET.get('ano')
    categoria = request.GET.get('categoria')
    fonte = request.GET.get('fonte')
    cargo = request.GET.get('cargo')
    esfera = request.GET.get('esfera')
    politico_id = request.GET.get('politico_id')

    queryset = Despesa.objects.all()

    if ano: queryset = queryset.filter(ano=ano)
    if categoria: queryset = queryset.filter(categoria=categoria)
    if fonte: queryset = queryset.filter(fonte=fonte)
    if cargo: queryset = queryset.filter(mandato__cargo=cargo)
    if esfera: queryset = queryset.filter(mandato__esfera=esfera)
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

    fornecedores_existentes = queryset.filter(fornecedor__isnull=False).values('fornecedor__razao_social').annotate(
        total=Sum('valor_liquidado')
    ).order_by('-total')[:5]
    
    stats_fornecedores = {f['fornecedor__razao_social']: float(f['total'] or 0) for f in fornecedores_existentes}

    # Calcula Top Políticos dinâmico (Frente 3)
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


# --- SISTEMA DE VÍNCULO (SEGUIR POLÍTICO) ---
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
    """Gerenciar assinaturas (seguir/parar de seguir políticos)"""
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
                return JsonResponse({'success': False, 'message': 'mandato_id é obrigatório'}, status=400)

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
                    'message': 'Você já está acompanhando este político',
                    'assinatura_id': assinatura.id,
                    'created': False
                })

            return JsonResponse({
                'success': True,
                'message': 'Agora você está acompanhando este político',
                'assinatura_id': assinatura.id,
                'created': True
            })
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@jwt_required
def api_remover_assinatura(request, assinatura_id):
    """Remover assinatura (parar de seguir político)"""
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
    """Associa ou desassocia um usuário a um político"""
    try:
        user, error = authenticate_request(request)
        if not user:
            return JsonResponse({'success': False, 'message': 'Usuário não autenticado'}, status=401)
            
        data = json.loads(request.body)
        politico_id = data.get('politico_id')
        
        if not politico_id:
            return JsonResponse({'success': False, 'message': 'ID do político é obrigatório'}, status=400)

        politico = get_object_or_404(Politico, id=politico_id)
        
        mandato_recente = Mandato.objects.filter(politico=politico).order_by('-ano_inicio').first()
        
        if not mandato_recente:
            return JsonResponse({'success': False, 'message': 'Político não possui mandatos registrados'}, status=400)

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
            'message': f'Você {status_msg} este político.',
            'ativo': assinatura.ativo
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

# Utility API endpoints (públicos - RF03 Filtros Dinâmicos)
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

# --- Autenticação JWT (RF07) ---
@csrf_exempt
@require_http_methods(["POST"])
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
            return JsonResponse({'success': False, 'message': 'Credenciais inválidas'}, status=401)
    except Exception as e:
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'message': f'Erro interno: {str(e)}'}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
def api_logout(request):
    response = JsonResponse({'success': True, 'message': 'Logout realizado com sucesso'})
    clear_jwt_cookies(response)
    return response

@csrf_exempt
@require_http_methods(["POST"])
def api_express_auth(request):
    try:
        data = json.loads(request.body)
        nome = data.get('nome', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return JsonResponse({'success': False, 'message': 'Email e senha são obrigatórios.'}, status=400)

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
                return JsonResponse({'success': False, 'message': 'Este email já está cadastrado com outra senha.'}, status=401)

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

