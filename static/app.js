// Componentes Alpine do cliente (antes eram o CLIENT_JS inline). Servido de
// /static/app.js; ativado por atributos x-data="..." no HTML — sem <script> inline.

function qs_fmt(ms) {
  ms = Math.max(0, ms);
  const m = Math.floor(ms / 60000), s = Math.floor(ms / 1000) % 60, t = ms % 1000;
  return m + ':' + String(s).padStart(2, '0') + '.' + String(t).padStart(3, '0');
}

// Cronômetro em andamento: atualiza a partir de `inicio` (epoch ms) até o
// nó sair da DOM (troca de painel pelo htmx).
function relogio(inicio) {
  return {
    txt: '0:00.000',
    init() {
      this._t = setInterval(() => {
        if (!this.$el.isConnected) { clearInterval(this._t); return; }
        this.txt = qs_fmt(Date.now() - Number(inicio));
      }, 10);
    },
    destroy() { clearInterval(this._t); },
  };
}

// Contagem regressiva até o início do campeonato (epoch ms).
function contagem(alvoMs) {
  return {
    txt: '…',
    init() {
      const passo = () => {
        if (!this.$el.isConnected) { clearInterval(this._t); return; }
        const resta = Number(alvoMs) - Date.now();
        if (resta <= 0) {
          this.txt = 'Começou! Aguarde a liberação das tentativas.';
          clearInterval(this._t);
          return;
        }
        const s = Math.floor(resta / 1000), d = Math.floor(s / 86400);
        this.txt = (d ? d + 'd ' : '')
          + String(Math.floor(s / 3600) % 24).padStart(2, '0') + 'h '
          + String(Math.floor(s / 60) % 60).padStart(2, '0') + 'm '
          + String(s % 60).padStart(2, '0') + 's';
      };
      passo();
      this._t = setInterval(passo, 1000);
    },
    destroy() { clearInterval(this._t); },
  };
}

// Escuta /ws e recarrega `target` via htmx quando algo muda (exceto enquanto
// há um cronômetro em andamento — [data-stop] cobre a tela toda).
function live(url, target) {
  return {
    init() {
      const abrir = () => {
        this._ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://')
                                 + location.host + '/ws');
        this._ws.onmessage = () => {
          if (document.querySelector('[data-stop]')) return;
          if (typeof htmx !== 'undefined') htmx.ajax('GET', url, { target, swap: 'outerHTML' });
        };
        this._ws.onclose = () => { this._rt = setTimeout(abrir, 1000); };
        this._ws.onerror = () => this._ws.close();
      };
      abrir();
    },
    destroy() {
      if (this._ws) { this._ws.onclose = null; this._ws.close(); }
      clearTimeout(this._rt);
    },
  };
}

// Aviso de cookies (LGPD/ePrivacy: banner informativo, dispensável para cookie
// estritamente necessário, mas é transparência barata). Some após aceitar.
function avisoCookies() {
  return {
    visivel: !localStorage.getItem('qs-aviso-cookies'),
    aceito() { localStorage.setItem('qs-aviso-cookies', '1'); this.visivel = false; },
  };
}

const _qs_pickers = () => {
  document.querySelectorAll('[data-fp-datetime]').forEach((el) => {
    if (el._qsFp) return; el._qsFp = 1;
    flatpickr(el, { enableTime: true, time_24hr: true, allowInput: true,
                    dateFormat: 'Y-m-d H:i' });
  });
  document.querySelectorAll('[data-fp-mmss]').forEach((el) => {
    if (el._qsFp) return; el._qsFp = 1;
    flatpickr(el, { noCalendar: true, enableTime: true, enableSeconds: true,
                    time_24hr: true, allowInput: true, defaultHour: 0,
                    dateFormat: 'i:s', className: 'fp-mmss' });
  });
};
if (document.readyState === 'loading')
  document.addEventListener('DOMContentLoaded', _qs_pickers);
else _qs_pickers();
document.addEventListener('htmx:afterSwap', () => {
  _qs_pickers();
  if (window.Alpine) Alpine.initTree(document.body);
});
