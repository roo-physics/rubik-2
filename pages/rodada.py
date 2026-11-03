"""Rodada: configurações, tentativas agrupadas, liberação e sorteio de grupos."""

import random
from urllib.parse import quote

from fasthtml.common import *
from sqlmodel import col, delete, select

from auth import current_user, require_admin, require_login
from components.daisy import (btn, card, drow, dtable, field, page,
                                  select_field, toggle)
from db import get_session
from models import Inscricao, Rodada, Tentativa
from scoring import FORMULTAS, classificar, fmt_ms, n_tentativas, ranking_rows
from ws import manager

OPCOES_FORMATO = ['Melhor de 1 (Bo1)', 'Melhor de 2 (Bo2)', 'Melhor de 3 (Bo3)',
                  'Média de 3 (Mo3)', 'Média de 5 aparada (Ao5)',
                  'Média de 12 aparada (Ao12)',
                  'Média das 3 melhores, de 5', 'Melhor de 5']


def _norm_mmss(valor):
    """Normaliza a saída do flatpickr mm:ss ('2:5' -> '02:05'); vazio -> None."""
    if not valor:
        return None
    partes = valor.split(':')
    try:
        minutos = int(partes[0])
        segundos = int(partes[1]) if len(partes) > 1 else 0
    except ValueError:
        return None
    return f'{minutos:02d}:{segundos:02d}'


def _gerar_tentativas(session, rodada_id, inscricoes, maximo_grupo, n):
    """`n` tentativas por atleta, embaralhadas em grupos de até `maximo_grupo`."""
    if not inscricoes:
        return
    maximo_grupo = max(int(maximo_grupo or 5), 1)
    n_grupos = (len(inscricoes) + maximo_grupo - 1) // maximo_grupo
    sorteadas = random.sample(list(inscricoes), len(inscricoes))
    grupos = [sorteadas[i::n_grupos] for i in range(n_grupos)]
    for grupo, membros in enumerate(grupos):
        for inscricao in membros:
            for numero in range(1, n + 1):
                session.add(Tentativa(numero=numero, grupo=grupo,
                                      rodada_id=rodada_id,
                                      inscricao_id=inscricao.id,
                                      situacao='Aguardando Liberação'))


def _calcular_progressao(rodada):
    """Ranking + classificados (usado na prévia e na confirmação).

    {'ok': False, 'erro': msg} quando impossível, senão
    {'ok': True, formato, n, linhas, ids_classificados, aviso}."""
    if rodada.formato not in FORMULTAS:
        return {'ok': False, 'erro': f'O formato "{rodada.formato or "(vazio)"}" não tem '
                'fórmula de pontuação — escolha um formato válido na rodada.'}
    if not rodada.tentativas:
        return {'ok': False, 'erro': 'Esta rodada ainda não tem tentativas — '
                'use Redistribuir primeiro.'}
    if rodada.n_pessoas_aprovadas is None and rodada.percent_aprovados is None:
        return {'ok': False, 'erro': 'Nada quem avançar ainda — defina "Quem avança" '
                '(quantidade de aprovados ou percentual) na rodada.'}
    n = n_tentativas(rodada.formato)
    linhas = ranking_rows(rodada)
    pontuacoes = [(linha['id'], linha['score']) for linha in linhas
                  if linha['score'] is not None]
    if not pontuacoes:
        return {'ok': False, 'erro': 'Nenhuma tentativa concluída nesta rodada gera '
                'pontuação — registre tempos antes de avançar.'}
    _, classificados = classificar(pontuacoes, rodada.n_pessoas_aprovadas,
                                   rodada.percent_aprovados)
    aviso = None
    if any(linha['geradas'] < n for linha in linhas):
        aviso = (f'Atenção: as tentativas geradas não batem com o formato '
                 f'({n} por atleta) — use Redistribuir para realinhar.')
    return {'ok': True, 'formato': rodada.formato, 'n': n, 'linhas': linhas,
            'ids_classificados': sorted(classificados), 'aviso': aviso}


def _progressao_area(rodada_id, dados, resultado=None):
    """Fragmento `#progressao-area`: prévia (com confirmar), erro, ou resumo."""
    if resultado is not None:
        nova_id, n_class = resultado
        corpo = [Div(f'Rodada seguinte criada com {n_class} classificados.',
                     cls='font-bold'),
                 btn('Abrir nova rodada', href=f'/rodada/{nova_id}', color=None,
                     icon='arrow_forward')]
    elif not dados.get('ok', False):
        corpo = [Div(dados['erro'], cls='text-error font-bold')]
    else:
        linhas = [drow([str(i + 1), linha['nome'],
                        f"{linha['validas']}/{dados['n']} válidas",
                        fmt_ms(linha['score']) if linha['score'] is not None else 'sem resultado',
                        '✔ avança' if linha['id'] in dados['ids_classificados'] else '✗'])
                  for i, linha in enumerate(dados['linhas'])]
        corpo = [
            Div(f"Progressão — {dados['formato']}", cls='text-lg font-bold'),
            (Div(dados['aviso'], cls='text-warning') if dados['aviso'] else ''),
            dtable(['Pos.', 'Atleta', 'Tentativas', 'Tempo', 'Avanço'], linhas),
            btn('Confirmar progressão', icon='how_to_reg', color='warning',
                hx_post=f'/rodada/{rodada_id}/progressao/confirmar',
                hx_target='#progressao-area', hx_swap='outerHTML'),
        ]
    return Div(*corpo, id='progressao-area',
               cls='flex flex-col gap-2 p-4 bg-base-100 rounded-box shadow-sm')


def _celula_tentativa(t, eh_admin, rodada_id):
    """Célula de uma tentativa: estado legível + ações do admin."""
    situacao, duracao, inicio, tid = t
    if situacao == 'Cancelado':
        corpo = Span('✗ Cancelado', cls='text-error text-xs')
    elif situacao == 'Realizado' and duracao is not None:
        corpo = Span(fmt_ms(duracao), cls='font-mono')
    elif situacao == 'Liberado' and inicio is not None:
        corpo = Div(Span('0:00.000', cls='text-warning font-mono',
                         **{'x-data': f'relogio({inicio})', 'x-text': 'txt'}))
    elif situacao == 'Liberado':
        corpo = Span('Liberado', cls='badge badge-info badge-sm')
    else:
        corpo = Span('Aguardando Liberação', cls='badge badge-ghost badge-sm')
    pecas = [corpo]
    if eh_admin and situacao != 'Cancelado':
        pecas.append(Div(
            btn(None, dense=True, icon='lock_open', title='Liberar',
                hx_post=f'/tentativa/{tid}/liberar',
                hx_target='#tentativas', hx_swap='outerHTML'),
            btn(None, dense=True, color='error', icon='block', title='Cancelar',
                hx_post=f'/tentativa/{tid}/cancelar',
                hx_target='#tentativas', hx_swap='outerHTML'),
            cls='flex gap-1'))
    return Div(*pecas, cls='flex flex-col items-center gap-1')


def _celula_resultado(linha, n, ranking):
    """Coluna Resultado: pontuação pela fórmula da rodada (parcial enquanto
    faltam tentativas) + rank denso (empates compartilham o lugar)."""
    if linha is None:
        return Span('—', cls='opacity-30')
    score = linha['score']
    if score is None:
        if not linha['validas']:
            return Span('—', cls='opacity-30')
        if n and linha['validas'] < n:
            return Div(f'faltam {n - linha["validas"]}', cls='text-xs opacity-50')
        return Span('sem resultado', cls='text-xs opacity-50')
    pecas = [Span(fmt_ms(score), cls='font-mono font-bold')]
    rk = ranking.get(score)
    if rk:
        pecas.append(Span(f'{rk}º', cls='badge badge-sm ' +
                          ('badge-success' if rk == 1 else 'badge-ghost')))
    return Div(*pecas, cls='flex flex-col items-center gap-1')


def _tentativas_section(rodada_id, eh_admin=False, aviso=None):
    """Fragmento `#tentativas` LARGO: uma linha por atleta, uma coluna por
    tentativa (T1..Tn) + Resultado (pontuação atual pela fórmula do formato).
    `aviso` = faixa de notificação."""
    with get_session() as session:
        rodada = session.get(Rodada, rodada_id)
        if rodada is None:
            return Response('Rodada não encontrada.', status_code=404)
        por_atleta = {}
        max_n = 0
        for tentativa in rodada.tentativas:
            if tentativa.inscricao is None:
                continue
            cadastro = tentativa.inscricao.cadastro
            nome = (cadastro.nome or cadastro.email or '?') if cadastro else '?'
            info = por_atleta.setdefault(tentativa.inscricao_id,
                                         {'nome': nome, 'grupo': tentativa.grupo or 0,
                                          'celulas': {}})
            info['celulas'][tentativa.numero] = (tentativa.situacao, tentativa.duracao,
                                                 tentativa.horario_inicio, tentativa.id)
            max_n = max(max_n, tentativa.numero)
        # pontuação parcial/total pela MESMA fórmula usada na progressão e no
        # pódio da listagem — nada de lógica duplicada aqui
        res = {l['id']: l for l in ranking_rows(rodada)}
        n_formato = n_tentativas(rodada.formato)
    distintos = sorted({l['score'] for l in res.values() if l['score'] is not None})
    ranking = {s: i + 1 for i, s in enumerate(distintos)}
    headers = ['Grupo', 'Atleta'] + [f'T{k}' for k in range(1, max_n + 1)] + ['Resultado']
    if eh_admin:
        headers.append('Extra')
    linhas = []
    for iid, info in sorted(por_atleta.items(), key=lambda kv: (kv[1]['grupo'], kv[1]['nome'])):
        celulas = [str(info['grupo']), info['nome']]
        for k in range(1, max_n + 1):
            t = info['celulas'].get(k)
            celulas.append(_celula_tentativa(t, eh_admin, rodada_id) if t
                           else Span('—', cls='opacity-30'))
        celulas.append(_celula_resultado(res.get(iid), n_formato, ranking))
        if eh_admin:
            celulas.append(btn(None, dense=True, outline=True, icon='add',
                               title='Nova tentativa',
                               hx_post=f'/rodada/{rodada_id}/tentativa_nova?inscricao={iid}',
                               hx_target='#tentativas', hx_swap='outerHTML'))
        linhas.append(drow(celulas))
    banner = (Div(aviso, cls='p-2 font-bold border border-warning rounded-box')
              if aviso else '')
    return Div(banner,
               Div('Tentativas', cls='text-xl font-bold'),
               dtable(headers, linhas),
               id='tentativas')


def _rodada_form(rodada_id, rodada, alvo=None):
    """`alvo` = eco de um envio inválido: reexibe o que foi digitado."""
    eco = alvo is not None

    def valor(campo, atributo):
        if eco:
            return alvo[campo] or None
        atual = getattr(rodada, atributo)
        return None if atual is None else str(atual)

    fmt = alvo['formato'] if eco else rodada.formato
    options = OPCOES_FORMATO + ([fmt] if fmt and fmt not in OPCOES_FORMATO else [])
    if eco:
        modo = alvo['modo_aprov']
    else:
        modo = ('pct' if (rodada.percent_aprovados is not None
                          and rodada.n_pessoas_aprovadas is None) else 'qtd')
    return Form(
        select_field('formato', 'Formato', options, value=fmt),
        field('tempo_maximo', 'Tempo máximo (mm:ss)',
              value=valor('tempo_maximo', 'tempo_maximo'),
              placeholder='00:00', data_fp_mmss=''),
        Fieldset(
            Legend('Quem avança', cls='text-sm font-semibold'),
            Label(Input(type='radio', name='modo_aprov', value='qtd',
                        **({'checked': ''} if modo == 'qtd' else {})),
                  Span('Quantidade de aprovados', cls='label-text'),
                  cls='flex items-center gap-2'),
            Input(type='number', id='n_pessoas_aprovadas', name='n_pessoas_aprovadas',
                  cls='input w-full', placeholder='ex.: 3',
                  **({'value': valor('n_pessoas_aprovadas', 'n_pessoas_aprovadas')}
                     if valor('n_pessoas_aprovadas', 'n_pessoas_aprovadas') else {})),
            Label(Input(type='radio', name='modo_aprov', value='pct',
                        **({'checked': ''} if modo == 'pct' else {})),
                  Span('Percentual dos pontuáveis', cls='label-text'),
                  cls='flex items-center gap-2'),
            Input(type='number', id='percent_aprovados', name='percent_aprovados',
                  cls='input w-full', placeholder='ex.: 50', min='1', max='100',
                  **({'value': valor('percent_aprovados', 'percent_aprovados')}
                     if valor('percent_aprovados', 'percent_aprovados') else {})),
            cls='border border-base-300 rounded-box p-3 flex flex-col gap-1'),
        field('maximo_grupo', 'Tamanho máximo do grupo', type='number',
              value=valor('maximo_grupo', 'maximo_grupo')),
        Div(btn('Enviar', type='submit', icon='send'),
            btn('Cancelar', href=f'/rodada/{rodada_id}', color=None),
            cls='flex gap-3 mt-1'),
        action=f'/rodada/{rodada_id}', method='post',
        cls='flex flex-col gap-3 bg-base-100 rounded-box shadow-sm p-4')


def _campo_int(txt, rotulo, erros, minimo=None, maximo=None):
    """Inteiro validado: vazio -> None; lixo/fora da faixa -> erro + None."""
    if txt in (None, ''):
        return None
    try:
        n = int(txt)
    except ValueError:
        erros.append(f'{rotulo}: use apenas um número inteiro (recebi "{txt}").')
        return None
    if minimo is not None and n < minimo:
        erros.append(f'{rotulo}: precisa ser ≥ {minimo}.')
        return None
    if maximo is not None and n > maximo:
        erros.append(f'{rotulo}: precisa ser ≤ {maximo}.')
        return None
    return n


def _validar_rodada(formato, tempo_maximo, modo_aprov, n_txt, pct_txt, grupo_txt):
    """(erros, valores limpos para gravar, eco bruto para reexibir)."""
    erros = []
    if formato not in FORMULTAS:
        erros.append(f'O formato "{formato or "(vazio)"}" não tem fórmula de pontuação '
                     '— escolha um da lista.')
    tm = _norm_mmss(tempo_maximo)
    if '%' in (tempo_maximo or ''):
        erros.append('Percentual não é tempo: ele vai no bloco "Quem avança", '
                     'não em Tempo máximo.')
    elif tm is None and (tempo_maximo or '').strip():
        erros.append(f'Tempo máximo inválido (recebi "{tempo_maximo}") — '
                     'use mm:ss, ex.: 01:30.')
    n = _campo_int(n_txt, 'Quantidade de aprovados', erros, minimo=1)
    pct = _campo_int(pct_txt, 'Percentual de aprovados', erros, minimo=1, maximo=100)
    grupo = _campo_int(grupo_txt, 'Tamanho máximo do grupo', erros, minimo=1)
    if modo_aprov not in ('qtd', 'pct'):
        erros.append('Escolha como a rodada classifica: por quantidade ou percentual.')
    elif modo_aprov == 'qtd' and n is None and not any(
            'Quantidade de aprovados' in e for e in erros):
        erros.append('Em "Quantidade", informe quantos aprovam (ou troque para Percentual).')
    elif modo_aprov == 'pct' and pct is None and not any(
            'Percentual de aprovados' in e for e in erros):
        erros.append('Em "Percentual", informe um valor de 1 a 100 (ou troque para Quantidade).')
    limpo = {'formato': formato, 'tempo_maximo': tm,
             'n_pessoas_aprovadas': n if modo_aprov == 'qtd' else None,
             'percent_aprovados': pct if modo_aprov == 'pct' else None,
             'maximo_grupo': grupo}
    eco = {'formato': formato, 'tempo_maximo': tempo_maximo or '',
           'modo_aprov': modo_aprov or '', 'n_pessoas_aprovadas': n_txt or '',
           'percent_aprovados': pct_txt or '', 'maximo_grupo': grupo_txt or ''}
    return erros, limpo, eco


def register(rt):
    @rt('/rodada/{rodada_id}', methods=['GET'], before=require_login)
    def get(request: Request, rodada_id: str, editar: str = '', travar: str = '',
            aviso: str = ''):
        user = current_user(request)
        eh_admin = user.role == 'admin'
        editando = eh_admin and editar in ('1', 'true')
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return Response('Rodada não encontrada.', status_code=404)
            # trava/destrava manual (toggle 'Travada' do admin). Não se trava
            # com tentativa em andamento — o atleta ficaria com cronômetro
            # que não pode fechar.
            if eh_admin and travar in ('0', '1'):
                if travar == '1' and any(t.horario_inicio is not None and t.duracao is None
                                         for t in rodada.tentativas):
                    return RedirectResponse(
                        f'/rodada/{rodada_id}?aviso='
                        + quote('Tentativa em andamento — trave só depois de encerrá-la.'),
                        status_code=303)
                rodada.travada = travar == '1'
                session.add(rodada)
                session.commit()
                return RedirectResponse(f'/rodada/{rodada_id}', status_code=303)
            campeonato = rodada.campeonato
            valores = dict(formato=rodada.formato, tempo_maximo=rodada.tempo_maximo,
                           n_pessoas_aprovadas=rodada.n_pessoas_aprovadas,
                           percent_aprovados=rodada.percent_aprovados,
                           maximo_grupo=rodada.maximo_grupo,
                           campeonato_id=rodada.campeonato_id,
                           travada=bool(rodada.travada))

        rows = [drow(['Formato', valores['formato'] or '-']),
                drow(['Tempo máximo (mm:ss)', valores['tempo_maximo'] or '-']),
                drow(['Classifica por', 'quantidade' if valores['n_pessoas_aprovadas'] is not None
                      else ('percentual' if valores['percent_aprovados'] is not None else '-')]),
                drow(['Aprovados', str(valores['n_pessoas_aprovadas'])
                      if valores['n_pessoas_aprovadas'] is not None
                      else (f"{valores['percent_aprovados']}% dos pontuáveis"
                            if valores['percent_aprovados'] is not None else '-')]),
                drow(['Tamanho máximo do grupo',
                      str(valores['maximo_grupo']) if valores['maximo_grupo'] is not None else '-'])]
        if eh_admin:
            # 'Travada' é conceito de coordenação; atleta não precisa saber assim.
            rows.append(drow(['Travada', 'sim' if valores['travada'] else 'não']))
        info = (_rodada_form(rodada_id, rodada) if editando else dtable(['Campo', 'Valor'], rows))

        botoes = []
        if eh_admin:
            botoes.append(toggle('Editar', f'/rodada/{rodada_id}', checked=editando))
            botoes.append(btn('Redistribuir grupos', icon='shuffle',
                              hx_post=f'/rodada/{rodada_id}/redistribuir',
                              hx_target='#tentativas', hx_swap='outerHTML'))
            botoes.append(btn('Avançar rodada', icon='skip_next', color=None,
                              hx_get=f'/rodada/{rodada_id}/progressao',
                              hx_target='#progressao-area', hx_swap='outerHTML'))
            botoes.append(Label(
                Input(cls='toggle toggle-error', type='checkbox',
                      **({'checked': ''} if valores['travada'] else {}),
                      onchange=f"location.href = '/rodada/{rodada_id}?travar=' + (this.checked ? '1' : '0')"),
                Span('Travada', cls='label-text'),
                cls='flex items-center gap-2 cursor-pointer'))
        botoes.append(btn('Retornar', href=f'/campeonato/{valores["campeonato_id"]}', color=None))

        avisos = ([Div('Rodada travada — resultados protegidos.',
                       cls='text-error font-bold')] if (eh_admin and valores['travada']) else [])
        if aviso:
            avisos.append(Div(aviso, cls='text-warning font-bold'))
        return page(request, 'Rodada',
                    Div('Rodada', cls='text-2xl font-bold'),
                    *avisos,
                    Div(card(f'Modalidade: {campeonato.modalidade if campeonato else '-'}'),
                        card(f'Data: {campeonato.data if campeonato else '-'}'),
                        cls='grid grid-cols-1 sm:grid-cols-2 gap-3'),
                    info,
                    Div(_tentativas_section(rodada_id, eh_admin),
                        **{'x-data': f"live('/rodada/{rodada_id}/tentativas', '#tentativas')"}),
                    Div(id='progressao-area'),
                    Div(*botoes, cls='flex flex-wrap gap-3 items-center'))

    @rt('/rodada/{rodada_id}/tentativas', before=require_login)
    def tentativas(request: Request, rodada_id: str):
        return _tentativas_section(rodada_id, current_user(request).role == 'admin')

    @rt('/rodada/{rodada_id}', methods=['POST'], before=require_admin)
    def post(request: Request, rodada_id: str, formato: str = None,
             tempo_maximo: str = None, modo_aprov: str = None,
             n_pessoas_aprovadas: str = None, percent_aprovados: str = None,
             maximo_grupo: str = None):
        erros, limpo, eco = _validar_rodada(formato, tempo_maximo, modo_aprov,
                                            n_pessoas_aprovadas, percent_aprovados,
                                            maximo_grupo)
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return Response('Rodada não encontrada.', status_code=404)
            if erros:
                return page(request, 'Rodada — corrija os erros',
                            Div('Corrija os erros abaixo', cls='text-2xl font-bold'),
                            Div(Ul(*[Li(e, cls='text-error') for e in erros],
                                   cls='list-disc pl-5'),
                                cls='p-3 border border-error rounded-box'),
                            _rodada_form(rodada_id, rodada, alvo=eco),
                            _tentativas_section(rodada_id, True))
            rodada.sqlmodel_update(limpo)
            session.add(rodada)
            session.commit()
        return RedirectResponse(f'/rodada/{rodada_id}', status_code=303)

    @rt('/rodada/{rodada_id}/redistribuir', methods=['POST'], before=require_admin)
    async def redistribuir(request: Request, rodada_id: str):
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return Response('Rodada não encontrada.', status_code=404)
            if rodada.travada:
                return _tentativas_section(rodada_id, True,
                                           aviso='Rodada travada — redistribuir proibido.')
            if any(t.horario_inicio is not None or t.duracao is not None
                   for t in rodada.tentativas):
                return _tentativas_section(rodada_id, True, aviso=(
                    'Há tentativas iniciadas ou concluídas — redistribuir apagaria '
                    'resultados; proibido.'))
            session.exec(delete(Tentativa).where(col(Tentativa.rodada_id) == rodada_id))
            inscricoes = session.exec(select(Inscricao).where(
                col(Inscricao.campeonato_id) == rodada.campeonato_id)).all()
            _gerar_tentativas(session, rodada_id, inscricoes,
                              rodada.maximo_grupo, n_tentativas(rodada.formato) or 5)
            session.commit()
        await manager.broadcast()
        return _tentativas_section(rodada_id, eh_admin=True)

    @rt('/tentativa/{tentativa_id}/liberar', methods=['POST'], before=require_admin)
    async def liberar(request: Request, tentativa_id: str):
        with get_session() as session:
            tentativa = session.get(Tentativa, tentativa_id)
            if tentativa is None:
                return Response('Tentativa não encontrada.', status_code=404)
            rodada_id = tentativa.rodada_id
            if tentativa.rodada is not None and tentativa.rodada.travada:
                return _tentativas_section(rodada_id, True,
                                           aviso='Rodada travada — liberação proibida.')
            if tentativa.horario_inicio is not None and tentativa.duracao is None:
                return _tentativas_section(rodada_id, True, aviso=(
                    'Tentativa em andamento — espere o atleta encerrar antes de liberar.'))
            if tentativa.situacao == 'Cancelado':
                return _tentativas_section(rodada_id, True, aviso=(
                    'Tentativa cancelada — dê Nova tentativa em vez de reabrir.'))
            tentativa.situacao = 'Liberado'
            tentativa.horario_inicio = None
            tentativa.duracao = None
            session.add(tentativa)
            session.commit()
        await manager.broadcast()
        return _tentativas_section(rodada_id, eh_admin=True)

    @rt('/tentativa/{tentativa_id}/cancelar', methods=['POST'], before=require_admin)
    async def cancelar(request: Request, tentativa_id: str):
        """Admin invalida uma tentativa (largada errada etc). Mantém os tempos
        gravados como histórico; ela sai do ranking por não ser mais 'Realizado'."""
        with get_session() as session:
            tentativa = session.get(Tentativa, tentativa_id)
            if tentativa is None:
                return Response('Tentativa não encontrada.', status_code=404)
            rodada_id = tentativa.rodada_id
            if tentativa.rodada is not None and tentativa.rodada.travada:
                return _tentativas_section(rodada_id, True,
                                           aviso='Rodada travada — não é possível cancelar.')
            if tentativa.situacao == 'Cancelado':
                return _tentativas_section(rodada_id, True, aviso='Tentativa já cancelada.')
            if tentativa.horario_inicio is not None and tentativa.duracao is None:
                return _tentativas_section(rodada_id, True, aviso=(
                    'Tentativa em andamento — o atleta precisa encerrar o cronômetro '
                    'antes do cancelamento.'))
            tentativa.situacao = 'Cancelado'
            session.add(tentativa)
            session.commit()
        await manager.broadcast()
        return _tentativas_section(rodada_id, True)

    @rt('/rodada/{rodada_id}/tentativa_nova', methods=['POST'], before=require_admin)
    async def tentativa_nova(request: Request, rodada_id: str, inscricao: str = ''):
        """Admin dá uma tentativa extra ao atleta (caso clássico de WCA)."""
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return Response('Rodada não encontrada.', status_code=404)
            if rodada.travada:
                return _tentativas_section(rodada_id, True,
                                           aviso='Rodada travada — não é possível dar nova tentativa.')
            insc = session.get(Inscricao, inscricao) if inscricao else None
            if insc is None or insc.campeonato_id != rodada.campeonato_id:
                return _tentativas_section(rodada_id, True, aviso='Inscrição inválida.')
            proprias = [t for t in rodada.tentativas if t.inscricao_id == inscricao]
            numero = max([t.numero for t in proprias], default=0) + 1
            grupo = proprias[0].grupo if proprias else None
            session.add(Tentativa(numero=numero, grupo=grupo, rodada_id=rodada_id,
                                  inscricao_id=inscricao, situacao='Liberado'))
            session.commit()
        await manager.broadcast()
        return _tentativas_section(rodada_id, True)

    @rt('/rodada/{rodada_id}/progressao', before=require_admin)
    def progressao(request: Request, rodada_id: str):
        """Prévia do ranking — não grava nada."""
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return _progressao_area(rodada_id,
                                        {'ok': False, 'erro': 'Rodada não encontrada.'})
            dados = _calcular_progressao(rodada)
        return _progressao_area(rodada_id, dados)

    @rt('/rodada/{rodada_id}/progressao/confirmar', methods=['POST'], before=require_admin)
    async def progressao_confirmar(request: Request, rodada_id: str):
        """Recalcula na hora e cria a próxima rodada só com os classificados."""
        with get_session() as session:
            rodada = session.get(Rodada, rodada_id)
            if rodada is None:
                return _progressao_area(rodada_id,
                                        {'ok': False, 'erro': 'Rodada não encontrada.'})
            if rodada.travada:
                return _progressao_area(rodada_id, {'ok': False, 'erro': (
                    'Rodada travada — já avançou ou foi fechada pela coordenação.')})
            if any(t.horario_inicio is not None and t.duracao is None
                   for t in rodada.tentativas):
                return _progressao_area(rodada_id, {'ok': False, 'erro': (
                    'Há tentativa em andamento — encerre-a antes de avançar de rodada.')})
            dados = _calcular_progressao(rodada)
            if not dados['ok']:
                return _progressao_area(rodada_id, dados)
            posicao = (rodada.posicao_rodada or 0) + 1
            proxima = session.exec(select(Rodada).where(
                col(Rodada.campeonato_id) == rodada.campeonato_id,
                col(Rodada.posicao_rodada) == posicao)).first()
            if proxima is not None and proxima.tentativas:
                return _progressao_area(rodada_id, {'ok': False, 'erro': (
                    f'A próxima rodada (posição {posicao}) já possui tentativas — '
                    'trabalhe nela (Redistribuir) em vez de confirmar de novo.')})
            if proxima is None:
                proxima = Rodada(campeonato_id=rodada.campeonato_id,
                                 posicao_rodada=posicao,
                                 formato=rodada.formato,
                                 tempo_maximo=rodada.tempo_maximo,
                                 maximo_grupo=rodada.maximo_grupo)
                session.add(proxima)
                session.commit()
                session.refresh(proxima)
            inscritos = [session.get(Inscricao, iid) for iid in dados['ids_classificados']]
            _gerar_tentativas(session, proxima.id, [i for i in inscritos if i],
                              proxima.maximo_grupo, dados['n'])
            rodada.travada = True   # trava a origem: resultados não mudam mais
            session.add(rodada)
            session.commit()
            nova_id, n_class = proxima.id, len(dados['ids_classificados'])
        await manager.broadcast()
        return _progressao_area(rodada_id, dados, resultado=(nova_id, n_class))
