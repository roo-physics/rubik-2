"""Aplicação FastHTML: páginas server-rendered + HTMX + sessão de servidor.

Rotas e páginas vivem em `pages`; componentes DaisyUI em
`components.daisy`; autenticação em `auth`; broadcast WebSocket
em `ws`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fasthtml.common import *
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

load_dotenv(Path(__file__).parent / ".env")

from components.daisy import HDRS
from db import init_db
from pages import (auth_pages, campeonatos, campeonato, competir, embaralhar,
                       home, rodada)
from ws import ws_connect, ws_disconnect

def not_found(request: Request, exc):
    return HTMLResponse("<p>Página não encontrada. <a href='/'>Início</a></p>",
                        status_code=404)


app, rt = fast_app(
    pico=False,
    hdrs=HDRS,
    secret_key=os.getenv("SECRET_KEY"),
    session_cookie="qs_session",
    on_startup=[init_db],
    exception_handlers={404: not_found},
    htmlkw={'data-theme': 'light'},
)

for mod in (home, auth_pages, campeonatos, campeonato, rodada, competir,
            embaralhar):
    mod.register(rt)

# assets estáticos (static/app.js etc.)
app.mount('/static',
          StaticFiles(directory=Path(__file__).resolve().parent / 'static'),
          name='static')


@app.ws("/ws", conn=ws_connect, disconn=ws_disconnect)
async def ws_echo(websocket: WebSocket):
    # Clientes apenas escutam; o loop mantém a conexão viva até o cliente
    # sair (é o receive que dispara o handler de desconexão/limpeza).
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
