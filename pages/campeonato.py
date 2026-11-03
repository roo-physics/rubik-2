"""Detalhe, edição, período de inscrições e inscrições de um campeonato."""

from datetime import datetime

from fasthtml.common import *
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, or_, select

from auth import CUIABA, current_user, require_admin, require_login
from components.daisy import (btn, drow, dtable, field, page, select_field,
                                  toggle)
from db import get_session
from models import Campeonato, Inscricao, Rodada, Tentativa
from periodo import estado_inscricoes

OPCOES_MODALIDADE = ['Cubo 3x3', 'Cubo 2x2', 'Cubo 4x4', 'Cubo 5x5', 'Cubo 6x6']


def _comecado(session, campeonato_id):
    """Alguma tentativa iniciada/concluída em qualquer rodada do campeonato."""
    return session.exec(
        select(Tentativa.id)
        .join(Rodada, col(Tentativa.rodada_id) == Rodada.id)
        .where(col(Rodada.campeonato_id) == campeonato_id,
               or_(col(Tentativa.horario_inicio).is_not(None),
                   col(Tentativa.duracao).is_not(None)))
        .limit(1)).first() is not None


def _linha_inscricoes(estado, hint):
    if estado == 'abertas':
        return f'Abertas · {hint}' if hint else 'Abertas'
    return hint[0].upper() + hint[1:]  # 'Encerradas em ...' / 'Abrem em ...'


def _campeonato_form(campeonato):
    options = OPCOES_MODALIDADE + ([campeonato.modalidade]
                                   if campeonato.modalidade and campeonato.modalidade not in OPCOES_MODALIDADE
                                   else [])
    return Form(
        select_field('modalidade', 'Modalidade', options, value=campeonato.modalidade),
        field('local', 'Local', value=campeonato.local),
        field('sobre_o_campeonato', 'Sobre o campeonato', value=campeonato.sobre_o_campeonato),
        field('data', 'Data e horário', value=campeonato.data, placeholder='AAAA-MM-DD HH:MM',
              data_fp_datetime=''),
        field('inscricoes_abertura', 'Inscrições — abertura',
              value=campeonato.inscricoes_abertura, placeholder='AAAA-MM-DD HH:MM',
              data_fp_datetime=''),
        field('inscricoes_fim', 'Inscrições — encerramento',
              value=campeonato.inscricoes_fim, placeholder='AAAA-MM-DD HH:MM',
              data_fp_datetime=''),
        Div(btn('Enviar', type='submit', icon='send'),
            btn('Cancelar', href=f'/campeonato/{campeonato.id}', color=None),
            cls='flex gap-3 mt-1'),
        action=f'/campeonato/{campeonato.id}', method='post',
        cls='flex flex-col gap-3 bg-base-100 rounded-box shadow-sm p-4')


def _inscritos_section(inscritos):
    """Roster do campeonato: cabeçalho + chips de nomes (dentro da página,
    não na listagem)."""
    chips = [Span(nome, cls='inline-flex items-center rounded-full bg-base-200 '
                            'px-2.5 py-0.5 text-sm') for nome in inscritos]
    return Div(
        Div(f'Inscritos ({len(inscritos)})', cls='text-lg font-bold'),
        Div(*chips if chips else [Span('nenhum ainda', cls='opacity-60')],
            cls='card bg-base-100 shadow-sm p-4 flex flex-wrap gap-1.5'),
        cls='flex flex-col gap-2',
    )


def _inscricao_area(user, campeonato_id, estado='abertas', hint='', comecado=False):
    with get_session() as session:
        inscrita = session.exec(select(Inscricao).where(
            col(Inscricao.campeonato_id) == campeonato_id,
            col(Inscricao.cadastro_id) == user.id)).first()
    partes = []
    if inscrita:
        partes.append(Div('Você está inscrito neste campeonato.', cls='opacity-60'))
        if estado == 'abertas' and not comecado:
            partes.append(btn('Desinscrever-se', icon='remove',
                              hx_post=f'/campeonato/{campeonato_id}/desinscrever',
                              hx_target='#inscricao-area', hx_swap='outerHTML'))
        elif comecado:
            partes.append(Div('O campeonato já começou — a inscrição não pode mais '
                              'ser cancelada.', cls='opacity-70 text-sm'))
    elif estado == 'abertas':
        partes.append(btn('Inscrever-se', icon='add',
                          hx_post=f'/campeonato/{campeonato_id}/inscrever',
                          hx_target='#inscricao-area', hx_swap='outerHTML'))
    else:
        partes.append(Div(f'Inscrições {hint}.', cls='opacity-70'))
    return Div(*partes, id='inscricao-area', cls='flex flex-col gap-1')


def register(rt):
    @rt('/campeonato/{campeonato_id}', methods=['GET'], before=require_login)
    def get(request: Request, campeonato_id: str, editar: str = ''):
        user = current_user(request)
        eh_admin = user.role == 'admin'
        editando = eh_admin and editar in ('1', 'true')
        with get_session() as session:
            campeonato = session.get(Campeonato, campeonato_id)
            if campeonato is None:
                return Response('Campeonato não encontrado.', status_code=404)
            rodadas = session.exec(
                select(Rodada).where(col(Rodada.campeonato_id) == campeonato_id)).all()
            inscritos = [i.cadastro.nome or i.cadastro.email or '?'
                         for i in campeonato.inscricoes if i.cadastro]
            estado, hint = estado_inscricoes(campeonato.inscricoes_abertura,
                                             campeonato.inscricoes_fim)
            comecado = _comecado(session, campeonato_id)
        rodadas.sort(key=lambda r: (r.posicao_rodada is None, r.posicao_rodada or 0))

        info = (_campeonato_form(campeonato) if editando else dtable(
            ['Campo', 'Valor'],
            [drow(['Modalidade', campeonato.modalidade or '-']),
             drow(['Data', campeonato.data or '-']),
             drow(['Inscrições', _linha_inscricoes(estado, hint)]),
             drow(['Local', campeonato.local or '-']),
             drow(['Sobre o campeonato', campeonato.sobre_o_campeonato or '-'])]))

        rows = [drow([str(rodada.posicao_rodada if rodada.posicao_rodada is not None else '-'),
                      rodada.formato or '-', rodada.tempo_maximo or '-'],
                     href=f'/rodada/{rodada.id}')
                for rodada in rodadas]

        botoes = [btn('Retornar', href='/campeonatos', color=None)]
        if eh_admin:
            botoes.append(toggle('Editar', f'/campeonato/{campeonato_id}', checked=editando))
            botoes.append(Form(btn('Adicionar rodada', icon='add', type='submit'),
                               action=f'/campeonato/{campeonato_id}/rodadas', method='post'))
            if estado == 'abertas':
                botoes.append(btn('Fechar inscrições', color='warning', icon='block',
                                  href=f'/campeonato/{campeonato_id}/fechar_inscricoes'))
        elif user.role == 'usuario_externo':
            botoes.append(_inscricao_area(user, campeonato_id, estado, hint, comecado))

        return page(request, 'Campeonato',
                    Div('Campeonato', cls='text-2xl font-bold'),
                    info,
                    Div('Rodadas', cls='text-xl font-bold'),
                    dtable(['#', 'Formato', 'Tempo máximo'], rows),
                    _inscritos_section(inscritos),
                    Div(*botoes, cls='flex flex-wrap gap-3 items-center'))

    @rt('/campeonato/{campeonato_id}', methods=['POST'], before=require_admin)
    def atual(campeonato_id: str, modalidade: str = None, local: str = None,
              sobre_o_campeonato: str = None, data: str = None,
              inscricoes_abertura: str = None, inscricoes_fim: str = None):
        with get_session() as session:
            campeonato = session.get(Campeonato, campeonato_id)
            if campeonato is None:
                return Response('Campeonato não encontrado.', status_code=404)
            campeonato.sqlmodel_update({
                'modalidade': modalidade, 'local': local,
                'sobre_o_campeonato': sobre_o_campeonato, 'data': data or None,
                'inscricoes_abertura': inscricoes_abertura or None,
                'inscricoes_fim': inscricoes_fim or None})
            session.add(campeonato)
            session.commit()
        return RedirectResponse(f'/campeonato/{campeonato_id}', status_code=303)

    @rt('/campeonato/{campeonato_id}/fechar_inscricoes', before=require_admin)
    def fechar_inscricoes(request: Request, campeonato_id: str):
        """Encerra o período AGORA (reabre depois editando o período)."""
        with get_session() as session:
            campeonato = session.get(Campeonato, campeonato_id)
            if campeonato is None:
                return Response('Campeonato não encontrado.', status_code=404)
            campeonato.inscricoes_fim = datetime.now(CUIABA).strftime('%Y-%m-%d %H:%M')
            session.add(campeonato)
            session.commit()
        return RedirectResponse(f'/campeonato/{campeonato_id}', status_code=303)

    @rt('/campeonato/{campeonato_id}/inscrever', methods=['POST'], before=require_login)
    def inscrever(request: Request, campeonato_id: str):
        user = current_user(request)
        if user.role != 'usuario_externo':
            return Response('Apenas usuários externos podem se inscrever.', status_code=403)
        with get_session() as session:
            campeonato = session.get(Campeonato, campeonato_id)
            if campeonato is None:
                return Response('Campeonato não encontrado.', status_code=404)
            estado, hint = estado_inscricoes(campeonato.inscricoes_abertura,
                                             campeonato.inscricoes_fim)
            if estado != 'abertas':
                return Response(f'Inscrições {hint}.', status_code=403)
            if session.exec(select(Inscricao).where(
                    col(Inscricao.campeonato_id) == campeonato_id,
                    col(Inscricao.cadastro_id) == user.id)).first() is None:
                try:
                    session.add(Inscricao(campeonato_id=campeonato_id, cadastro_id=user.id))
                    session.commit()
                except IntegrityError:  # corrida: outra inscrição simultânea venceu
                    session.rollback()
        return _inscricao_area(user, campeonato_id, estado, hint)

    @rt('/campeonato/{campeonato_id}/desinscrever', methods=['POST'], before=require_login)
    def desinscrever(request: Request, campeonato_id: str):
        user = current_user(request)
        with get_session() as session:
            if _comecado(session, campeonato_id):
                return Response('O campeonato já começou — a inscrição não pode mais '
                                'ser cancelada.', status_code=403)
            session.exec(delete(Inscricao).where(
                col(Inscricao.campeonato_id) == campeonato_id,
                col(Inscricao.cadastro_id) == user.id))
            session.commit()
        return _inscricao_area(user, campeonato_id)

    @rt('/campeonato/{campeonato_id}/rodadas', methods=['POST'], before=require_admin)
    def nova_rodada(request: Request, campeonato_id: str):
        with get_session() as session:
            posicoes = session.exec(select(Rodada.posicao_rodada).where(
                col(Rodada.campeonato_id) == campeonato_id)).all()
            rodada = Rodada(campeonato_id=campeonato_id,
                            posicao_rodada=(max(posicoes) if posicoes else 0) + 1)
            session.add(rodada)
            session.commit()
            session.refresh(rodada)
        return RedirectResponse(f'/rodada/{rodada.id}', status_code=303)
