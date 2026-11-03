"""Fórmulas de pontuação por formato de rodada (estilo WCA de cubo mágico).

Funções puras — listas de durações em ms e strings — sem banco, para o
smoke poder `import scoring` e testar direto.

Modelo de DNF/DNS por *preenchimento*: faltam tentativas válidas, a lista
ordenada é completada com `inf` até o tamanho do formato e os cortes
(melhor/pior) se aplicam sobre ela. Um `inf` que sobreviva à aparada
significa "sem resultado" — exatamente a regra WCA (Ao5 tolera 1 DNF,
Mo3 não tolera nenhum).
"""

import math

INF = float('inf')


def parse_mmss(valor):
    """'mm:ss' -> milissegundos; vazio/inválido -> None."""
    if not valor or ':' not in valor:
        return None
    partes = valor.split(':')
    try:
        minutos = int(partes[0])
        segundos = int(partes[1]) if len(partes) > 1 else 0
    except ValueError:
        return None
    if minutos < 0 or segundos < 0:
        return None
    return (minutos * 60 + segundos) * 1000


def _melhor(duracoes, n):
    """Bo1/Bo2/Bo3/Bo5: a mais rápida."""
    return min(duracoes) if duracoes else None


def _media_exata(duracoes, n):
    """Mo3: média de todas as N; qualquer falta anula."""
    if len(duracoes) < n:
        return None
    return round(sum(sorted(duracoes)[:n]) / n)


def _media_melhores_k(k):
    """Legado 'Média das 3 melhores, de 5': média das k mais rápidas."""
    def fn(duracoes, n):
        if len(duracoes) < k:
            return None
        return round(sum(sorted(duracoes)[:k]) / k)
    return fn


def _media_aparada(duracoes, n):
    """Ao5/Ao12: descarta a melhor e a pior (com DNFs como `inf` no fim),
    média do meio."""
    ordenadas = sorted(duracoes)[:n]
    preenchidas = ordenadas + [INF] * (n - len(ordenadas))
    meio = preenchidas[1:-1]
    if any(d == INF for d in meio):
        return None
    return round(sum(meio) / len(meio))


FORMULTAS = {
    'Melhor de 1 (Bo1)': (1, _melhor),
    'Melhor de 2 (Bo2)': (2, _melhor),
    'Melhor de 3 (Bo3)': (3, _melhor),
    'Média de 3 (Mo3)': (3, _media_exata),
    'Média de 5 aparada (Ao5)': (5, _media_aparada),
    'Média de 12 aparada (Ao12)': (12, _media_aparada),
    # Rótulos legados (já gravados em rodadas existentes):
    'Melhor de 5': (5, _melhor),
    'Média das 3 melhores, de 5': (5, _media_melhores_k(3)),
}


def n_tentativas(formato):
    """Quantas tentativas por atleta o formato pede; None se desconhecido."""
    entrada = FORMULTAS.get(formato)
    return entrada[0] if entrada else None


def score(duracoes, formato, corte_ms=None):
    """Tempo único do atleta. `duracoes` = tentativas concluídas em ms;
    acima de `corte_ms` (tempo máximo da rodada) a tentativa é eliminada."""
    entrada = FORMULTAS.get(formato)
    if entrada is None:
        return None
    n, fn = entrada
    validas = [d for d in duracoes if d is not None
               and (corte_ms is None or d <= corte_ms)]
    return fn(validas, n)


def classificar(pontuacoes, n_aprovados=None, percent=None):
    """(ranking, classificados). `pontuacoes` = [(id, ms), ...].
    n_aprovados tem prioridade sobre percent; empates na linha de corte
    avançam todos (regra WCA não desfaz empate por sorteio aqui)."""
    ranking = sorted(pontuacoes, key=lambda ps: (ps[1], ps[0]))
    if not ranking:
        return ranking, set()
    if n_aprovados is not None:
        limite = n_aprovados
    elif percent is not None:
        limite = math.ceil(len(ranking) * percent / 100)
    else:
        return ranking, set()
    if limite <= 0:
        return ranking, set()
    cortados = ranking[:limite]
    ultimo = cortados[-1][1]
    while len(cortados) < len(ranking) and ranking[len(cortados)][1] == ultimo:
        cortados.append(ranking[len(cortados)])
    return ranking, {chave for chave, _ in cortados}


def fmt_ms(ms):
    """ms -> 'm:ss.mmm' (formatação canônica de tempos do app)."""
    m, resto = divmod(int(ms), 60000)
    s, t = divmod(resto, 1000)
    return f'{m}:{s:02d}.{t:03d}'


def ranking_rows(rodada):
    """Linhas de ranking a partir dos objetos ORM de `rodada` (tentativas e
    inscrições) — só percorre/carrega; quem chama deve estar com a sessão
    ativa. Ordena por tempo; sem pontuação vai para o fim (por nome)."""
    corte = parse_mmss(rodada.tempo_maximo)
    atletas = {}
    for tentativa in rodada.tentativas:
        if tentativa.inscricao is None:
            continue
        info = atletas.setdefault(tentativa.inscricao_id,
                                  {'nome': '?', 'duracoes': [], 'geradas': 0})
        info['geradas'] += 1
        cadastro = tentativa.inscricao.cadastro
        if cadastro is not None:
            info['nome'] = cadastro.nome or cadastro.email or '?'
        if tentativa.situacao == 'Realizado' and tentativa.duracao is not None:
            info['duracoes'].append(tentativa.duracao)
    linhas = []
    for inscricao_id, info in atletas.items():
        validas = [d for d in info['duracoes'] if corte is None or d <= corte]
        linhas.append({'id': inscricao_id, 'nome': info['nome'],
                       'score': score(info['duracoes'], rodada.formato, corte),
                       'validas': len(validas), 'geradas': info['geradas']})
    linhas.sort(key=lambda l: (l['score'] is None, l['score'] or 0, l['nome']))
    return linhas
