"""Builders de componentes DaisyUI (Tailwind via CDN).

DaisyUI entrega componentes prontos (`btn`, `card`, `input`, `toggle`,
`table`, `navbar`, ...) com o CSS oficial via CDN; o script do Tailwind
browser gera as classes utilitárias de layout em tempo de execução — sem
pipeline Node.
"""

from fasthtml.common import *

from auth import current_user

DAISY_CSS = Link(rel='stylesheet', href='https://cdn.jsdelivr.net/npm/daisyui@5.7.50/daisyui.css', type='text/css')
TAILWIND_BROWSER = Script(src='https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4')
ROBOTO_FONT = Link(rel='stylesheet', href='https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap', type='text/css')
MATERIAL_ICONS = Link(rel='stylesheet', href='https://fonts.googleapis.com/icon?family=Material+Icons', type='text/css')
FLATPICKR_CSS = Link(rel='stylesheet', href='https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.css', type='text/css')
FLATPICKR_JS = Script(src='https://cdn.jsdelivr.net/npm/flatpickr@4.6.13/dist/flatpickr.min.js')
# ORDEM IMPORTA: o cdn.min.js do Alpine (3.17) dá boot sozinho num
# queueMicrotask logo após o PRÓPRIO script executar — sem flag para desligar.
# Toda função usada em x-data precisa existir antes disso: scripts nossos
# first, Alpine POR ÚLTIMO (todos deferidos; defer executa em ordem de
# documento). three.js (pesado, só numa página) pode vir depois: o init do
# cubo espera THREE no DOMContentLoaded.
APP_JS = Script(src='/static/app.js', defer=True)
SCRAMBLE_JS = Script(src='/static/scramble.js', defer=True)
ALPINE = Script(src='https://cdn.jsdelivr.net/npm/alpinejs@3.17.5/dist/cdn.min.js', defer=True)
# favicon emoji inline (mata o 404 de /favicon.ico sem arquivo)
FAVICON = Link(rel='icon',
               href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
                    "viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E"
                    "\U0001F3B2%3C/text%3E%3C/svg%3E")

CUSTOM_CSS = Style(Safe("""
html { font-family: Roboto, -apple-system, 'Helvetica Neue', Helvetica, Arial, sans-serif !important; }
.botao-cronometro { font-size: clamp(3em, 3em, 5em); }
[x-cloak] { display: none !important; }
/* picker mm:ss: esconde a coluna de horas e o separador */
.fp-mmss .flatpickr-time input.flatpickr-hour,
.fp-mmss .flatpickr-time input.flatpickr-hour + .flatpickr-time-separator { display: none; }
.fp-mmss .flatpickr-time { max-height: none; }
/* mobile: iOS nao da zoom ao focar (campos >= 16px); navbar compacta */
@media (max-width: 640px) {
  .input, .select, .textarea { font-size: 16px; }
  .navbar { padding-inline: .5rem; }
  .flatpickr-calendar { max-width: 96vw; }
}
"""))

# O JavaScript do cliente vive em static/app.js (componentes Alpine), servido
# como asset — as páginas só levam atributos x-data/x-text, sem inline.

HDRS = (TAILWIND_BROWSER, DAISY_CSS, ROBOTO_FONT, MATERIAL_ICONS, FLATPICKR_CSS,
        CUSTOM_CSS, FLATPICKR_JS, APP_JS, SCRAMBLE_JS, ALPINE, FAVICON)


# ----------------------------------------------------------------- básicos

def btn(text=None, *, href=None, icon=None, color='primary', flat=False,
        outline=False, dense=False, cls='', **kwargs):
    """`btn` DaisyUI: cor sólida (primary/neutral/...), ghost (flat) ou outline."""
    classes = 'btn'
    if flat:
        classes += ' btn-ghost'
    elif outline:
        classes += ' btn-outline'
    elif color:
        classes += f' btn-{color}'
    if dense:
        classes += ' btn-sm'
    if cls:
        classes += f' {cls}'
    conteudo = []
    if icon:
        conteudo.append(I(icon, cls='material-icons'))
    if text is not None:
        conteudo.append(text)
    if href is not None:
        return A(*conteudo, href=href, cls=classes, **kwargs)
    return Button(*conteudo, cls=classes, type=kwargs.pop('type', 'button'), **kwargs)


def card(*content):
    secoes = [Div(c, cls='px-4 py-2') if isinstance(c, str) else c for c in content]
    return Div(*secoes, cls='card bg-base-100 shadow-sm')


# ----------------------------------------------------------------- listas/tabelas

def dtable(headers, rows):
    return Div(Table(
        Thead(Tr(*[Th(h) for h in headers])),
        Tbody(*rows),
        cls='table'), cls='overflow-x-auto bg-base-100 rounded-box shadow-sm')


def drow(cells, href=None):
    tds = [Td(c) for c in cells]
    if href is not None:
        # linha INTEIRA é o link (no lugar de um botão 'Abrir' extra)
        return Tr(*tds, cls='cursor-pointer hover:bg-base-200',
                  onclick=f"window.location.href='{href}'")
    return Tr(*tds)


# ----------------------------------------------------------------- formulários

def field(name, label, value=None, type='text', cls='', **attrs):
    inp = Input(cls=f'input w-full {cls}'.strip(), id=name, name=name, type=type,
                **({'value': value} if value else {}), **attrs)
    return Label(Span(label, cls='label-text'), inp, cls='flex flex-col gap-1')


def select_field(name, label, options, value=None, **attrs):
    opts = [Option(o, value=o, **({'selected': ''} if o == value else {})) for o in options]
    sel = Select(*opts, cls='select w-full', id=name, name=name, **attrs)
    return Label(Span(label, cls='label-text'), sel, cls='flex flex-col gap-1')


def toggle(label, url, checked=False):
    return Label(
        Input(cls='toggle toggle-primary', type='checkbox',
              **({'checked': ''} if checked else {}),
              onchange=f"location.href = {url!r} + (this.checked ? '?editar=1' : '')"),
        Span(label, cls='label-text'),
        cls='flex items-center gap-2 cursor-pointer')


# ----------------------------------------------------------------- layout

DRAWER_ID = 'qs-drawer'


def _menu_lateral(user):
    """Sidebar (drawer) — a navegação inteira mora aqui; nada repetido no topo."""
    if user is None:
        itens = [Li(A('Entrar', href='/logar')),
                 Li(A('Cadastrar', href='/cadastrar'))]
    else:
        itens = [Li(Span(f'Olá, {user.nome or user.email}',
                         cls='opacity-70 inline-block max-w-48 truncate')),
                 Li(A('Início', href='/')),
                 Li(A('Campeonatos', href='/campeonatos'))]
        if user.role != 'admin':
            itens.append(Li(A('Competir', href='/competir')))
        itens.append(Li(Form(btn('Sair', flat=True, icon='logout', type='submit'),
                             action='/logout', method='post')))
    return Ul(*itens, cls='menu p-4 w-72 min-h-full bg-base-100 shadow-xl')


def navbar(user):
    """Barra do topo: marca + hambúrguer, que abre a sidebar."""
    return Header(
        Div(Label(I('menu', cls='material-icons'),
                  **{'for': DRAWER_ID, 'aria-label': 'Abrir menu'},
                  cls='btn btn-ghost btn-square'),
            A('Competições', href='/', cls='btn btn-ghost text-xl font-bold')),
        cls='navbar bg-base-100 shadow-sm')


def _aviso_cookies():
    """Barra de transparência: cookie de sessão é estritamente necessário
    (LGPD/ePrivacy não exigem consentimento para ele), mas avisar é barato."""
    return Div(
        Span('Usamos só um cookie de sessão — necessário para manter você logado. '
             'Nada de rastreamento.', cls='text-sm'),
        btn('Entendi', dense=True, flat=True, **{'x-on:click': 'aceito()'}),
        **{'x-data': 'avisoCookies()', 'x-show': 'visivel', 'x-cloak': True},
        cls='fixed bottom-4 inset-x-0 z-40 mx-auto w-fit flex items-center gap-3 '
            'bg-base-300 border border-base-content/10 rounded-full px-4 py-2 shadow-lg')


def page(request, title, *content, extra=()):
    """Página completa com drawer (sidebar pelo hambúrguer); `extra` no <body>."""
    user = current_user(request)
    return (Title(title),
            Div(Input(type='checkbox', id=DRAWER_ID, cls='drawer-toggle'),
                Div(navbar(user),
                    Main(*content,
                         cls='mx-auto w-full max-w-4xl flex flex-col gap-4 p-4'),
                    cls='drawer-content flex flex-col min-h-dvh'),
                Div(Label(**{'for': DRAWER_ID}, cls='drawer-overlay'),
                    _menu_lateral(user),
                    cls='drawer-side'),
                cls='drawer bg-base-200'),
            _aviso_cookies(),
            *extra)
