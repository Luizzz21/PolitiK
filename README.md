# PolitiK
Uma redenção àqueles que necessitam de visualizar as coisas com mais clareza, utilize o Politik, um dashboard BI em tempo real de gastos políticos.

## 🚀 Como fazer o Deploy (Produção)

O PolitiK está pronto para ser publicado em qualquer ambiente utilizando **Docker** e **Docker Compose**. A arquitetura conta com:
- **Django (Gunicorn)**: Servidor Web Backend e Frontend renderizado.
- **PostgreSQL**: Banco de Dados relacional.
- **Redis**: Fila de mensagens e Cache em memória.
- **Celery Worker**: Processamento assíncrono para consumir dados de governos.
- **Celery Beat**: Agendador de tarefas (Robô de enriquecimento B2B via Receita Federal, Ingestão Diária da Câmara, etc).

### Passos:
1. Instale o Docker e Docker Compose no seu servidor (VPS, AWS, DigitalOcean).
2. Clone o repositório:
   ```bash
   git clone https://github.com/Luizzz21/PolitiK.git
   cd PolitiK
   ```
3. Suba toda a infraestrutura:
   ```bash
   docker-compose up -d --build
   ```
4. O servidor vai automaticamente aplicar as migrações no banco, coletar arquivos estáticos e iniciar na porta `8000`. Acesse `http://seu-ip:8000`.

## 🤖 Automações e Inteligência de Dados
O PolitiK conta com um conjunto de scripts que rodam em *background*:
- Motor de Anomalias de Gastos (executado para cada nota fiscal nova).
- Motor de Enriquecimento de CNPJs (Cruza dados de ReceitaWS / BrasilAPI).
- Integração Cota Parlamentar (Câmara e Senado) e Portal da Transparência (Executivo).
- Extensão Open Source para TCEs Estaduais (`CONTRIBUTING_ESTADOS.md`).
