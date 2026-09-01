# 🌎 PolitiK - Iniciativa de Transparência Estadual (Open Source)

Bem-vindo ao braço comunitário do **PolitiK**! 
Enquanto a esfera Federal (Câmara, Senado e Executivo) já possui APIs unificadas e estruturadas pelo nosso núcleo, o Brasil possui 26 Estados e o Distrito Federal. Cada Tribunal de Contas Estadual (TCE) e cada Assembleia Legislativa (ALE) possui um formato próprio de prestação de contas (alguns com APIs modernas, outros com PDFs escaneados ou tabelas HTML arcaicas).

É impossível manter 27 raspadores de dados atualizados sozinhos. É aqui que **você** entra.

## 🎯 O Objetivo
Nosso objetivo é ter um Adapter (Raspador) para cada estado na pasta politik_django/ingestao/tces/. 
Se o seu estado ainda não possui um adapter funcionando, você pode criar um e enviar um Pull Request!

## 🛠️ Como criar o Adapter do seu Estado

1. **Crie o arquivo do seu Estado**
   Crie um arquivo com a sigla do estado, ex: sc.py ou ce.py dentro de politik_django/ingestao/tces/.

2. **Implemente a Classe Coletora**
   Seu script deve herdar de TCEBaseCollector (veja base.py). O único método obrigatório que você precisa implementar com a lógica real de extração é o fetch_despesas().

3. **Homologação e Teste**
   Para testar seu coletor isoladamente, rode no terminal:
   python manage.py ingest_tces --uf SC --ano 2026

## 💡 Dicas de Engenharia
- **Não derrube os portais:** Coloque time.sleep(1) entre as requisições. 
- **Se não tiver API, faça Scraping:** Bibliotecas como BeautifulSoup (para HTML estático) ou Playwright (para portais que dependem de JavaScript) são muito bem-vindas.
- **Tratamento de Erros:** Englobe suas chamadas de rede em blocos try/except para não quebrar a rotina inteira se o site do governo do seu estado cair (o que acontece com frequência).

Obrigado por ajudar a vigiar os gastos públicos do Brasil! 🇧🇷

