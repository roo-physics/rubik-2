"""Página de apoio: um embaralhamento fixo (estilo WCA), passo a passo, com
cubo 3D girável em three.js. Conteúdo educativo — não toca em dados."""

import json

from fasthtml.common import *

from auth import require_login
from components.daisy import btn, page

SCRAMBLE = ["R", "U2", "R'", "F'", "U", "B'", "D2", "L", "R", "U2",
            "F'", "L2", "D", "U'", "R2"]

# three.js é pesado e só desta página: carrega por `extra` (o init do cubo
# espera por ele, ver static/scramble.js). UMD r147: último build com
# examples/js clássico (sem bundler, igual ao resto do app).
CDN = (
    Script(src='https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js', defer=True),
    Script(src='https://cdn.jsdelivr.net/npm/three@0.147.0/examples/js/controls/OrbitControls.js',
           defer=True),
)


def register(rt):
    @rt('/embaralhar', before=require_login)
    def get(request: Request):
        chips = Template(
            Button(**{'x-text': 'lab',
                      '@click': 'irPara(i)',
                      'cls': 'cursor-pointer select-none shrink-0',
                      'x-bind:class': "passo === i ? 'badge badge-primary badge-lg' "
                                       ": 'badge badge-outline badge-lg'",
                      'x-bind:data-passo': 'i'}),
            **{'x-for': '(lab, i) in passos'},
        )
        faixa = Div(chips,
                    **{'@pointerdown': 'scrubStart($event)',
                       '@pointermove': 'scrubMove($event)',
                       '@pointerup': 'scrubEnd($event)',
                       '@pointerleave': 'scrubEnd($event)'},
                    cls='w-full flex flex-nowrap items-center gap-1.5 overflow-x-auto '
                        'select-none cursor-ew-resize py-1',
                    style='touch-action: pan-x; scrollbar-width: none')
        painel = Div(
            faixa,
            Div(
                btn('‹ anterior', color=None, dense=True, **{'@click': 'irPara(passo - 1)'}),
                btn('próximo ›', color=None, dense=True, **{'@click': 'irPara(passo + 1)'}),
                Span(**{'x-text': "'passo ' + passo + ' de ' + moves.length",
                        'cls': 'badge badge-ghost ml-2'}),
                cls='flex flex-wrap items-center gap-2',
            ),
            Div(
                Div(id='cubo-3d',
                    cls='flex-1 min-w-0 w-full h-[380px] md:h-[520px] rounded-box border border-base-300'),
                Div(id='cubo-3d-verso',
                    cls='flex-1 min-w-0 w-full h-[240px] md:h-[520px] rounded-box border border-base-300'),
                cls='flex flex-col md:flex-row gap-3 w-full',
            ),
            Div('Arraste para girar o cubo; roda do mouse / pinça para dar zoom. '
                'O segundo cubo mostra sempre o lado oposto — a seta e os graus '
                'valem nas duas visões.',
                cls='text-xs opacity-60'),
            **{'x-data': 'cubeView()', 'data-moves': json.dumps(SCRAMBLE)},
            cls='card bg-base-100 shadow-sm p-5 flex flex-col gap-3 items-start w-full',
        )
        return page(request, 'Embaralhar',
                    Div('Embaralhar o cubo', cls='text-2xl font-bold'),
                    Div('Sequência fixa de embaralhamento — clique num passo para ver o '
                        'cubo naquele estado (passo a passo até a posição final).',
                        cls='opacity-70'),
                    painel,
                    extra=CDN)
