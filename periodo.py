"""Período de inscrições — datas gravadas como 'AAAA-MM-DD HH:MM' (hora de Cuiabá)."""

from datetime import datetime

from auth import CUIABA


def parse_dt(txt):
    if not txt:
        return None
    try:
        return datetime.strptime(txt[:16], '%Y-%m-%d %H:%M')
    except ValueError:
        return None


def fmt_br(dt):
    return dt.strftime('%d/%m/%Y %H:%M')


def estado_inscricoes(abertura, fim, agora=None):
    """(estado, rotulo): 'abertas' | 'aguardando' | 'encerradas' + a data-limite.

    Sem período definido => abertas (compatibilidade com cadastros antigos).
    """
    agora = agora or datetime.now(CUIABA).replace(tzinfo=None)
    ini, end = parse_dt(abertura), parse_dt(fim)
    if ini and agora < ini:
        return 'aguardando', f'abrem em {fmt_br(ini)}'
    if end and agora > end:
        return 'encerradas', f'encerradas em {fmt_br(end)}'
    if end:
        return 'abertas', f'até {fmt_br(end)}'
    return 'abertas', ''
