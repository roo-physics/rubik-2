"""Lista de campeonatos: a pill de data é o link para entrar; o badge mostra
só a FASE (inscrições abertas/aguardando/encerradas, em curso, encerrado·campeão).
Resultados por rodada vivem dentro do campeonato, não na listagem."""

from fasthtml.common import *
from sqlmodel import select

from auth import current_user, require_admin, require_login
from components.daisy import btn, page
from db import get_session
from models import Campeonato
from periodo import estado_inscricoes, parse_dt
from scoring import fmt_ms, ranking_rows


def _pill_data(campeonato):
    """Pill com a data — afordância visual; o CARD inteiro é o link."""
    dt = parse_dt(campeonato.data)
    rotulo = f'{dt:%d/%m/%Y} · {dt:%H:%M}' if dt else 'sem data'
    return Span(rotulo,
                cls=('badge badge-primary' if dt else 'badge badge-ghost')
                    + ' badge-lg rounded-full px-4 text-sm')


def _badge_fase(campeonato):
    rodadas = sorted(campeonato.rodadas,
                     key=lambda r: (r.posicao_rodada is None, r.posicao_rodada or 0))
    comecado = any(t.horario_inicio is not None or t.duracao is not None
                   for r in rodadas for t in r.tentativas)
    if not comecado:
        estado, hint = estado_inscricoes(campeonato.inscricoes_abertura,
                                         campeonato.inscricoes_fim)
        texto = ('Inscrições abertas' + (f' · {hint}' if hint else '')
                 if estado == 'abertas' else f'Inscrições {hint}')
        cor = 'badge-info' if estado == 'abertas' else 'badge-ghost'
        return Div(texto, cls=f'badge {cor} badge-lg')
    ultima = rodadas[-1] if rodadas else None
    if ultima is not None and ultima.travada:
        pontuam = [l for l in ranking_rows(ultima) if l['score'] is not None]
        if pontuam:
            return Div(f"Encerrado · Campeão: {pontuam[0]['nome']} — "
                       f"{fmt_ms(pontuam[0]['score'])}",
                       cls='badge badge-success badge-lg')
        return Div('Encerrado', cls='badge badge-success badge-lg')
    return Div('Em curso', cls='badge badge-warning badge-lg')


def _card_campeonato(campeonato):
    return A(
        Div(_pill_data(campeonato),
            Div(f'{campeonato.modalidade or "Sem modalidade"} · '
                f'{campeonato.local or "sem local"}', cls='text-lg font-bold'),
            cls='flex items-center gap-4 min-w-0'),
        _badge_fase(campeonato),
        href=f'/campeonato/{campeonato.id}',
        cls='card bg-base-100 shadow-sm p-5 flex flex-col gap-3 items-start '
            'no-underline text-current transition hover:shadow-md '
            'hover:ring-2 hover:ring-primary/30')


def register(rt):
    @rt('/campeonatos', before=require_login)
    def get(request: Request):
        eh_admin = current_user(request).role == 'admin'
        with get_session() as session:
            campeonatos = session.exec(
                select(Campeonato).order_by(Campeonato.data)).all()
            cards = [_card_campeonato(c) for c in campeonatos]
        botoes = [btn('Retornar', href='/', color=None)]
        if eh_admin:
            botoes.append(Form(btn('Novo campeonato', icon='add', type='submit'),
                               action='/campeonatos/novo', method='post'))
        return page(request, 'Campeonatos',
                    Div('Campeonatos', cls='text-2xl font-bold'),
                    Div(*botoes, cls='flex flex-wrap gap-3 items-center'),
                    *(cards or [Div('Nenhum campeonato ainda.',
                                    cls='card bg-base-100 shadow-sm p-5 opacity-70')]))

    @rt('/campeonatos/novo', methods=['POST'], before=require_admin)
    def novo(request: Request):
        with get_session() as session:
            campeonato = Campeonato()
            session.add(campeonato)
            session.commit()
            session.refresh(campeonato)
        return RedirectResponse(f'/campeonato/{campeonato.id}?editar=1', status_code=303)
