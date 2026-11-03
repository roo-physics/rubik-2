"""Autenticação por sessão (cookie assinado), sem JWT.

As sessões expiram à meia-noite de Cuiabá (MT) — igual ao comportamento do
código antigo com JWT, que fixava `exp` na próxima meia-noite local.
"""

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pwdlib import PasswordHash
from sqlmodel import select
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from db import get_session
from models import Cadastro

LOGIN_URL = "/logar"
CUIABA = ZoneInfo("America/Cuiaba")

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")


def midnight_cuiaba() -> int:
    """Timestamp UTC da próxima meia-noite (00:00) em Cuiabá."""
    agora = datetime.now(tz=CUIABA)
    proxima_meia_noite = (agora + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return int(proxima_meia_noite.timestamp())


def session_valid(conn) -> bool:
    """A sessão da request/websocket ainda não passou da meia-noite."""
    exp = conn.session.get("exp")
    return exp is not None and time.time() < exp


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def authenticate(email: str, password: str) -> Cadastro | None:
    with get_session() as session:
        user = session.exec(select(Cadastro).where(Cadastro.email == email)).first()
        if user is None:
            verify_password(password, DUMMY_HASH)  # equaliza o tempo de resposta
            return None
        if not verify_password(password, user.hashed_password):
            return None
    if user.disabled:
        return None
    return user


def current_user(request: Request) -> Cadastro | None:
    """Usuário da sessão atual (cacheado por request), ou None."""
    if "qs_user" not in request.scope:
        user = None
        if request.session.get("user_id") is not None and session_valid(request):
            with get_session() as session:
                user = session.get(Cadastro, request.session["user_id"])
            if user is not None and user.disabled:
                user = None
        elif "user_id" in request.session:
            request.session.clear()  # sessão expirada: descarta o cookie
        request.scope["qs_user"] = user
    return request.scope["qs_user"]


def set_current_user(request: Request, user: Cadastro):
    request.scope["qs_user"] = user
    request.session["user_id"] = user.id
    request.session["exp"] = midnight_cuiaba()


def clear_current_user(request: Request):
    request.scope["qs_user"] = None
    request.session.clear()


# ------------------------------------------------------------------ guards
# Funções `before` do FastHTML: um valor retornado responde ao request e
# pula o handler.


def require_login(request: Request):
    if current_user(request) is None:
        return RedirectResponse(LOGIN_URL, status_code=303)


def require_admin(request: Request):
    user = current_user(request)
    if user is None:
        return RedirectResponse(LOGIN_URL, status_code=303)
    if user.role != "admin":
        return Response("Acesso restrito a administradores.", status_code=403)
