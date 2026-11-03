"""Página inicial: menu principal sensível ao papel do usuário."""

from fasthtml.common import *

from auth import current_user
from components.daisy import btn, page


def register(rt):
    @rt('/')
    def get(request: Request):
        user = current_user(request)
        if user is None:
            conteudo = (
                Div('Bem-vindo(a)!', cls='text-2xl font-bold'),
                Div('Entre ou crie uma conta para participar dos campeonatos.', cls='opacity-70'),
                Div(btn('Entrar', href='/logar', icon='login'),
                    btn('Cadastrar', href='/cadastrar', color=None, icon='person_add'),
                    cls='flex justify-center gap-3 mt-4'))
        else:
            botoes = [btn('Campeonatos', href='/campeonatos', icon='flag')]
            if user.role != 'admin':
                botoes.append(btn('Competir', href='/competir', icon='timer'))
            botoes.append(btn('Embaralhar', href='/embaralhar', icon='shuffle', color=None))
            conteudo = (
                Div(f'Olá, {user.nome or user.email}!', cls='text-2xl font-bold'),
                Div(*botoes, cls='flex justify-center gap-3 mt-4'))
        return page(request, 'Início', *conteudo)
