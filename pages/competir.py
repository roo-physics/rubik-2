"""Tela do competidor.

Modos do painel (decididos por _contexto):
- 'rodando'  : cronômetro em andamento — o Parar cobre a viewport TODA.
- 'pronta'   : tentativa liberada esperando — o Iniciar cobre a tela.
- 'espera'   : campeonato em curso sem tentativa liberada — suas marcas na
               rodada atual, o que resta (com aviso de aguardo) e a posição
               na rodada anterior.
- 'contagem' : campeonato ainda não começou — contagem regressiva.
- 'nada'     : nenhuma inscrição relevante.
"""

import time
from datetime import datetime

from fasthtml.common import *
from sqlalchemy import update
from sqlmodel import col, or_, select

from auth import CUIABA, current_user, require_login
from components.daisy import btn, page
from db import get_session
from models import Inscricao, Rodada, Tentativa
from periodo import parse_dt
from scoring import fmt_ms, ranking_rows
from ws import manager


def _tentativa_em_aberto(user, WHERE):
    with get_session() as session:
        return session.exec(
            select(Tentativa).join(Inscricao)
            .join(Rodada, col(Tentativa.rodada_id) == Rodada.id)
            .where(col(Inscricao.cadastro_id) == user.id,
                   col(Rodada.travada).is_not(True), *WHERE)
            .limit(1)).first()


def _contexto(user):
    """O que a tela deve mostrar agora (ver docstring do módulo)."""
    rodando = _tentativa_em_aberto(user, (
        col(Tentativa.situacao) == 'Liberado',
        col(Tentativa.horario_inicio).is_not(None),
        col(Tentativa.duracao).is_(None)))
    if rodando is not None:
        return {'modo': 'rodando', 'tentativa': rodando}

    pendente = _tentativa_em_aberto(user, (
        col(Tentativa.situacao) == 'Liberado',
        col(Tentativa.horario_inicio).is_(None)))
    if pendente is not None:
        return {'modo': 'pronta', 'tentativa': pendente}

    agora = datetime.now(CUIABA).replace(tzinfo=None)
    with get_session() as session:
        meus = session.exec(
            select(Inscricao).where(col(Inscricao.cadastro_id) == user.id)).all()
        campeonatos = [i.campeonato for i in meus if i.campeonato is not None]

        def comecado(cid):
            return session.exec(
                select(Tentativa.id)
                .join(Rodada, col(Tentativa.rodada_id) == Rodada.id)
                .where(col(Rodada.campeonato_id) == cid,
                       or_(col(Tentativa.horario_inicio).is_not(None),
                           col(Tentativa.duracao).is_not(None)))
                .limit(1)).first() is not None

        def chave(c):
            return parse_dt(c.data) or datetime.max

        cursos = sorted((c for c in campeonatos if comecado(c.id)), key=chave)
        if cursos:
            c = cursos[0]
            minha_insc = next(i.id for i in meus if i.campeonato_id == c.id)
            com_minhas = sorted(
                (r for r in c.rodadas
                 if any(t.inscricao_id == minha_insc for t in r.tentativas)),
                key=lambda r: (r.posicao_rodada is None, r.posicao_rodada or 0))
            atual = next((r for r in com_minhas if not r.travada),
                         com_minhas[-1] if com_minhas else None)
            travadas_anteriores = [r for r in com_minhas
                                   if r is not atual and r.travada]
            anterior = travadas_anteriores[-1] if travadas_anteriores else None
            pos = None
            if anterior is not None and anterior.formato:
                pontuam = [l for l in ranking_rows(anterior) if l['score'] is not None]
                idx = next((i for i, l in enumerate(pontuam)
                            if l['id'] == minha_insc), None)
                if idx is not None:
                    pos = (idx + 1, len(pontuam))
            minhas = sorted((t for t in atual.tentativas
                             if t.inscricao_id == minha_insc),
                            key=lambda t: t.numero) if atual else []
            feitas = [(t.numero, t.duracao) for t in minhas
                      if t.situacao == 'Realizado' and t.duracao is not None]
            faltam = [t.numero for t in minhas
                      if t.situacao in ('Liberado', 'Aguardando Liberação')]
            return {'modo': 'espera', 'campeonato': c, 'atual': atual, 'pos': pos,
                    'feitas': feitas, 'faltam': faltam}

        futuros = sorted((c for c in campeonatos
                          if (dt := parse_dt(c.data)) and dt > agora
                          and not comecado(c.id)),
                         key=lambda c: parse_dt(c.data))
        if futuros:
            c = futuros[0]
            alvo = int(parse_dt(c.data).replace(tzinfo=CUIABA).timestamp() * 1000)
            return {'modo': 'contagem', 'campeonato': c, 'alvo_ms': alvo}

    return {'modo': 'nada'}


def _painel(user, aviso=None):
    ctx = _contexto(user)
    modo = ctx['modo']
    banner = [Div(aviso, cls='text-error font-bold')] if aviso else []
    oculto = Input(type='hidden', name='tempo', id='tempo-campo')
    comuns = dict(hx_target='#competir-panel', hx_swap='outerHTML',
                  hx_include='#tempo-campo',
                  onclick="document.getElementById('tempo-campo').value = Date.now()")

    if modo == 'rodando':
        t = ctx['tentativa']
        return Div(oculto, *banner,
                   btn(Div(
                       Span('0:00.000',
                            **{'x-data': f'relogio({t.horario_inicio})', 'x-text': 'txt'}),
                       Span('Toque para parar', cls='text-xl'),
                       cls='flex flex-col items-center gap-2 w-full'),
                       icon='stop', color='error',
                       hx_post=f'/tentativa/{t.id}/parar',
                       cls='botao-cronometro rounded-none touch-manipulation select-none fixed inset-0 z-50',
                       data_stop='', **comuns),
                   id='competir-panel')

    if modo == 'pronta':
        t = ctx['tentativa']
        return Div(oculto, *banner,
                   btn('Iniciar', icon='play_arrow', color='primary',
                       hx_post=f'/tentativa/{t.id}/iniciar',
                       cls='botao-cronometro rounded-none touch-manipulation select-none fixed left-0 right-0 bottom-0 top-16 z-40',
                       **comuns),
                   id='competir-panel')

    if modo == 'espera':
        c, atual = ctx['campeonato'], ctx['atual']
        partes = list(banner)
        titulo = c.modalidade or 'Campeonato'
        if atual is not None and atual.posicao_rodada is not None:
            titulo += f' — Rodada {atual.posicao_rodada}'
        partes.append(Div(titulo, cls='text-2xl font-bold'))
        if ctx['pos']:
            partes.append(Div(f'Rodada anterior: {ctx["pos"][0]}º lugar entre '
                              f'{ctx["pos"][1]} que pontuaram', cls='text-lg'))
        if ctx['feitas']:
            partes.append(Div(
                Div('Suas marcas nesta rodada', cls='font-bold'),
                Div(*[Span(f'Tentativa {n}: {fmt_ms(d)}',
                           cls='badge badge-outline badge-lg')
                      for n, d in ctx['feitas']],
                    cls='flex flex-wrap gap-2'),
                cls='card bg-base-100 shadow-sm p-4 flex flex-col gap-2'))
        if ctx['faltam']:
            partes.append(Div(
                Div('Restam', cls='font-bold'),
                Div(*[Span(f'Tentativa {n} — aguardando liberação',
                           cls='badge badge-ghost badge-lg')
                      for n in ctx['faltam']],
                    cls='flex flex-wrap gap-2'),
                Div('Aguarde — esta tela atualiza sozinha quando o juiz liberar.',
                    cls='opacity-70'),
                cls='card bg-base-100 shadow-sm p-4 flex flex-col gap-2'))
        if not ctx['feitas'] and not ctx['faltam']:
            partes.append(Div('Você completou todas as tentativas desta rodada. '
                              'Aguarde o resultado.', cls='opacity-70'))
        return Div(*partes, id='competir-panel',
                   cls='flex flex-col items-center gap-4 py-10')

    if modo == 'contagem':
        c = ctx['campeonato']
        return Div(*banner,
                   Div(f'{c.modalidade or "Campeonato"} · {c.local or "sem local"}',
                       cls='text-xl font-bold'),
                   Div(f'Data: {c.data}', cls='opacity-70'),
                   Div('Começa em', cls='text-lg uppercase tracking-wide opacity-60'),
                   Div('…', cls='text-5xl font-bold font-mono',
                       **{'x-data': f"contagem({ctx['alvo_ms']})", 'x-text': 'txt'}),
                   Div('A prova aparece aqui quando o juiz liberar a primeira tentativa.',
                       cls='opacity-60 text-sm'),
                   id='competir-panel', cls='flex flex-col items-center gap-3 py-16')

    return Div(*banner,
               Div('Nenhuma tentativa liberada.', cls='opacity-70'),
               Div(btn('Atualizar', color=None, icon='refresh',
                       hx_get='/competir/painel', hx_target='#competir-panel',
                       hx_swap='outerHTML'),
                   btn('Menu principal', color=None, href='/'),
                   cls='flex gap-3'),
               id='competir-panel',
               cls='flex flex-col items-center gap-4 py-10')


def _resolve_tempo(tempo: str) -> int:
    try:
        return int(tempo)
    except (TypeError, ValueError):
        return int(time.time() * 1000)


def register(rt):
    @rt('/competir', methods=['GET'], before=require_login)
    def get(request: Request):
        user = current_user(request)
        return page(request, 'Competir',
                    Div(_painel(user),
                        **{'x-data': "live('/competir/painel', '#competir-panel')"}))

    @rt('/competir/painel', before=require_login)
    def painel(request: Request):
        return _painel(current_user(request))

    @rt('/tentativa/{tentativa_id}/iniciar', methods=['POST'], before=require_login)
    async def iniciar(request: Request, tentativa_id: str, tempo: str = ''):
        user = current_user(request)
        with get_session() as session:
            tentativa = session.get(Tentativa, tentativa_id)
            if tentativa is None:
                return Response('Tentativa não encontrada.', status_code=404)
            if tentativa.inscricao.cadastro_id != user.id:
                return Response('Tentativa de outro competidor.', status_code=403)
            if tentativa.rodada is not None and tentativa.rodada.travada:
                return _painel(user, aviso='Rodada travada — tentativa protegida.')
            # UPDATE condicional: o primeiro clique vence; um segundo (outra
            # aba/dispositivo) não encontra a linha e não sobrescreve o início.
            session.exec(
                update(Tentativa)
                .where(col(Tentativa.id) == tentativa_id,
                       col(Tentativa.situacao) == 'Liberado',
                       col(Tentativa.horario_inicio).is_(None))
                .values(horario_inicio=_resolve_tempo(tempo)))
            session.commit()
        await manager.broadcast()
        return _painel(user)

    @rt('/tentativa/{tentativa_id}/parar', methods=['POST'], before=require_login)
    async def parar(request: Request, tentativa_id: str, tempo: str = ''):
        user = current_user(request)
        with get_session() as session:
            tentativa = session.get(Tentativa, tentativa_id)
            if tentativa is None:
                return Response('Tentativa não encontrada.', status_code=404)
            if tentativa.inscricao.cadastro_id != user.id:
                return Response('Tentativa de outro competidor.', status_code=403)
            if tentativa.rodada is not None and tentativa.rodada.travada:
                return _painel(user, aviso='Rodada travada — tentativa protegida.')
            if (tentativa.horario_inicio is not None
                    and tentativa.duracao is None):
                agora = _resolve_tempo(tempo)
                session.exec(
                    update(Tentativa)
                    .where(col(Tentativa.id) == tentativa_id,
                           col(Tentativa.situacao) == 'Liberado',
                           col(Tentativa.horario_inicio).is_not(None),
                           col(Tentativa.duracao).is_(None))
                    .values(duracao=max(0, agora - tentativa.horario_inicio),
                            situacao='Realizado'))
                session.commit()
        await manager.broadcast()
        return _painel(user)
