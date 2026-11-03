// Cubo 3D da página /embaralhar (three.js UMD r147 + OrbitControls + Alpine).
// O estado do cubo SÃO os cubinhos: girar uma face = rodar os 9 cubos da
// camada ao redor do eixo; posições são arredondadas após cada giro.
// Andar para TRÁS anima o DESFAZER (contra-giro). Uma seta circular mostra a
// face, o sentido e a quantidade do giro (próximo passo em repouso; durante
// a animação ela gira junto com a camada; no último passo, nenhuma seta).

(function () {
  const PRETO = 0x16161a;
  const COR_SETA = 0xfbbf24;
  const CORES = { R: 0xd94f4f, L: 0xf08c2b, U: 0xf5f5f5, D: 0xf3d435,
                  F: 0x39a85a, B: 0x2f6fdb };
  // giro horário (U em cima, F para o observador): eixo + ângulo base
  const EIXO = { R: 'x', L: 'x', U: 'y', D: 'y', F: 'z', B: 'z' };
  const BASE = { R: -Math.PI / 2, L: Math.PI / 2,
                 U: -Math.PI / 2, D: Math.PI / 2,
                 F: -Math.PI / 2, B: Math.PI / 2 };
  const CAMADA = { R: ['x', 1], L: ['x', -1], U: ['y', 1],
                   D: ['y', -1], F: ['z', 1], B: ['z', -1] };
  const NORMAIS = { R: [1, 0, 0], L: [-1, 0, 0], U: [0, 1, 0],
                    D: [0, -1, 0], F: [0, 0, 1], B: [0, 0, -1] };

  function parse(token) {
    const face = token[0];
    const suf = token.slice(1);
    return { face, mult: suf === "'" ? -1 : (suf === '2' ? 2 : 1) };
  }

  // '↻90°' horário / '↺90°' anti-horário / '180°' (sentido não importa)
  function rotuloDeg(angulo) {
    const deg = Math.round(Math.abs(angulo) * 180 / Math.PI);
    if (deg >= 135) return deg + '\u00B0';
    return (angulo < 0 ? '\u21BB' : '\u21BA') + deg + '\u00B0';
  }

  function fazRodulo(texto) {
    const cv = document.createElement('canvas');
    cv.width = 256; cv.height = 96;
    const ctx = cv.getContext('2d');
    ctx.font = 'bold 56px sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.lineWidth = 10; ctx.strokeStyle = 'rgba(0,0,0,.65)';
    ctx.strokeText(texto, 128, 50);
    ctx.fillStyle = '#fbbf24';
    ctx.fillText(texto, 128, 50);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({
      map: new THREE.CanvasTexture(cv), transparent: true, depthTest: false }));
    sp.name = 'rotulo';
    sp.scale.set(1.25, 1.25 * 96 / 256, 1);
    return sp;
  }

  // Seta em arco sobre a face: varredura = |ângulo|, sentido = o do giro
  // REAL visto de fora da face (por isso o ajuste pelo sinal e·n).
  function fazSeta(face, angulo) {
    const n = new THREE.Vector3(...NORMAIS[face]);
    const e = new THREE.Vector3(...{ x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }[EIXO[face]]);
    const aparente = angulo * e.dot(n);
    const raio = 0.72, N = 24, pts = [];
    for (let i = 0; i <= N; i++) {
      const a = -Math.abs(aparente) / 2 + aparente * (i / N);
      pts.push(new THREE.Vector3(Math.cos(a) * raio, Math.sin(a) * raio, 0));
    }
    const mat = new THREE.MeshBasicMaterial({ color: COR_SETA });
    const g = new THREE.Group();
    g.name = 'seta';
    g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 24, 0.06, 8), mat));
    const fim = pts[pts.length - 1], ante = pts[pts.length - 2];
    const cone = new THREE.Mesh(new THREE.ConeGeometry(0.16, 0.36, 12), mat);
    cone.position.copy(fim);
    cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0),
                                       fim.clone().sub(ante).normalize());
    g.add(cone);
    const rot = fazRodulo(rotuloDeg(angulo));
    rot.position.set(0, 0, 0.55);   // flutua acima da face, virado p/ câmera
    g.add(rot);
    g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), n);
    g.position.copy(n).multiplyScalar(1.66);
    return g;
  }

  class CubeScramble {
    constructor(container, verso) {
      this.container = container;
      this.gen = 0;
      this.anim = null;
      this.seta = null;
      this.ultimo = -1;            // último passo renderizado → direção do anim
      this.movesRef = [];
      this.passoRef = 0;
      const w = container.clientWidth || 360, h = container.clientHeight || 400;
      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 100);
      this.camera.position.set(5.4, 5.6, 7.4);
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      this.renderer.setPixelRatio(window.devicePixelRatio || 1);
      this.renderer.setSize(w, h);
      container.appendChild(this.renderer.domElement);
      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enablePan = false;
      // segundo canvas: MESMA cena, câmera na ANTIPODA da principal (espelhada
      // em X, Y e Z a cada frame) — o que uma visão esconde, a outra mostra
      this.verso = null;
      if (verso) {
        const w2 = verso.clientWidth || 300, h2 = verso.clientHeight || 300;
        this.verso = {
          el: verso,
          renderer: new THREE.WebGLRenderer({ antialias: true, alpha: true }),
          cam: new THREE.PerspectiveCamera(40, w2 / h2, 0.1, 100),
        };
        this.verso.renderer.setPixelRatio(window.devicePixelRatio || 1);
        this.verso.renderer.setSize(w2, h2);
        verso.appendChild(this.verso.renderer.domElement);
      }
      this._build();
      if (window.ResizeObserver) {
        const ro = new ResizeObserver(() => this._resize());
        ro.observe(container);
        if (verso) ro.observe(verso);
      }
      this._loop = this._loop.bind(this);
      requestAnimationFrame(this._loop);
    }

    _build() {
      const geo = new THREE.BoxGeometry(0.96, 0.96, 0.96);
      this.cubies = [];
      for (const x of [-1, 0, 1]) for (const y of [-1, 0, 1]) for (const z of [-1, 0, 1]) {
        const cores = [x === 1 ? CORES.R : PRETO, x === -1 ? CORES.L : PRETO,
                       y === 1 ? CORES.U : PRETO, y === -1 ? CORES.D : PRETO,
                       z === 1 ? CORES.F : PRETO, z === -1 ? CORES.B : PRETO];
        const mesh = new THREE.Mesh(geo, cores.map((c) => new THREE.MeshBasicMaterial({ color: c })));
        mesh.position.set(x, y, z);
        mesh.userData.ini = new THREE.Vector3(x, y, z);
        this.scene.add(mesh);
        this.cubies.push(mesh);
      }
    }

    _resize() {
      const w = this.container.clientWidth, h = this.container.clientHeight;
      if (w && h) {
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(w, h);
      }
      if (this.verso) {
        const w2 = this.verso.el.clientWidth, h2 = this.verso.el.clientHeight;
        if (w2 && h2) {
          this.verso.cam.aspect = w2 / h2;
          this.verso.cam.updateProjectionMatrix();
          this.verso.renderer.setSize(w2, h2);
        }
      }
    }

    _eixo(nome) {
      return new THREE.Vector3(nome === 'x' ? 1 : 0, nome === 'y' ? 1 : 0, nome === 'z' ? 1 : 0);
    }

    _arredonda(c) {
      for (const k of ['x', 'y', 'z']) c.position[k] = Math.round(c.position[k]);
    }

    _girar(token, animar, inverso = false) {
      const { face, mult } = parse(token);
      const angulo = BASE[face] * mult * (inverso ? -1 : 1);
      const axis = this._eixo(EIXO[face]);
      const [e, v] = CAMADA[face];
      const alvo = this.cubies.filter((c) => Math.round(c.position[e]) === v);
      if (!animar) {
        alvo.forEach((c) => {
          c.rotateOnWorldAxis(axis, angulo);
          c.position.applyAxisAngle(axis, angulo);
          this._arredonda(c);
        });
        return null;
      }
      const grupo = new THREE.Group();
      this.scene.add(grupo);
      alvo.forEach((c) => grupo.attach(c));
      return { grupo, alvo, axis, angulo, t0: performance.now(), dur: 220 };
    }

    _assentar(anim) {
      anim.grupo.quaternion.setFromAxisAngle(anim.axis, anim.angulo);
      anim.grupo.updateMatrixWorld(true);
      anim.alvo.forEach((c) => { this.scene.attach(c); this._arredonda(c); });
      this.scene.remove(anim.grupo);
    }

    limpaSeta() {
      if (this.seta) {
        this.seta.removeFromParent();
        this.seta.traverse(o => {
          if (o.geometry) o.geometry.dispose();
          const m = o.material;
          if (m) { if (m.map) m.map.dispose(); m.dispose(); }
        });
        this.seta = null;
      }
    }

    // seta do PRÓXIMO giro, parada sobre a face (some após o último passo)
    setaProxima() {
      this.limpaSeta();
      const m = this.movesRef[this.passoRef];
      if (!m) return;
      const { face, mult } = parse(m);
      this.seta = fazSeta(face, BASE[face] * mult);
      this.scene.add(this.seta);
    }

    reset() {
      this.gen++;
      this.limpaSeta();
      if (this.anim) { this.scene.remove(this.anim.grupo); this.anim = null; }
      this.cubies.forEach((c) => {
        c.position.copy(c.userData.ini);
        c.quaternion.identity();
        this.scene.add(c);
      });
    }

    irPara(passo, moves) {
      const atras = passo < this.ultimo;
      this.ultimo = passo;
      this.movesRef = moves || [];
      this.passoRef = passo;
      this.reset();
      let tokenAnim = null, inverso = false;
      if (atras) {
        // recolora até o estado 'passo+1' e ANIMA o desfazer de moves[passo]
        if (this.movesRef.length) {
          for (let k = 0; k <= passo && k < this.movesRef.length; k++)
            this._girar(this.movesRef[k], false);
          if (passo < this.movesRef.length) { tokenAnim = this.movesRef[passo]; inverso = true; }
        }
      } else {
        for (let k = 0; k < passo - 1; k++) this._girar(this.movesRef[k], false);
        if (passo > 0) tokenAnim = this.movesRef[passo - 1];
      }
      if (tokenAnim) {
        this.anim = this._girar(tokenAnim, true, inverso);
        const { face, mult } = parse(tokenAnim);
        this.seta = fazSeta(face, BASE[face] * mult * (inverso ? -1 : 1));
        this.anim.grupo.add(this.seta);   // seta gira junto com a camada
      } else {
        this.setaProxima();
      }
    }

    _loop() {
      requestAnimationFrame(this._loop);
      if (this.anim) {
        const p = Math.min(1, (performance.now() - this.anim.t0) / this.anim.dur);
        const ease = 1 - Math.pow(1 - p, 3);
        this.anim.grupo.quaternion.setFromAxisAngle(this.anim.axis, this.anim.angulo * ease);
        if (p >= 1) { const a = this.anim; this.anim = null; this._assentar(a); this.setaProxima(); }
      }
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
      if (this.verso) {
        const cam = this.verso.cam, q = this.camera.position;
        cam.position.set(-q.x, -q.y, -q.z);  // antípoda exata: onde a principal
        cam.up.set(0, 1, 0);                 // vê o topo, o verso vê a base
        cam.lookAt(0, 0, 0);
        this.verso.renderer.render(this.scene, cam);
      }
    }
  }

  window.CubeScramble = CubeScramble;

  // O MUNDO three.js vive AQUI, fora do objeto x-data: o Alpine envolve o
  // x-data inteiro num Proxy reativo (estilo Vue) que quebra propriedades
  // não-configuráveis do three.js (modelViewMatrix) e faz o renderer PULAR
  // malhas — os 'cubos que sumiam' ao trocar de passo.
  let viewer = null;

  // componente Alpine: #passo selecionado <-> cubo
  window.cubeView = function () {
    return {
      passo: 0,
      moves: [],
      init() {
        this.moves = JSON.parse(this.$el.dataset.moves || '[]');
        const alvo = document.getElementById('cubo-3d');
        const montar = () => {
          if (window.THREE && window.CubeScramble && alvo && !alvo.dataset.vivo) {
            alvo.dataset.vivo = '1';
            viewer = new CubeScramble(alvo, document.getElementById('cubo-3d-verso'));
            alvo.__cubo = viewer;  // gancho p/ inspeção (smoke/shots)
          }
          if (viewer) viewer.irPara(this.passo, this.moves);
        };
        montar();
        // three.js chega DEPOIS do boot do Alpine (defer da página): monta no
        // DOMContentLoaded, quando todo defer já rodou (guard: data-vivo).
        document.addEventListener('DOMContentLoaded', montar);
      },
      g(m) { return m.endsWith('2') ? '180°' : (m.endsWith("'") ? '↺90°' : '↻90°'); },
      get passos() {
        return ['#0 · início'].concat(
          this.moves.map((m, k) => '#' + (k + 1) + ' · ' + m + ' · ' + this.g(m)));
      },
      irPara(i) {
        const n = Math.max(0, Math.min(i, this.moves.length));
        if (n === this.passo) return;   // último passo: clicar/arrastar adiante não move
        this.passo = n;
        if (viewer) viewer.irPara(n, this.moves);
        this.$nextTick(() => {
          const el = this.$el.querySelector('[data-passo="' + this.passo + '"]');
          if (el) el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
        });
      },
      // arrastar a faixa de passos troca de passo (36px por passo)
      scrubStart(e) { this._sx = e.clientX; },
      scrubMove(e) {
        if (this._sx == null) return;
        const d = this._sx - e.clientX;
        if (Math.abs(d) >= 36) { this._sx = e.clientX; this.irPara(this.passo + (d > 0 ? 1 : -1)); }
      },
      scrubEnd() { this._sx = null; },
    };
  };
})();
