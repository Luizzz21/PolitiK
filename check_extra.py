import sys

filepath = 'd:/Documentos/Pessoal/Projetos/PolitiK/PolitiK/politik_django/templates/fornecedores.html'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()
if '{% block extra_head %}' not in content:
    print('extra_head NOT found')
    content = content.replace('{% block content %}', '{% block extra_head %}\n<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>\n{% endblock %}\n\n{% block content %}')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
else:
    print('extra_head found')
