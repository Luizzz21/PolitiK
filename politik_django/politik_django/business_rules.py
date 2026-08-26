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
    def verificar_anomalia_cnpj(cnpj: str, situacao_cadastral: str = None) -> Tuple[bool, str]:
        """
        RF04 - Motor de Anomalias
        Verifica CNPJ contra base da Receita Federal (simulado)
        Retorna (is_anomalous, reason)
        """
        if not cnpj or len(cnpj) != 14:
            return False, "CNPJ inválido"

        # Validação básica de formato
        if not cnpj.isdigit():
            return False, "CNPJ contém caracteres inválidos"

        # Verificação de situação cadastral (se fornecida)
        if situacao_cadastral and situacao_cadastral.upper() in ['BAIXADA', 'INAPTA', 'SUSPENSA', 'NULA']:
            return True, f"Empresa com situação cadastral suspeita: {situacao_cadastral}"

        # Verificação de padrões suspeitos
        # 1. Todos dígitos iguais
        if len(set(cnpj)) <= 3:
            return True, "CNPJ com dígitos repetidos (padrão suspeito)"

        # 2. Muitos zeros no final (padrão de empresas fantasmas)
        if cnpj.endswith('0000'):
            return True, "CNPJ com muitos zeros finais (suspeito)"

        # 3. Sequência numérica
        if cnpj in ['12345678901234', '00000000000000', '11111111111111',
                    '22222222222222', '33333333333333', '44444444444444',
                    '55555555555555', '66666666666666', '77777777777777',
                    '88888888888888', '99999999999999']:
            return True, "CNPJ com padrão de teste/inválido"

        # Na implementação real, aqui faria chamada à API da Receita Federal
        # para verificar situação cadastral, data de abertura, etc.

        return False, ""

    @staticmethod
    def verificar_triggers_volume(categoria: str, valor: float, descricao: str = "",
                                  data_emissao: datetime = None) -> Tuple[bool, str, str]:
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
        # Volume suspeito: mais que 50 litros/dia * preço médio
        if 'COMBUSTIVEL' in categoria_upper or 'COMBUSTIVEL' in descricao_upper:
            limite = limites['combustivel_litros_diarios'] * limites['combustivel_preco_medio']
            if valor > limite:
                return True, 'volume', f'Gasto de combustível suspeito: R$ {valor:.2f} (limite: R$ {limite:.2f}/dia)'

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

    @classmethod
    def limpar_cache_limites(cls) -> None:
        """Clear the limits cache after a batch run."""
        cls._CACHE_LIMITES = None

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
                despesa.fornecedor.cnpj,
                despesa.fornecedor.situacao_cadastral
            )
            if is_anomalous:
                alerta = Alerta.objects.create(
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
            despesa.data_emissao
        )
        if is_triggered:
            alerta = Alerta.objects.create(
                mandato=despesa.mandato,
                tipo=tipo_alerta,
                severidade='alta' if tipo_alerta == 'volume' else 'media',
                titulo=f'Alerta de {tipo_alerta} detectado',
                descricao=mensagem,
                valor_trigger=NegocioRegras._obter_limite_trigger(despesa.categoria),
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