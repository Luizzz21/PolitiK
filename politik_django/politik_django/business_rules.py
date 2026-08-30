"""
PolitiK - Business Rules Module
Implements RF03-RF05: Categorization, Anomaly Detection, Volume Triggers
"""

import re
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from .models import Despesa, Fornecedor, Mandato, Alerta, Configuracao


class NegocioRegras:
    """
    Centralized business rules for the PolitiK platform
    Following requirements in order: RF03, RF04, RF05
    """

    # --- Batch-processing cache (primed by anomaly_engine) ---
    _CACHE_LIMITES: Dict[str, Any] = None

    # RF03 - Categorização de Gastos: Categorias Absolutas Obrigatórias
    CATEGORIAS_ABSOLUTAS = {
        'Cota Parlamentar': [
            'COTA PARLAMENTAR', 'MANUTENCAO', 'MANUTENÇÃO', 'ALUGUEL', 'LOCAÇÃO',
            'MATERIAL DE EXPEDIENTE', 'CONSUMO DE ÁGUA', 'ENERGIA ELÉTRICA',
            'SERVIÇOS POSTAIS', 'TELEFONIA', 'INTERNET', 'MATERIAIS',
            'ESCRITORIO', 'ESCRITÓRIO', 'CONDOMINIO', 'CONDOMÍNIO'
        ],
        'Emendas Pix': [
            'EMENDA PIX', 'TRANSFERENCIA ESPECIAL', 'TRANSFERÊNCIA ESPECIAL', 'CONVÊNIO',
            'EMENDA PIX INDIVIDUAL', 'EMENDA PIX DE BANCO'
        ],
        'Emendas de Comissão': [
            'EMENDA DE COMISSÃO', 'EMENDA DE BANCO', 'EMENDA DE RELATOR'
        ],
        'Salários': [
            'SALARIO', 'SALÁRIO', 'REMUNERAÇÃO', 'REMUNERACAO', 'PROVENTOS',
            'APOSENTADORIA', 'PENSÃO', 'PENSAO', '13º SALARIO', '13º SALÁRIO',
            'FÉRIAS', 'FERIAS', 'GRATIFICAÇÃO', 'GRATIFICACAO'
        ],
        'Auxílio-Moradia': [
            'AUXILIO MORADIA', 'AUXÍLIO MORADIA', 'ALUGUEL RESIDENCIAL', 'MORADIA',
            'AUXÍLIO-MORADIA', 'AUXILIO-MORADIA'
        ],
        'Combustíveis e Lubrificantes': [
            'COMBUSTIVEL', 'COMBUSTÍVEL', 'GASOLINA', 'ETANOL', 'DIESEL',
            'LUBRIFICANTE', 'ÓLEO DIESEL', 'OLEO DIESEL', 'GNV',
            'POSTO DE COMBUSTIVEL', 'POSTO DE COMBUSTÍVEL'
        ],
        'Passagens Aéreas': [
            'PASSAGEM AEREA', 'PASSAGEM AÉREA', 'EMBARQUE', 'DESCOLAGEM', 'POUSSO',
            'TARIFA AEREA', 'TARIFA AÉREA', 'BILHETE AEREO', 'BILHETE AÉREO'
        ],
        'Consultorias e Pesquisas': [
            'CONSULTORIA', 'ASSESSORIA', 'PESQUISA', 'ESTUDO', 'LAUDO', 'PARECER',
            'CONSULTOR', 'ASSESSOR', 'PESQUISADOR'
        ],
        'Serviços de Saúde': [
            'SAUDE', 'SAÚDE', 'HOSPITAL', 'CLINICA', 'CLÍNICA', 'CONSULTA',
            'EXAME', 'PROCEDIMENTO', 'MEDICAMENTO', 'FARMACIA', 'FARMÁCIA',
            'LABORATORIO', 'LABORATÓRIO'
        ],
        'Educação': [
            'EDUCAÇÃO', 'EDUCACAO', 'ESCOLA', 'UNIVERSIDADE', 'CURSO',
            'CAPACITAÇÃO', 'CAPACITACAO', 'TREINAMENTO', 'PALESTRA',
            'SEMINARIO', 'SEMINÁRIO', 'CONGRESSO', 'WORKSHOP'
        ]
    }

    # RF05 - Gatilhos de Volume: Limites Padrão
    LIMITES_PADRAO = {
        'combustivel_litros_diarios': 50,  # litros - capacidade média de tanque
        'combustivel_preco_medio': 6.5,    # R$/litro
        'emendas_pix_mensais': 100000,     # R$
        'material_expediente_limite': 5000,  # R$
        'consultorias_limite': 100000,     # R$
        'servicos_saude_limite': 50000,    # R$
        'passagens_limite_mensal': 30000,  # R$
        'salarios_limite_mensal': 50000,   # R$
    }

    @staticmethod
    def obter_categoria_absoluta(descricao: str) -> str:
        """
        RF03 - Categorização absoluta obrigatória
        Mapeia descrições para as 11 categorias absolutas definidas
        """
        if not descricao:
            return 'Outros'

        descricao_upper = descricao.upper().strip()

        # Verificação especial para CEAP
        if 'CEAP' in descricao_upper:
            return 'Cota Parlamentar'

        # Mapeamento por palavras-chave (ordem de prioridade)
        for categoria, palavras_chave in NegocioRegras.CATEGORIAS_ABSOLUTAS.items():
            for palavra in palavras_chave:
                if palavra in descricao_upper:
                    return categoria

        return 'Outros'

    @staticmethod
    def verificar_anomalia_cnpj(fornecedor: Fornecedor, valor_despesa: float, data_emissao: datetime = None) -> Tuple[bool, str]:
        """
        RF04 - Motor de Anomalias
        Verifica CNPJ contra base da Receita Federal usando dados locais enriquecidos
        Retorna (is_anomalous, reason)
        """
        cnpj = fornecedor.cnpj
        if not cnpj or len(cnpj) != 14:
            return False, "CNPJ inválido"

        # Validação básica de formato
        if not cnpj.isdigit():
            return False, "CNPJ contém caracteres inválidos"

        # Verificação de situação cadastral
        situacao = fornecedor.situacao_cadastral
        if situacao and situacao.upper() in ['BAIXADA', 'INAPTA', 'SUSPENSA', 'NULA']:
            return True, f"Empresa com situação cadastral suspeita: {situacao}"

        # Verificação 2.1: CNPJ Frio - Empresa com menos de 3 meses faturando alto
        if fornecedor.data_abertura and data_emissao:
            dias_abertura = (data_emissao - fornecedor.data_abertura).days
            if 0 <= dias_abertura < 90 and valor_despesa > 5000:
                return True, f"Empresa recém-criada (aberta há {dias_abertura} dias da emissão) recebendo R$ {valor_despesa:,.2f}"

        # Verificação 2.2: CNPJ Frio - Despesa maior que 3x o Capital Social
        if fornecedor.capital_social and fornecedor.capital_social > 0:
            if float(valor_despesa) > float(fornecedor.capital_social) * 3:
                return True, f"Despesa (R$ {valor_despesa:,.2f}) excede 3x o Capital Social (R$ {fornecedor.capital_social:,.2f})"

        # Padrões numéricos suspeitos (Fallback de dados ausentes)
        if len(set(cnpj)) <= 3:
            return True, "CNPJ com dígitos repetidos (padrão suspeito)"

        if cnpj.endswith('0000'):
            return True, "CNPJ com muitos zeros finais (suspeito)"

        if cnpj in ['12345678901234', '00000000000000', '11111111111111']:
            return True, "CNPJ com padrão de teste/inválido"

        return False, ""

    @staticmethod
    def verificar_triggers_volume(categoria: str, valor: float, descricao: str = "",
                                  data_emissao=None, despesa=None) -> Tuple[bool, str, str]:
        """
        RF05 - Gatilhos de Volume
        Gera alertas para gastos que ultrapassem limites matemáticos lógicos
        Retorna (is_triggered, alert_type, message)
        """
        if not categoria or valor <= 0:
            return False, "", ""

        categoria_upper = categoria.upper()
        descricao_upper = descricao.upper() if descricao else ""

        # Obter limites da configuração
        limites = NegocioRegras._obter_limites_configuracao()

        # 1. Gatilho específico para Combustíveis
        # Refinado: Volume suspeito = (limite diário) * (dias desde a última nota de combustível)
        if 'COMBUSTIVEL' in categoria_upper or 'COMBUSTIVEL' in descricao_upper:
            limite_diario = limites['combustivel_litros_diarios'] * limites['combustivel_preco_medio']
            dias_acumulados = 1
            
            if despesa and despesa.mandato and despesa.data_emissao:
                from .models import Despesa
                ultima_despesa = Despesa.objects.filter(
                    mandato=despesa.mandato,
                    categoria=despesa.categoria,
                    data_emissao__lt=despesa.data_emissao
                ).order_by('-data_emissao').first()
                
                if ultima_despesa and ultima_despesa.data_emissao:
                    delta = (despesa.data_emissao - ultima_despesa.data_emissao).days
                    dias_acumulados = max(1, delta)
                else:
                    # Se não houver nota anterior, assumimos um acúmulo de 15 dias de tolerância
                    dias_acumulados = 15

            limite_total = limite_diario * dias_acumulados
            if valor > limite_total:
                return True, 'volume', f'Combustível: R$ {valor:.2f} (Acumulado de {dias_acumulados} dia(s). Limite tolerado: R$ {limite_total:.2f}).'

        # 2. Gatilho para Emendas Pix
        if 'EMENDA' in categoria_upper and 'PIX' in categoria_upper:
            if valor > limites['emendas_pix_mensais']:
                return True, 'volume', f'Emenda Pix acima do limite mensal: R$ {valor:.2f}'

        # 3. Gatilhos específicos por categoria
        gatilhos_categoria = {
            'Material de Expediente': (limites['material_expediente_limite'], 'Material de expediente excessivo'),
            'Consultorias e Pesquisas': (limites['consultorias_limite'], 'Consultoria suspeitamente alta'),
            'Serviços de Saúde': (limites['servicos_saude_limite'], 'Serviço de saúde excessivo'),
            'Passagens Aéreas': (limites['passagens_limite_mensal'], 'Passagens aéreas excessivas'),
            'Salários': (limites['salarios_limite_mensal'], 'Salário acima do limite'),
        }

        if categoria in gatilhos_categoria:
            limite, mensagem = gatilhos_categoria[categoria]
            if valor > limite:
                return True, 'anomalia', f'{mensagem}: R$ {valor:.2f}'

        # 4. Verificação de volume por dia (para despesas diárias)
        if data_emissao:
            limite_diario = NegocioRegras._calcular_limite_diario(categoria, valor)
            if limite_diario and valor > limite_diario:
                return True, 'volume', f'Volume diário suspeito para {categoria}: R$ {valor:.2f}'

        return False, "", ""

    @staticmethod
    def _calcular_limite_diario(categoria: str, valor: float) -> Optional[float]:
        """
        Calcula limite diário baseado na categoria
        """
        # Limites diários por categoria (valores aproximados)
        limites_diarios = {
            'Combustíveis e Lubrificantes': 50 * 6.5,  # 50 litros * R$ 6,5
            'Alimentação': 200,  # R$ 200/dia (valor razoável)
            'Hospedagem': 500,   # R$ 500/dia
            'Locomoção': 300,    # R$ 300/dia
        }

        for cat, limite in limites_diarios.items():
            if cat.upper() in categoria.upper():
                return limite

        return None

    @staticmethod
    def _obter_limites_configuracao() -> Dict[str, Any]:
        """
        Obtém limites da configuração do sistema
        """
        limites = NegocioRegras.LIMITES_PADRAO.copy()

        # Cache de lote: se o motor de processamento em lote já carregou os
        # limites, reutiliza para evitar N+1 queries dentro do loop.
        if NegocioRegras._CACHE_LIMITES is not None:
            return NegocioRegras._CACHE_LIMITES.copy()

        try:
            configs = Configuracao.objects.all()
            for config in configs:
                chave = config.chave
                valor = config.valor_numerico

                if chave == 'LIMITE_VOLUME_COMBUSTIVEL' and isinstance(valor, (int, float)):
                    limites['combustivel_litros_diarios'] = int(valor)
                elif chave == 'LIMITE_EMENDAS_PIX' and isinstance(valor, (int, float)):
                    limites['emendas_pix_mensais'] = float(valor)
                elif chave == 'LIMITE_MATERIAL_EXPEDIENTE' and isinstance(valor, (int, float)):
                    limites['material_expediente_limite'] = float(valor)
                elif chave == 'LIMITE_CONSULTORIAS' and isinstance(valor, (int, float)):
                    limites['consultorias_limite'] = float(valor)
        except Exception:
            pass  # Usa padrões se houver erro

        return limites

    # --- Cache helpers for batch processing ---
    @classmethod
    def definir_cache_limites(cls, limites: Dict[str, Any]) -> None:
        """Prime the limits cache for a batch run (avoids per-record DB queries)."""
        cls._CACHE_LIMITES = limites

    @staticmethod
    def verificar_concentracao_fornecedor(mandato) -> Tuple[bool, str, float, str]:
        """
        RF05 - Concentração (> 60% do mandato em 1 fornecedor)
        """
        from django.db.models import Sum
        total_mandato = Despesa.objects.filter(mandato=mandato).aggregate(t=Sum('valor_liquidado'))['t'] or 0.0
        
        if total_mandato < 50000:
            return False, "", 0.0, None
            
        top_fornecedor = Despesa.objects.filter(mandato=mandato, fornecedor__isnull=False).values(
            'fornecedor__cnpj', 'fornecedor__razao_social'
        ).annotate(total=Sum('valor_liquidado')).order_by('-total').first()
        
        if top_fornecedor:
            total_top = top_fornecedor['total'] or 0.0
            percentual = (total_top / total_mandato) * 100
            if percentual >= 60.0:
                nome_forn = top_fornecedor.get('fornecedor__razao_social')
                cnpj_forn = top_fornecedor.get('fornecedor__cnpj')
                display_name = nome_forn if nome_forn else (f"o CNPJ {cnpj_forn}" if cnpj_forn else "fornecedor não identificado")
                msg = f"Concentração anômala: {percentual:.1f}% dos gastos (R$ {total_top:,.2f}) foram para {display_name}."
                return True, msg, float(total_top), cnpj_forn
                
        return False, "", 0.0, None

    @staticmethod
    def verificar_spike_anormal(despesa) -> Tuple[bool, str]:
        """
        RF05 - Spike Anormal (Gasto do mês atual é 3x maior que a média histórica dos meses anteriores)
        """
        if not despesa.data_emissao or not despesa.mandato_id:
            return False, ""
            
        from django.db.models import Sum
        from datetime import date
        
        ano, mes = despesa.data_emissao.year, despesa.data_emissao.month
        
        gasto_mes_atual = float(Despesa.objects.filter(
            mandato=despesa.mandato,
            data_emissao__year=ano,
            data_emissao__month=mes
        ).aggregate(t=Sum('valor_liquidado'))['t'] or 0.0)
        
        if gasto_mes_atual < 20000:
            return False, ""
            
        meses_passados = Despesa.objects.filter(
            mandato=despesa.mandato,
            data_emissao__lt=date(ano, mes, 1)
        ).values('data_emissao__year', 'data_emissao__month').annotate(total=Sum('valor_liquidado'))
        
        if len(meses_passados) < 3:
            return False, ""
            
        soma_historico = sum(float(m['total']) for m in meses_passados)
        media_historica = soma_historico / len(meses_passados)
        
        if media_historica > 5000 and gasto_mes_atual >= (media_historica * 3.0):
            return True, f"Spike Anormal: Gasto do mês {mes}/{ano} (R$ {gasto_mes_atual:,.2f}) é {gasto_mes_atual/media_historica:.1f}x maior que a média histórica (R$ {media_historica:,.2f})."
            
        return False, ""

    @staticmethod
    def calcular_e_atualizar_score(mandato) -> int:
        """
        F2.10 - Recalcula o score de risco do mandato com base nos alertas vivos (não resolvidos).
        """
        alertas = Alerta.objects.filter(mandato=mandato, resolvido=False)
        
        score = 0
        for a in alertas:
            if 'CNPJ' in a.titulo or 'Situação Cadastral' in a.titulo or a.referencia_cnpj:
                score += 30
            elif a.severidade == 'critica':
                score += 20
            elif a.severidade == 'alta':
                score += 10
            else:
                score += 5
                
        score = min(score, 100)
        
        if mandato.score_risco != score:
            mandato.score_risco = score
            mandato.save(update_fields=['score_risco'])
            
        return score

    @classmethod
    def limpar_cache_limites(cls) -> None:
        """Clear the limits cache after a batch run."""
        cls._CACHE_LIMITES = None

    @staticmethod
    def verificar_fracionamento(despesa: Despesa) -> Tuple[bool, str, float]:
        """
        RF05 - Verifica fracionamento de despesa (lei de licitação)
        Agrupa todas as despesas daquele mandato para aquele fornecedor no MESMO DIA.
        Retorna (is_fracionado, message, soma_dia).
        """
        if not despesa.data_emissao or not despesa.mandato_id or not despesa.fornecedor_id:
            return False, "", 0.0

        from django.db.models import Sum
        
        # Filtra despesas do mesmo fornecedor, no mesmo mandato e no mesmo dia
        soma = Despesa.objects.filter(
            mandato=despesa.mandato,
            fornecedor=despesa.fornecedor,
            data_emissao=despesa.data_emissao
        ).exclude(pk=despesa.pk).aggregate(total=Sum('valor_liquidado'))['total'] or 0.0
        
        # Soma o valor da despesa atual
        soma_dia = float(soma) + float(despesa.valor_liquidado)
        
        # O limite da lei 8.666 para dispensa é R$ 8.000 a 17.600. Usaremos 8.000 como gatilho.
        if soma_dia >= 8000.0:
            count = Despesa.objects.filter(
                mandato=despesa.mandato,
                fornecedor=despesa.fornecedor,
                data_emissao=despesa.data_emissao
            ).exclude(pk=despesa.pk).count()
            
            if count > 0:
                data_str = despesa.data_emissao.strftime("%d/%m/%Y")
                return True, f"Fracionamento suspeito: {count + 1} despesas no dia {data_str} totalizando R$ {soma_dia:,.2f}", soma_dia
                
        return False, "", 0.0

    @staticmethod
    def processar_despesa_com_validacao(despesa: Despesa) -> Tuple[bool, list]:
        """
        Processa uma despesa aplicando todas as validações
        Retorna (success, lista_de_alertas_gerados)
        """
        alertas_gerados = []

        # 1. RF03 - Categorização automática se não definida
        if not despesa.categoria or despesa.categoria == 'Outros':
            categoria_sugerida = NegocioRegras.obter_categoria_absoluta(
                despesa.tipo_verba or despesa.descricao_despesa or ''
            )
            if categoria_sugerida != 'Outros':
                despesa.categoria = categoria_sugerida

        # 2. RF04 - Verificar anomalia no CNPJ do fornecedor
        if despesa.fornecedor and despesa.fornecedor.cnpj:
            is_anomalous, motivo = NegocioRegras.verificar_anomalia_cnpj(
                despesa.fornecedor,
                float(despesa.valor_liquidado),
                despesa.data_emissao
            )
            if is_anomalous:
                alerta, created = Alerta.objects.get_or_create(
                    mandato=despesa.mandato,
                    tipo='anomalia',
                    severidade='media',
                    titulo=f'Anomalia detectada no CNPJ do fornecedor',
                    descricao=f'CNPJ {despesa.fornecedor.cnpj}: {motivo}',
                    valor_real=despesa.valor_liquidado,
                    referencia_cnpj=despesa.fornecedor.cnpj
                )
                alertas_gerados.append(alerta)

        # 3. RF05 - Verificar triggers de volume
        is_triggered, tipo_alerta, mensagem = NegocioRegras.verificar_triggers_volume(
            despesa.categoria,
            float(despesa.valor_liquidado),
            despesa.tipo_verba or despesa.descricao_despesa or '',
            despesa.data_emissao,
            despesa
        )
        if is_triggered:
            alerta, created = Alerta.objects.get_or_create(
                mandato=despesa.mandato,
                tipo=tipo_alerta,
                severidade='alta' if tipo_alerta == 'volume' else 'media',
                titulo=f'Alerta de {tipo_alerta} detectado',
                descricao=mensagem,
                valor_trigger=NegocioRegras._obter_limite_trigger(despesa.categoria),
                valor_real=despesa.valor_liquidado
            )
            alertas_gerados.append(alerta)

        # 4. F2.3 - Verificar Fracionamento de despesas no mesmo dia
        if despesa.pk is None: # Se for nova inserção
            # Precisamos salvar primeiro para poder agregar, mas aqui só lemos o passado
            is_frac, msg_frac, soma_frac = NegocioRegras.verificar_fracionamento(despesa)
            if is_frac:
                alerta, created = Alerta.objects.get_or_create(
                    mandato=despesa.mandato,
                    tipo='suspeita',
                    severidade='critica',
                    titulo='Possível Fracionamento de Despesa',
                    descricao=msg_frac,
                    valor_trigger=8000,
                    valor_real=soma_frac,
                )
                alertas_gerados.append(alerta)
                
            # F2.7 - Verificar Despesa Duplicada
            if despesa.fornecedor and despesa.data_emissao and despesa.valor_liquidado:
                duplicadas = Despesa.objects.filter(
                    mandato=despesa.mandato,
                    fornecedor=despesa.fornecedor,
                    data_emissao=despesa.data_emissao,
                    valor_liquidado=despesa.valor_liquidado
                ).exclude(pk=despesa.pk).count()
                if duplicadas > 0:
                    alerta, created = Alerta.objects.get_or_create(
                        mandato=despesa.mandato,
                        tipo='suspeita',
                        severidade='alta',
                        titulo='Despesa Duplicada',
                        descricao=f'Despesa idêntica (mesmo fornecedor, data e valor exato de R$ {despesa.valor_liquidado:.2f}) lançada {duplicadas} vez(es) anterior(es).',
                        valor_real=despesa.valor_liquidado,
                    )
                    alertas_gerados.append(alerta)

        # F2.4 - Gasto em Dia Não Útil (Fim de Semana)
        if despesa.data_emissao:
            dia_semana = despesa.data_emissao.weekday()
            # 5 = Sábado, 6 = Domingo
            if dia_semana in [5, 6] and despesa.categoria not in ['Hospedagem', 'Passagens Aéreas', 'Alimentação', 'Cota Parlamentar']:
                # Alimentação e hospedagem podem ser válidas. Consultoria/Material em domingo é estranho.
                alerta, created = Alerta.objects.get_or_create(
                    mandato=despesa.mandato,
                    tipo='suspeita',
                    severidade='media',
                    titulo='Gasto em Fim de Semana',
                    descricao=f'Despesa da categoria "{despesa.categoria}" emitida num {"Domingo" if dia_semana == 6 else "Sábado"}.',
                    valor_real=despesa.valor_liquidado,
                )
                alertas_gerados.append(alerta)

        # F2.5 - Inconsistência Geográfica
        if despesa.fornecedor and despesa.fornecedor.uf and despesa.mandato.estado_uf:
            # Categorias estritamente locais
            cats_locais = ['Combustíveis e Lubrificantes', 'Serviços de Saúde', 'Alimentação']
            if despesa.categoria in cats_locais and despesa.fornecedor.uf != despesa.mandato.estado_uf:
                # Exceção comum: Brasília (DF) para mandatos federais
                if not (despesa.mandato.esfera == 'Federal' and despesa.fornecedor.uf == 'DF'):
                    alerta, created = Alerta.objects.get_or_create(
                        mandato=despesa.mandato,
                        tipo='suspeita',
                        severidade='alta',
                        titulo='Inconsistência Geográfica',
                        descricao=f'Agente de {despesa.mandato.estado_uf} realizou despesa local ({despesa.categoria}) no estado de {despesa.fornecedor.uf}.',
                        valor_real=despesa.valor_liquidado,
                        referencia_cnpj=despesa.fornecedor.cnpj
                    )
                    alertas_gerados.append(alerta)

        # F2.8 - Vínculo Societário / Parentesco
        if despesa.fornecedor and despesa.fornecedor.quadro_societario and despesa.mandato and despesa.mandato.politico:
            politico = despesa.mandato.politico
            nome_politico_parts = politico.nome_civil.upper().split()
            # Pega o último sobrenome do político (mais propenso a matching familiar)
            if len(nome_politico_parts) > 1:
                sobrenome_politico = nome_politico_parts[-1]
                
                # Procura no QSA
                for socio in despesa.fornecedor.quadro_societario:
                    nome_socio = socio.get('nome', '').upper()
                    
                    # Evita match em nomes muito curtos como "DA", "SILVA" é muito comum mas vamos deixar por enquanto
                    if len(sobrenome_politico) > 3 and sobrenome_politico in nome_socio:
                        alerta, created = Alerta.objects.get_or_create(
                            mandato=despesa.mandato,
                            tipo='suspeita',
                            severidade='alta',
                            titulo='Possível Vínculo Societário/Parentesco',
                            descricao=f'O sócio "{socio.get("nome")}" possui o sobrenome "{sobrenome_politico}" do político.',
                            valor_real=despesa.valor_liquidado,
                            referencia_cnpj=despesa.fornecedor.cnpj
                        )
                        alertas_gerados.append(alerta)
                        break # Um alerta por despesa já basta para F2.8

        # 5. F2.9 - Verificar Spike Anormal
        if despesa.pk is None:
            is_spike, msg_spike = NegocioRegras.verificar_spike_anormal(despesa)
            if is_spike:
                spike_exist = Alerta.objects.filter(mandato=despesa.mandato, titulo='Spike Anormal Detectado', resolvido=False).exists()
                if not spike_exist:
                    alerta, created = Alerta.objects.get_or_create(
                        mandato=despesa.mandato,
                        tipo='volume',
                        severidade='alta',
                        titulo='Spike Anormal Detectado',
                        descricao=msg_spike,
                        valor_real=despesa.valor_liquidado
                    )
                    alertas_gerados.append(alerta)

        # Salvar despesa
        despesa.save()

        return True, alertas_gerados

    @staticmethod
    def _obter_limite_trigger(categoria: str) -> float:
        """Obtém o limite de trigger para uma categoria"""
        limites = NegocioRegras._obter_limites_configuracao()

        gatilhos = {
            'Combustíveis e Lubrificantes': limites['combustivel_litros_diarios'] * limites['combustivel_preco_medio'],
            'Emendas Pix': limites['emendas_pix_mensais'],
            'Material de Expediente': limites['material_expediente_limite'],
            'Consultorias e Pesquisas': limites['consultorias_limite'],
            'Serviços de Saúde': limites['servicos_saude_limite'],
            'Passagens Aéreas': limites['passagens_limite_mensal'],
            'Salários': limites['salarios_limite_mensal'],
        }

        return gatilhos.get(categoria, 0)

    @staticmethod
    def gerar_relatorio_anomalias(mandato_id: int = None) -> Dict[str, Any]:
        """
        Gera relatório de anomalias para análise
        """
        queryset = Despesa.objects.all()
        if mandato_id:
            queryset = queryset.filter(mandato_id=mandato_id)

        # Categorias com mais despesas
        por_categoria = queryset.values('categoria').annotate(
            total=Sum('valor_liquidado'),
            count=Count('id')
        ).order_by('-total')

        # Fornecedores com mais gastos
        por_fornecedor = queryset.values(
            'fornecedor_cnpj'
        ).annotate(
            total=Sum('valor_liquidado'),
            count=Count('id')
        ).order_by('-total')[:20]

        # Alertas ativos
        alertas_queryset = Alerta.objects.filter(resolvido=False)
        if mandato_id:
            alertas_queryset = alertas_queryset.filter(mandato_id=mandato_id)

        alertas = alertas_queryset.values('tipo', 'severidade').annotate(
            count=Count('id')
        )

        return {
            'total_despesas': queryset.count(),
            'valor_total': float(queryset.aggregate(total=Sum('valor_liquidado'))['total'] or 0),
            'por_categoria': list(por_categoria),
            'top_fornecedores': list(por_fornecedor),
            'alertas_ativos': list(alertas),
        }


# Import Sum for aggregate
from django.db.models import Sum, Count