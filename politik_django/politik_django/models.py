"""
PolitiK - Political Transparency Platform
Django Models following requirements in order: RF01-RF07
Then RNF01-RNF03 (Performance, Scalability, Security)
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.core.validators import RegexValidator
import json

# Validators
CNPJValidator = RegexValidator(
    regex=r'^\d{14}$',
    message='CNPJ deve ter 14 dígitos'
)

UFValidator = RegexValidator(
    regex=r'^[A-Z]{2}$',
    message='UF deve ser o código de 2 letras do estado'
)

class Politico(models.Model):
    """
    RF02 - Mapeamento Multiesfera: Política padronizada para todas esferas
    Armazena informações básicas sobre políticos
    """
    nome_civil = models.CharField(max_length=255, verbose_name="Nome Civil")
    nome_social = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nome Social")
    partido = models.CharField(max_length=100, blank=True, null=True, verbose_name="Partido")
    uf = models.CharField(max_length=2, blank=True, null=True, validators=[UFValidator], verbose_name="UF")
    municipio = models.CharField(max_length=100, blank=True, null=True, verbose_name="Município")
    data_nascimento = models.DateField(blank=True, null=True, verbose_name="Data de Nascimento")
    sexo = models.CharField(max_length=1, blank=True, null=True, choices=[('M', 'Masculino'), ('F', 'Feminino'), ('O', 'Outro')], verbose_name="Sexo")
    grau_instrucao = models.CharField(max_length=100, blank=True, null=True, verbose_name="Grau de Instrução")
    ocupacao = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ocupação")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Político"
        verbose_name_plural = "Políticos"
        ordering = ['nome_civil']
        db_table = 'politico'

    def __str__(self):
        return self.nome_civil

class Mandato(models.Model):
    """
    RF02 - Mapeamento Multiesfera: Todos os cargos padronizados
    Representa um mandato político específico
    """
    politico = models.ForeignKey(Politico, on_delete=models.CASCADE, related_name='mandatos', verbose_name="Político")

    # RF02: Cargo padronizado para todas esferas
    CARGO_CHOICES = [
        ('Presidente', 'Presidente'),
        ('Vice-Presidente', 'Vice-Presidente'),
        ('Governador', 'Governador'),
        ('Vice-Governador', 'Vice-Governador'),
        ('Senador', 'Senador'),
        ('Deputado Federal', 'Deputado Federal'),
        ('Deputado Estadual', 'Deputado Estadual'),
        ('Prefeito', 'Prefeito'),
        ('Vice-Prefeito', 'Vice-Prefeito'),
        ('Vereador', 'Vereador'),
        ('Ministro', 'Ministro'),
        ('Secretário', 'Secretário'),
        ('Secretário Municipal', 'Secretário Municipal'),
    ]

    cargo = models.CharField(max_length=50, choices=CARGO_CHOICES, verbose_name="Cargo")

    # Esfera de atuação (RF02)
    ESFERA_CHOICES = [
        ('Federal', 'Federal'),
        ('Estadual', 'Estadual'),
        ('Municipal', 'Municipal'),
    ]

    esfera = models.CharField(max_length=20, choices=ESFERA_CHOICES, verbose_name="Esfera")

    estado_uf = models.CharField(max_length=2, blank=True, null=True, validators=[UFValidator], verbose_name="UF")
    municipio = models.CharField(max_length=100, blank=True, null=True, verbose_name="Município")

    ano_inicio = models.IntegerField(blank=True, null=True, verbose_name="Ano de Início")
    ano_fim = models.IntegerField(blank=True, null=True, verbose_name="Ano de Fim")

    # Motor Anti-Corrupção - Score consolidado (0 a 100)
    score_risco = models.IntegerField(default=0, verbose_name="Score de Risco", help_text="0-100: Quanto maior, mais anomalias")

    created_at = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Mandato"
        verbose_name_plural = "Mandatos"
        db_table = 'mandato'
        unique_together = ['politico', 'cargo', 'ano_inicio']
        indexes = [
            models.Index(fields=['politico', 'cargo', 'esfera']),
        ]

    def __str__(self):
        return f"{self.politico.nome_civil} - {self.cargo} ({self.esfera})"

class Fornecedor(models.Model):
    """
    RF04 - CNPJ cross-reference: Base de empresas do governo
    Armazena informações de empresas que recebem recursos públicos
    """
    cnpj = models.CharField(max_length=14, unique=True, validators=[CNPJValidator], verbose_name="CNPJ")
    razao_social = models.CharField(max_length=255, verbose_name="Razão Social")
    nome_fantasia = models.CharField(max_length=255, blank=True, null=True, verbose_name="Nome Fantasia")

    # Situação cadastral (para verificação RF04)
    SITUACAO_CADASTRAL_CHOICES = [
        ('ATIVA', 'Ativa'),
        ('INAPTA', 'Inapta'),
        ('SUSPENSA', 'Suspensa'),
        ('BAIXADA', 'Baixada'),
        ('NULO', 'Nulo'),
    ]

    situacao_cadastral = models.CharField(max_length=50, blank=True, null=True, choices=SITUACAO_CADASTRAL_CHOICES, verbose_name="Situação Cadastral")
    data_situacao_cadastral = models.DateField(blank=True, null=True, verbose_name="Data Situação Cadastral")
    data_inicio_atividade = models.DateField(blank=True, null=True, verbose_name="Data Início Atividade")

    cnae_fiscal = models.CharField(max_length=20, blank=True, null=True, verbose_name="CNAE Fiscal")

    # Endereço
    logradouro = models.CharField(max_length=255, blank=True, null=True, verbose_name="Logradouro")
    numero = models.CharField(max_length=20, blank=True, null=True, verbose_name="Número")
    complemento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Complemento")
    bairro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Bairro")
    municipio = models.CharField(max_length=100, blank=True, null=True, verbose_name="Município")
    uf = models.CharField(max_length=2, blank=True, null=True, validators=[UFValidator], verbose_name="UF")
    cep = models.CharField(max_length=8, blank=True, null=True, verbose_name="CEP")

    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefone")
    email = models.CharField(max_length=255, blank=True, null=True, verbose_name="Email")

    natureza_juridica = models.CharField(max_length=200, blank=True, null=True, verbose_name="Natureza Jurídica")
    capital_social = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Capital Social")
    ultima_atualizacao_receita = models.DateTimeField(blank=True, null=True, verbose_name="Última consulta à Receita")
    
    quadro_societario = models.JSONField(blank=True, null=True, verbose_name="Quadro Societário (QSA)")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Fornecedor"
        verbose_name_plural = "Fornecedores"
        db_table = 'fornecedor'
        indexes = [
            models.Index(fields=['cnpj', 'situacao_cadastral']),
        ]

    def __str__(self):
        return f"{self.razao_social} ({self.cnpj})"

    @property
    def is_suspicious(self):
        """Check if supplier is suspicious (RF04)"""
        return self.situacao_cadastral in ['BAIXADA', 'INAPTA', 'SUSPENSA']

class Despesa(models.Model):
    """
    RF03 - Categorização de Gastos: Categorização absoluta obrigatória
    Registra todas as despesas com recursos públicos
    """
    mandato = models.ForeignKey(Mandato, on_delete=models.CASCADE, related_name='despesas', verbose_name="Mandato")
    fornecedor = models.ForeignKey(Fornecedor, on_delete=models.SET_NULL, blank=True, null=True, related_name='despesas', verbose_name="Fornecedor")

    # RF03: Categorias absolutas obrigatórias
    CATEGORIA_ABSOLUTA_CHOICES = [
        ('Cota Parlamentar', 'Cota Parlamentar'),
        ('Emendas Pix', 'Emendas Pix'),
        ('Emendas de Comissão', 'Emendas de Comissão'),
        ('Salários', 'Salários'),
        ('Auxílio-Moradia', 'Auxílio-Moradia'),
        ('Combustíveis e Lubrificantes', 'Combustíveis e Lubrificantes'),
        ('Passagens Aéreas', 'Passagens Aéreas'),
        ('Consultorias e Pesquisas', 'Consultorias e Pesquisas'),
        ('Serviços de Saúde', 'Serviços de Saúde'),
        ('Educação', 'Educação'),
        ('Outros', 'Outros'),
    ]

    categoria = models.CharField(max_length=100, choices=CATEGORIA_ABSOLUTA_CHOICES, verbose_name="Categoria")

    # Subcategoria adicional (não obrigatória)
    subcategoria = models.CharField(max_length=100, blank=True, null=True, verbose_name="Subcategoria")

    tipo_verba = models.CharField(max_length=255, verbose_name="Tipo de Verba")
    descricao_despesa = models.TextField(blank=True, null=True, verbose_name="Descrição da Despesa")
    numero_documento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Número do Documento")

    # Valores financeiros
    valor_liquidado = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor Liquidado")
    valor_empenhado = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Valor Empenhado")
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Valor Pago")
    valor_desconto = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Valor Desconto")

    # Datas
    data_emissao = models.DateField(verbose_name="Data de Emissão")
    data_pagamento = models.DateField(blank=True, null=True, verbose_name="Data de Pagamento")

    numero_parcela = models.IntegerField(blank=True, null=True, verbose_name="Número da Parcela")
    parcela = models.IntegerField(blank=True, null=True, verbose_name="Parcela")

    # Documentação
    url_documento = models.URLField(blank=True, null=True, verbose_name="URL do Documento")

    # Metadados
    fonte = models.CharField(max_length=50, verbose_name="Fonte")  # camara, senado, transparencia, tce
    ano = models.IntegerField(verbose_name="Ano")
    mes = models.IntegerField(blank=True, null=True, verbose_name="Mês")

    # RF04/RF05: rastreamento de processamento pelo motor de anomalias
    processado_em = models.DateTimeField(blank=True, null=True, verbose_name="Processado pelo Motor de Anomalias")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"
        db_table = 'despesa'
        ordering = ['-data_emissao', '-criado_em']
        indexes = [
            models.Index(fields=['mandato', 'ano', 'mes']),
            models.Index(fields=['categoria']),
            models.Index(fields=['valor_liquidado']),
            models.Index(fields=['-valor_liquidado']),
            models.Index(fields=['data_emissao']),
            models.Index(fields=['-data_emissao']),
            models.Index(fields=['fonte']),
            models.Index(fields=['processado_em', 'id']),
        ]

    def __str__(self):
        return f"{self.mandato.politico.nome_civil} - {self.categoria}: R$ {self.valor_liquidado:.2f}"

    @property
    def valor_total_pago(self):
        """Return total paid (valor_pago + valor_desconto)"""
        total = self.valor_pago or 0
        total += self.valor_desconto or 0
        return total

class Alerta(models.Model):
    """
    RF05 - Gatilhos de Volume: Alertas automáticos para limites suspeitos
    RF04 - Motor de Anomalias: Alertas para empresas suspeitas
    """
    TIPO_CHOICES = [
        ('anomalia', 'Anomalia'),
        ('volume', 'Volume'),
        ('suspeita', 'Suspeita'),
    ]

    mandato = models.ForeignKey(Mandato, on_delete=models.CASCADE, related_name='alertas', verbose_name="Mandato")

    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, verbose_name="Tipo")

    SEVERIDADE_CHOICES = [
        ('baixa', 'Baixa'),
        ('media', 'Média'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]

    severidade = models.CharField(max_length=20, choices=SEVERIDADE_CHOICES, verbose_name="Severidade")

    titulo = models.CharField(max_length=255, verbose_name="Título")
    descricao = models.TextField(verbose_name="Descrição")

    # Valores para referência
    valor_trigger = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Valor Trigger")
    valor_real = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Valor Real")

    referencia_cnpj = models.CharField(max_length=14, blank=True, null=True, verbose_name="CNPJ Referência")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    resolvido = models.BooleanField(default=False, verbose_name="Resolvido")
    resolvido_em = models.DateTimeField(blank=True, null=True, verbose_name="Resolvido em")

    class Meta:
        verbose_name = "Alerta"
        verbose_name_plural = "Alertas"
        db_table = 'alerta'
        ordering = ['-criado_em']
        indexes = [
            models.Index(fields=['tipo', 'severidade']),
            models.Index(fields=['criado_em']),
        ]

    def __str__(self):
        return f"{self.mandato.politico.nome_civil} - {self.titulo} ({self.get_tipo_display()})"

    def resolver(self):
        """Mark alert as resolved"""
        self.resolvido = True
        self.resolvido_em = timezone.now()
        self.save()

class Usuario(AbstractUser):
    """
    RF07 - Sistema de Inscrição/Alerta: Usuários (anonimos ou autenticados)
    Estende AbstractUser para suporte a autenticação
    """
    EMAIL_UNIQUE = models.BooleanField(default=True, verbose_name="Email Único")

    # Campos adicionais para perfil
    telefone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefone")
    preferencias = models.JSONField(default=dict, blank=True, verbose_name="Preferências")

    # RF07: Flag para identificar usuários anônimos vs autenticados
    anonimo = models.BooleanField(default=True, verbose_name="Anônimo")

    # Tracking
    ultimo_login = models.DateTimeField(blank=True, null=True, verbose_name="Último Login")

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        db_table = 'usuario'

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_anonymous_user(self):
        return self.anonimo

class Assinatura(models.Model):
    """
    RF07 - Sistema de Inscrição/Alerta: Inscrições de usuários
    Permite que usuários recebam notificações sobre políticos específicos
    """
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='assinaturas', verbose_name="Usuário")
    mandato = models.ForeignKey(Mandato, on_delete=models.CASCADE, related_name='assinaturas', verbose_name="Mandato")

    TIPO_NOTIFICACAO_CHOICES = [
        ('email', 'Email'),
        ('push', 'Push'),
        ('sms', 'SMS'),
    ]

    tipo_notificacao = models.CharField(max_length=20, choices=TIPO_NOTIFICACAO_CHOICES, default='email', verbose_name="Tipo de Notificação")

    FREQUENCIA_CHOICES = [
        ('imediata', 'Imediata'),
        ('diaria', 'Diária'),
        ('semanal', 'Semanal'),
    ]

    frequencia = models.CharField(max_length=20, choices=FREQUENCIA_CHOICES, default='imediata', verbose_name="Frequência")

    ativo = models.BooleanField(default=True, verbose_name="Ativo")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Assinatura"
        verbose_name_plural = "Assinaturas"
        db_table = 'assinatura'
        unique_together = ['usuario', 'mandato']

    def __str__(self):
        return f"{self.usuario.get_full_name()} assina {self.mandato.politico.nome_civil}"

class Configuracao(models.Model):
    """
    Configurações do sistema (RF05 - Gatilhos, RNF03 - Escalabilidade)
    """
    CHAVE_CHOICES = [
        ('LIMITE_VOLUME_COMBUSTIVEL', 'Limite Volume Combustível'),
        ('LIMITE_EMENDAS_PIX', 'Limite Emendas Pix'),
        ('CACHE_TTL_SEGUNDOS', 'Cache TTL segundos'),
        ('MAX_DEPUTADOS_POR_BATCH', 'Max Deputados por Batch'),
        ('TIMEOUT_API_SEGUNDOS', 'Timeout API segundos'),
        ('ANO_ATUAL', 'Ano Atual'),
    ]

    chave = models.CharField(max_length=50, choices=CHAVE_CHOICES, unique=True, verbose_name="Chave")
    valor = models.CharField(max_length=500, verbose_name="Valor")
    descricao = models.TextField(blank=True, null=True, verbose_name="Descrição")
    tipo = models.CharField(max_length=20, blank=True, null=True, verbose_name="Tipo")

    criado_em = models.DateTimeField(default=timezone.now, verbose_name="Criado em")
    atualizado_em = models.DateTimeField(auto_now=True, verbose_name="Atualizado em")

    class Meta:
        verbose_name = "Configuração"
        verbose_name_plural = "Configurações"
        db_table = 'configuracao'

    def __str__(self):
        return f"{self.get_chave_display()}: {self.valor}"

    @property
    def valor_numerico(self):
        """Tenta converter valor para número"""
        try:
            if self.tipo == 'integer':
                return int(self.valor)
            elif self.tipo == 'decimal':
                return float(self.valor)
            elif self.tipo == 'boolean':
                return self.valor.lower() in ['true', '1', 'sim']
        except (ValueError, TypeError):
            pass
        return self.valor


# Remover a classe NegocioRegras duplicada