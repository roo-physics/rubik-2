"""Canal WebSocket para notificar clientes sobre atualizações.

Substitui o `asyncio.Event` compartilhado do código antigo: cada página
assistente (Rodada / Competir) mantém uma conexão e recebe um texto curto
sempre que uma tentativa muda de estado. A sessão precisa ser válida
(meia-noite de Cuiabá), senão a conexão é fechada.
"""

from starlette.websockets import WebSocket

from auth import session_valid


class WSManager:
    def __init__(self):
        self.active: set[WebSocket] = set()

    def add(self, ws: WebSocket):
        self.active.add(ws)

    def remove(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self):
        for ws in list(self.active):
            try:
                await ws.send_text("atualizar")
            except Exception:
                self.active.discard(ws)


manager = WSManager()


async def ws_connect(ws: WebSocket):
    if ws.session.get("user_id") is None or not session_valid(ws):
        await ws.close(code=4401)
        return
    manager.add(ws)


async def ws_disconnect(ws: WebSocket):
    manager.remove(ws)
