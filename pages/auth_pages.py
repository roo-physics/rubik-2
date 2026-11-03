"""Login, cadastro e logout por sessão de servidor (sem JWT)."""

from fasthtml.common import *
from sqlmodel import select

from auth import (authenticate, clear_current_user, current_user,
                      hash_password, set_current_user)
from components.daisy import btn, field, page
from db import get_session
from models import Cadastro

FORM_CLS = 'flex flex-col gap-3 bg-base-100 rounded-box shadow-sm p-4 max-w-md'


def _login_form(request, erro=None, email=''):
    return page(request, 'Entrar',
                Div('Entrar', cls='text-2xl font-bold'),
                Form(
                    field('email', 'E-mail', value=email, required='', autofocus='',
                          autocomplete='username'),
                    field('senha', 'Senha', type='password', required='',
                          autocomplete='current-password'),
                    *([Div(erro, cls='text-error')] if erro else []),
                    Div(btn('Logar', type='submit', icon='login'),
                        btn('Retornar', href='/', color=None),
                        cls='flex gap-3 mt-1'),
                    action='/logar', method='post', cls=FORM_CLS))


def _cadastro_form(request, erro=None, nome='', email=''):
    return page(request, 'Cadastrar',
                Div('Cadastrar', cls='text-2xl font-bold'),
                Form(
                    field('nome', 'Nome', value=nome, required='', autofocus='',
                          autocomplete='name'),
                    field('email', 'E-mail', value=email, required='',
                          autocomplete='email'),
                    field('senha', 'Senha', type='password', required='',
                          autocomplete='new-password'),
                    *([Div(erro, cls='text-error')] if erro else []),
                    Div(btn('Cadastrar', type='submit', icon='person_add'),
                        btn('Retornar', href='/', color=None),
                        cls='flex gap-3 mt-1'),
                    action='/cadastrar', method='post', cls=FORM_CLS))


def register(rt):
    @rt('/logar', methods=['GET'])
    def get_logar(request: Request):
        if current_user(request):
            return RedirectResponse('/campeonatos', status_code=303)
        return _login_form(request)

    @rt('/logar', methods=['POST'])
    def post_logar(request: Request, email: str, senha: str):
        user = authenticate(email, senha)
        if user is None:
            return _login_form(request, erro='E-mail ou senha incorretos', email=email)
        set_current_user(request, user)
        return RedirectResponse('/campeonatos', status_code=303)

    @rt('/logout', methods=['POST'])
    def post_logout(request: Request):
        clear_current_user(request)
        return RedirectResponse('/', status_code=303)

    @rt('/cadastrar', methods=['GET'])
    def get_cadastrar(request: Request):
        if current_user(request):
            return RedirectResponse('/campeonatos', status_code=303)
        return _cadastro_form(request)

    @rt('/cadastrar', methods=['POST'])
    def post_cadastrar(request: Request, nome: str, email: str, senha: str):
        with get_session() as session:
            if session.exec(select(Cadastro).where(Cadastro.email == email)).first():
                return _cadastro_form(request, erro='E-mail já cadastrado', nome=nome, email=email)
            user = Cadastro(nome=nome, email=email, hashed_password=hash_password(senha),
                            role='usuario_externo')
            session.add(user)
            session.commit()
            session.refresh(user)
        set_current_user(request, user)
        return RedirectResponse('/campeonatos', status_code=303)
