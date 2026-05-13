/**
 * data-agents-api · escritório dos agentes
 *
 * Three.js cena isométrica + WebSocket client conectando ao backend
 * /events. Reage a 4 tipos de evento:
 *
 *   delegation          → beam Supervisor → agente + monitor pulsa
 *   tool_call           → monitor do agente pulsa com cor da plataforma
 *   dispatcher_decision → agentes não selecionados adormecem visualmente
 *   session_end         → reset cena, exibe métricas finais
 *
 * Sem build step — script puro carregado pela página.
 */

(function () {
  'use strict';

  // ─── Config ────────────────────────────────────────────────────────────────

  const TIER_COLORS = { T0: 0x4ade80, T1: 0x3a8eff, T2: 0xa78bfa, T3: 0x94a3b8 };
  const SLEEP_GRAY = 0x4a4d5a;
  const PLATFORM_COLORS = {
    databricks: 0xff5722,
    fabric: 0x0078d4,
    migration: 0xf4c875,
    postgres: 0x336791,
    docs: 0x60a5fa,
    memory: 0xa78bfa,
    github: 0xdde2f0,
    web: 0x5dcaa5,
  };

  // ─── Three.js setup ────────────────────────────────────────────────────────

  const sceneEl = document.getElementById('scene');
  const scene = new THREE.Scene();
  // Fog ciano-azulado dá aquele clima "cyberpunk noturno"
  scene.fog = new THREE.Fog(0x0a1422, 22, 48);

  const FRUSTUM = 22;
  let aspect = window.innerWidth / window.innerHeight;
  const camera = new THREE.OrthographicCamera(
    -FRUSTUM * aspect / 2, FRUSTUM * aspect / 2,
    FRUSTUM / 2, -FRUSTUM / 2,
    0.1, 100
  );
  camera.position.set(14, 14, 14);
  camera.lookAt(0, 0, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);
  // Sombras realistas — soft shadow map dá profundidade ao escritório
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  sceneEl.appendChild(renderer.domElement);

  // Ambient mais frio + sun mais branco/azulado (estética futurista)
  scene.add(new THREE.AmbientLight(0x8090c0, 0.5));
  const sun = new THREE.DirectionalLight(0xddeeff, 0.85);
  sun.position.set(8, 14, 4);
  sun.castShadow = true;
  sun.shadow.mapSize.width = 2048;
  sun.shadow.mapSize.height = 2048;
  sun.shadow.camera.left = -16;
  sun.shadow.camera.right = 16;
  sun.shadow.camera.top = 16;
  sun.shadow.camera.bottom = -10;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 40;
  sun.shadow.bias = -0.0005;
  scene.add(sun);
  // Rim azul vibrante pra silhuetar os bonecos
  const rim = new THREE.DirectionalLight(0x00aaff, 0.4);
  rim.position.set(-8, 6, -4);
  scene.add(rim);

  // Pontos de luz ciano nos cantos do escritório (estética datacenter)
  const corner1 = new THREE.PointLight(0x00ddff, 0.6, 12);
  corner1.position.set(-14, 3, -7);
  scene.add(corner1);
  const corner2 = new THREE.PointLight(0x00ddff, 0.6, 12);
  corner2.position.set(14, 3, 7);
  scene.add(corner2);
  const corner3 = new THREE.PointLight(0xaa66ff, 0.4, 10);
  corner3.position.set(-14, 3, 7);
  scene.add(corner3);
  const corner4 = new THREE.PointLight(0xaa66ff, 0.4, 10);
  corner4.position.set(14, 3, -7);
  scene.add(corner4);

  // Floor base escuro (datacenter style)
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(34, 16),
    new THREE.MeshStandardMaterial({ color: 0x161a26, roughness: 0.7 })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // Grid neon ciano sobre o chão (cyberpunk!)
  const grid = new THREE.GridHelper(34, 17, 0x00ddff, 0x004258);
  grid.position.y = 0.01;
  grid.material.transparent = true;
  grid.material.opacity = 0.55;
  scene.add(grid);

  // (faixa de energia removida — grid neon ciano já dá identidade visual
  // ao chão sem ofuscar os bonecos)

  function wall(x, z, w, d) {
    const g = new THREE.Mesh(
      new THREE.BoxGeometry(w, 1.6, d),
      new THREE.MeshStandardMaterial({
        color: 0x1a1f2e,
        emissive: 0x002238,
        emissiveIntensity: 0.15,
        roughness: 0.85,
      })
    );
    g.position.set(x, 0.8, z);
    g.receiveShadow = true;
    scene.add(g);
  }
  wall(0, -7.5, 30, 0.2);
  wall(0, +7.5, 30, 0.2);
  wall(-15, 0, 0.2, 16);
  wall(+15, 0, 0.2, 16);

  // ─── Construtores reutilizáveis ────────────────────────────────────────────

  // ─── Texturas estilo Minecraft pra cabeça ──────────────────────────────────
  // 6 faces (right, left, top, bottom, front, back). Frente tem o rosto;
  // topo tem cabelo; resto é pele.

  function _mkPixelTexture(drawFn, size = 32) {
    const c = document.createElement('canvas');
    c.width = size; c.height = size;
    const ctx = c.getContext('2d');
    drawFn(ctx, size);
    const tex = new THREE.CanvasTexture(c);
    tex.magFilter = THREE.NearestFilter; // pixel art crisp (sem blur)
    tex.minFilter = THREE.NearestFilter;
    return tex;
  }

  function makeMinecraftHeadMaterials(skinHex = 0xe8c8a0, hairHex = '#3a2a1a', eyeHex = '#222') {
    const skin = '#' + skinHex.toString(16).padStart(6, '0');
    // color=white pra textura aparecer sem tint. Quando o agente dorme,
    // setAsleep muda color pra cinza, escurecendo a textura naturalmente.
    const mkMat = (tex) => new THREE.MeshStandardMaterial({
      map: tex, color: 0xffffff, transparent: true, roughness: 0.65,
    });

    // Side (lateral): pele com franja de cabelo no topo
    const sideTex = _mkPixelTexture((ctx, s) => {
      ctx.fillStyle = skin;
      ctx.fillRect(0, 0, s, s);
      ctx.fillStyle = hairHex;
      ctx.fillRect(0, 0, s, s * 0.22); // franja
    });
    // Top: só cabelo
    const topTex = _mkPixelTexture((ctx, s) => {
      ctx.fillStyle = hairHex;
      ctx.fillRect(0, 0, s, s);
    });
    // Bottom (queixo): só pele
    const bottomTex = _mkPixelTexture((ctx, s) => {
      ctx.fillStyle = skin;
      ctx.fillRect(0, 0, s, s);
    });
    // Front (rosto): pele + cabelo + olhos + boca
    const frontTex = _mkPixelTexture((ctx, s) => {
      ctx.fillStyle = skin;
      ctx.fillRect(0, 0, s, s);
      // Cabelo (franja no topo)
      ctx.fillStyle = hairHex;
      ctx.fillRect(0, 0, s, s * 0.22);
      // Olhos (2 quadrados escuros)
      ctx.fillStyle = eyeHex;
      ctx.fillRect(s * 0.20, s * 0.42, s * 0.16, s * 0.13);
      ctx.fillRect(s * 0.64, s * 0.42, s * 0.16, s * 0.13);
      // Pupilas brancas (dá vida)
      ctx.fillStyle = '#fff';
      ctx.fillRect(s * 0.26, s * 0.46, s * 0.06, s * 0.06);
      ctx.fillRect(s * 0.70, s * 0.46, s * 0.06, s * 0.06);
      // Boca
      ctx.fillStyle = '#7a4030';
      ctx.fillRect(s * 0.34, s * 0.72, s * 0.32, s * 0.06);
    });
    // Back (nuca): cabelo cobrindo mais que a frente
    const backTex = _mkPixelTexture((ctx, s) => {
      ctx.fillStyle = skin;
      ctx.fillRect(0, 0, s, s);
      ctx.fillStyle = hairHex;
      ctx.fillRect(0, 0, s, s * 0.5);
    });

    // BoxGeometry material order: [+x, -x, +y, -y, +z, -z]
    return [
      mkMat(sideTex),    // right (lateral)
      mkMat(sideTex.clone()), // left
      mkMat(topTex),     // top (cabelo)
      mkMat(bottomTex),  // bottom (queixo)
      mkMat(frontTex),   // front (rosto)
      mkMat(backTex),    // back (nuca)
    ];
  }

  function voxelPerson(shirt, skinHex = 0xe8c8a0, hairHex = '#3a2a1a') {
    const g = new THREE.Group();
    const skin = skinHex;
    const headMats = makeMinecraftHeadMaterials(skin, hairHex);
    const head = new THREE.Mesh(
      new THREE.BoxGeometry(0.45, 0.45, 0.45),
      headMats // 6 materials, um por face
    );
    head.position.y = 1.45;
    head.castShadow = true;
    g.add(head);
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 0.65, 0.35),
      new THREE.MeshStandardMaterial({ color: shirt, transparent: true, roughness: 0.6 })
    );
    body.position.y = 0.9;
    body.castShadow = true;
    g.add(body);
    const armMat = new THREE.MeshStandardMaterial({ color: shirt, transparent: true, roughness: 0.6 });
    const armL = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.55, 0.18), armMat);
    armL.position.set(-0.35, 0.9, 0);
    armL.castShadow = true;
    g.add(armL);
    const armR = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.55, 0.18), armMat);
    armR.position.set(0.35, 0.9, 0);
    armR.castShadow = true;
    g.add(armR);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x2a2a35, transparent: true, roughness: 0.6 });
    const legL = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.55, 0.22), legMat);
    legL.position.set(-0.13, 0.28, 0);
    legL.castShadow = true;
    g.add(legL);
    const legR = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.55, 0.22), legMat);
    legR.position.set(0.13, 0.28, 0);
    legR.castShadow = true;
    g.add(legR);
    // materials array inclui os 6 materials da cabeça (tinting pra sleep mode)
    // + body + braços + pernas
    return {
      group: g, head, body, armL, armR, legL, legR,
      headMaterials: headMats,
      materials: [...headMats, body.material, armMat, legMat],
    };
  }

  function deskWithChair(facing) {
    const g = new THREE.Group();
    const top = new THREE.Mesh(
      new THREE.BoxGeometry(1.4, 0.08, 0.7),
      new THREE.MeshStandardMaterial({ color: 0x9b7a4f, roughness: 0.7 })
    );
    top.position.y = 0.7;
    top.castShadow = true;
    top.receiveShadow = true;
    g.add(top);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x6e5538, roughness: 0.7 });
    [[-0.6, -0.3], [0.6, -0.3], [-0.6, 0.3], [0.6, 0.3]].forEach(([x, z]) => {
      const l = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.7, 0.06), legMat);
      l.position.set(x, 0.35, z);
      l.castShadow = true;
      g.add(l);
    });
    const monBase = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.12, 0.12),
      new THREE.MeshStandardMaterial({ color: 0x222 })
    );
    monBase.position.set(0, 0.78, 0.15 * facing);
    monBase.castShadow = true;
    g.add(monBase);
    const screenMat = new THREE.MeshStandardMaterial({
      color: 0x0a0a14,
      emissive: 0x3a8eff,
      emissiveIntensity: 0.5,
    });
    const monitor = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.38, 0.05), screenMat);
    monitor.position.set(0, 1.0, 0.2 * facing);
    monitor.rotation.y = facing > 0 ? 0 : Math.PI;
    monitor.castShadow = true;
    g.add(monitor);
    const kb = new THREE.Mesh(
      new THREE.BoxGeometry(0.45, 0.03, 0.15),
      new THREE.MeshStandardMaterial({ color: 0x3a3a45 })
    );
    kb.position.set(0, 0.755, -0.18 * facing);
    kb.castShadow = true;
    g.add(kb);

    // Caneca de café — pequeno cilindro escuro com tampo branco (vapor)
    const mug = new THREE.Mesh(
      new THREE.CylinderGeometry(0.06, 0.05, 0.12, 12),
      new THREE.MeshStandardMaterial({ color: 0x6e3a1f, roughness: 0.5 })
    );
    mug.position.set(0.45, 0.79, -0.18 * facing);
    mug.castShadow = true;
    g.add(mug);

    // Pilha de papéis empilhados
    const papers = new THREE.Mesh(
      new THREE.BoxGeometry(0.22, 0.04, 0.16),
      new THREE.MeshStandardMaterial({ color: 0xf0ecd8, roughness: 0.9 })
    );
    papers.position.set(-0.45, 0.76, -0.18 * facing);
    papers.castShadow = true;
    g.add(papers);

    const chair = new THREE.Group();
    const seat = new THREE.Mesh(
      new THREE.BoxGeometry(0.45, 0.08, 0.45),
      new THREE.MeshStandardMaterial({ color: 0x4a4a58, roughness: 0.7 })
    );
    seat.position.y = 0.42;
    seat.castShadow = true;
    chair.add(seat);
    const back = new THREE.Mesh(
      new THREE.BoxGeometry(0.45, 0.55, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x4a4a58, roughness: 0.7 })
    );
    // Encosto fica do lado OPOSTO ao monitor (atrás do boneco, perto da parede)
    back.position.set(0, 0.7, -0.22 * facing);
    back.castShadow = true;
    chair.add(back);
    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.04, 0.4),
      new THREE.MeshStandardMaterial({ color: 0x222 })
    );
    stem.position.y = 0.2;
    chair.add(stem);
    chair.position.z = -0.7 * facing;
    g.add(chair);

    return { group: g, monitor, screenMat, chair };
  }

  // Holograma piramidal ciano + base metálica — substitui as plantas (visual futurista)
  function plant() {
    const g = new THREE.Group();
    // Base metálica
    const base = new THREE.Mesh(
      new THREE.CylinderGeometry(0.28, 0.32, 0.08, 8),
      new THREE.MeshStandardMaterial({
        color: 0x1a2030,
        metalness: 0.9,
        roughness: 0.2,
      })
    );
    base.position.y = 0.04;
    base.castShadow = true;
    g.add(base);

    // Anel ciano emissivo na base (efeito projetor)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.18, 0.26, 24),
      new THREE.MeshBasicMaterial({
        color: 0x00ddff,
        transparent: true,
        opacity: 0.85,
        side: THREE.DoubleSide,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.09;
    g.add(ring);

    // Pirâmide holográfica (cone translúcido brilhante)
    const holo = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.35, 0),
      new THREE.MeshStandardMaterial({
        color: 0x00ddff,
        emissive: 0x00aaee,
        emissiveIntensity: 0.9,
        transparent: true,
        opacity: 0.55,
      })
    );
    holo.position.y = 0.65;
    g.add(holo);

    // Animação handled fora — guardamos referência pra rotacionar no loop
    g.userData.holo = holo;
    return g;
  }

  function nameplate(text, color) {
    const c = document.createElement('canvas');
    c.width = 320; c.height = 80;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, 320, 80);
    ctx.fillStyle = 'rgba(15, 18, 28, 0.92)';
    ctx.beginPath();
    ctx.roundRect(0, 20, 320, 40, 8);
    ctx.fill();
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(296, 40, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = '600 28px sans-serif';
    ctx.fillStyle = '#dde2f0';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, 16, 40);
    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    sprite.scale.set(2.0, 0.5, 1);
    return { sprite, canvas: c, ctx, tex };
  }

  function redrawNameplate(np, text, color, opacity) {
    np.ctx.clearRect(0, 0, 320, 80);
    np.ctx.globalAlpha = opacity;
    np.ctx.fillStyle = 'rgba(15, 18, 28, 0.92)';
    np.ctx.beginPath();
    np.ctx.roundRect(0, 20, 320, 40, 8);
    np.ctx.fill();
    np.ctx.fillStyle = color;
    np.ctx.beginPath();
    np.ctx.arc(296, 40, 7, 0, Math.PI * 2);
    np.ctx.fill();
    np.ctx.font = '600 28px sans-serif';
    np.ctx.fillStyle = '#dde2f0';
    np.ctx.fillText(text, 16, 40);
    np.tex.needsUpdate = true;
    np.ctx.globalAlpha = 1;
  }

  function makeZ() {
    const c = document.createElement('canvas');
    c.width = 64; c.height = 64;
    const ctx = c.getContext('2d');
    ctx.font = '500 40px sans-serif';
    ctx.fillStyle = 'rgba(200, 200, 255, 0.75)';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('z', 32, 32);
    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0 }));
    sprite.scale.set(0.5, 0.5, 1);
    return sprite;
  }

  // ─── Plantas decorativas ───────────────────────────────────────────────────

  // Hologramas nos 4 cantos do escritório maior + 2 nas laterais externas
  const _holograms = [];
  [[-13.5, -6.5], [-13.5, 6.5], [13.5, -6.5], [13.5, 6.5], [-13.5, 0], [13.5, 0]].forEach(([x, z]) => {
    const p = plant();
    p.position.set(x, 0, z);
    scene.add(p);
    _holograms.push(p.userData.holo);
  });

  // ─── Supervisor ────────────────────────────────────────────────────────────

  const supDeskGroup = new THREE.Group();
  const supTable = new THREE.Mesh(
    new THREE.CylinderGeometry(0.9, 0.95, 0.12, 8),
    new THREE.MeshStandardMaterial({ color: 0xb89060, roughness: 0.6 })
  );
  supTable.position.y = 0.75;
  supTable.castShadow = true;
  supTable.receiveShadow = true;
  supDeskGroup.add(supTable);
  const supPedestal = new THREE.Mesh(
    new THREE.CylinderGeometry(0.4, 0.5, 0.7, 6),
    new THREE.MeshStandardMaterial({ color: 0x6e5538 })
  );
  supPedestal.position.y = 0.35;
  supPedestal.castShadow = true;
  supDeskGroup.add(supPedestal);
  const lampPole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.03, 0.03, 0.6),
    new THREE.MeshStandardMaterial({ color: 0x222 })
  );
  lampPole.position.y = 1.15;
  supDeskGroup.add(lampPole);
  const lampShade = new THREE.Mesh(
    new THREE.ConeGeometry(0.18, 0.18, 6),
    new THREE.MeshStandardMaterial({ color: 0xf4c875, emissive: 0xf4c875, emissiveIntensity: 0.4 })
  );
  lampShade.position.y = 1.45;
  lampShade.rotation.x = Math.PI;
  supDeskGroup.add(lampShade);
  // Supervisor à DIREITA do escritório (eixo +X), em x=+9 — afastado da
  // fileira do meio (que vai até x=+1) e com 5u de respiro até a parede
  // (em x=+15).
  supDeskGroup.position.set(9, 0, 0);
  scene.add(supDeskGroup);

  // Supervisor com camisa dourada + skin dourado pálido + cabelo claro
  const supPerson = voxelPerson(0xf4c875, 0xfde68a, '#7a5a00');
  supPerson.group.position.set(9, 0, 0.5);
  // Encara -X (em direção aos 14 agentes que estão em x=-8..+4)
  // rotation.y = -π/2 aponta a frente do mesh pra -x
  supPerson.group.rotation.y = -Math.PI / 2;
  scene.add(supPerson.group);

  const supRing = new THREE.Mesh(
    new THREE.RingGeometry(1.2, 1.3, 32),
    new THREE.MeshBasicMaterial({ color: 0xf4c875, transparent: true, opacity: 0.4, side: THREE.DoubleSide })
  );
  supRing.rotation.x = -Math.PI / 2;
  supRing.position.set(9, 0.02, 0);
  scene.add(supRing);

  // Spark da lâmpada — sobe quando supervisor pulsa
  const lampSpark = new THREE.Mesh(
    new THREE.SphereGeometry(0.18, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xfff2cc, transparent: true, opacity: 0 })
  );
  lampSpark.position.set(9, 1.55, 0);
  scene.add(lampSpark);

  // Aro pulsante adicional (dourado vibrante) quando supervisor está ativo
  const supPulseRing = new THREE.Mesh(
    new THREE.RingGeometry(1.35, 1.45, 48),
    new THREE.MeshBasicMaterial({ color: 0xfff2aa, transparent: true, opacity: 0, side: THREE.DoubleSide })
  );
  supPulseRing.rotation.x = -Math.PI / 2;
  supPulseRing.position.set(9, 0.04, 0);
  scene.add(supPulseRing);

  const dispRing = new THREE.Mesh(
    new THREE.RingGeometry(1.55, 1.62, 64),
    new THREE.MeshBasicMaterial({ color: 0x5dcaa5, transparent: true, opacity: 0, side: THREE.DoubleSide })
  );
  dispRing.rotation.x = -Math.PI / 2;
  dispRing.position.set(9, 0.03, 0);
  scene.add(dispRing);

  // ─── Estado dos agentes ────────────────────────────────────────────────────

  const agents = new Map(); // name → agentObj
  const agentList = [];     // ordem estável

  function createAgent(name, tier, idx, total) {
    // Layout: 3 fileiras horizontais (5+4+5 = 14), supervisor à direita
    // em x=+11. Todos os agentes olham pra +x. Fileira do meio (z=0) tem
    // 4 agentes pra deixar espaço onde o supervisor está alinhado.
    let fileira, colIdx, rowsInFileira, z;
    if (idx < 5) {
      fileira = 'top'; colIdx = idx; rowsInFileira = 5; z = +4.5;
    } else if (idx < 9) {
      fileira = 'mid'; colIdx = idx - 5; rowsInFileira = 4; z = 0;
    } else {
      fileira = 'bot'; colIdx = idx - 9; rowsInFileira = 5; z = -4.5;
    }
    // Fileira top/bot: 5 mesas em x=-8..+4 (spacing 3u entre centros)
    // Fileira mid: 4 mesas em x=-8..+1 (mesmo spacing, mais curta — deixa
    // o supervisor à direita visualmente isolado)
    const xStart = -8;
    const x = xStart + colIdx * 3.0;
    const facing = 1; // todos os agentes têm mesmo facing local

    const color = TIER_COLORS[tier] || TIER_COLORS.T2;
    const desk = deskWithChair(facing);
    desk.group.position.set(x, 0, z);
    // Rotação +π/2 mantém compatibilidade com a estrutura interna do
    // deskWithChair (que orienta no eixo Z local). Após rotação, o monitor
    // local +z vira global +x (perto do supervisor à direita), e a cadeira
    // local -z vira global -x (atrás do boneco).
    desk.group.rotation.y = Math.PI / 2;
    scene.add(desk.group);

    // Boneco do lado ESQUERDO da mesa (oposto ao supervisor), olhando pra
    // +x — todos viram pro supervisor à direita.
    // rotation.y = +π/2 encara +x (DIREÇÃO DO SUPERVISOR em x=+9).
    const person = voxelPerson(color);
    person.group.position.set(x - 0.5, 0.4, z);
    person.group.rotation.y = Math.PI / 2;
    person.legL.visible = false;
    person.legR.visible = false;
    person.body.position.y = 0.5;
    person.head.position.y = 1.05;
    person.armL.position.y = 0.5;
    person.armR.position.y = 0.5;
    scene.add(person.group);

    // Halo no chão SOB o boneco
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.55, 0.7, 32),
      new THREE.MeshBasicMaterial({
        color: 0x5dcaa5,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
      })
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.set(x - 0.5, 0.03, z);
    scene.add(halo);

    // Nameplate flutua acima da cabeça do boneco
    const np = nameplate(name, '#' + color.toString(16).padStart(6, '0'));
    np.sprite.position.set(x - 0.5, 1.95, z);
    scene.add(np.sprite);

    const zSprite = makeZ();
    zSprite.position.set(x - 0.5, 1.85, z);
    scene.add(zSprite);

    return {
      name, tier, baseColor: color, facing,
      // pos = onde os beams chegam (cabeça do boneco)
      pos: { x: x - 0.3, y: 1.2, z: z },
      desk, person, nameplate: np, zSprite, halo,
      asleep: false,
      working: false,
      pulse: 0,
      idlePhase: Math.random() * Math.PI * 2,
      currentEmissive: 0.5,
      targetEmissive: 0.5,
      currentPlatformColor: null,
      lastBeamAt: 0, // timestamp do último beam — usado pra recorrência
    };
  }

  // Intervalo entre beams recorrentes pro mesmo agente trabalhando
  const BEAM_RECURRENCE_MS = 2500;

  // ─── HUD helpers ───────────────────────────────────────────────────────────

  const $phase = document.getElementById('phase-label');
  const $active = document.getElementById('active-count');
  const $cost = document.getElementById('cost');
  const $turns = document.getElementById('turn-count');
  const $log = document.getElementById('task-log');
  const $disp = document.getElementById('dispatch-toast');
  const $dispMsg = document.getElementById('dispatch-msg');
  const $loading = document.getElementById('loading');
  const $loadingText = document.getElementById('loading-text');
  const $badgeRow = document.getElementById('badge-row');
  const $connDot = document.getElementById('conn-dot');
  const $connLabel = document.getElementById('conn-label');

  let cost = 0;
  let turns = 0;
  const agentsSeenThisSession = new Set(); // pra contagem dinâmica

  // Estado de "quem está trabalhando agora" — continuamente, sem decay.
  // Os logs do projeto não atribuem tool_call.agent_name à maioria das tools,
  // mas o workflow_step nos dá o agente ativo do momento. Tracking simples:
  //   - currentWorker='supervisor' até primeira delegation
  //   - delegation X → currentWorker=X, todas as tools subsequentes pulsam X
  //   - delegation Y → currentWorker=Y, X para de pulsar
  //   - session_end → tudo zera
  let currentWorker = null;        // null | 'supervisor' | nome de agente
  let supervisorActive = false;    // true = lâmpada pulsa contínuo
  let lastEventAt = performance.now();

  function updateActiveCount() {
    // Mostra "X/14 ativos nesta sessão" enquanto dispatcher_decision
    // não chegar. Se dispatcher_decision já tiver chegado, ele sobrescreve.
    if (agents.size > 0) {
      $active.textContent = `${agentsSeenThisSession.size}/${agents.size}`;
    }
  }

  function shortenTool(tool) {
    if (!tool) return '';
    // Tira o prefixo mcp__plataforma__ pra log curto
    if (tool.startsWith('mcp__')) {
      const parts = tool.split('__');
      return parts[parts.length - 1];
    }
    return tool;
  }

  function setConnStatus(state, label) {
    $connDot.classList.remove('connected', 'connecting', 'disconnected');
    $connDot.classList.add(state);
    $connLabel.textContent = label;
  }

  function logTask(html) {
    $log.innerHTML = html;
  }

  function setAsleep(agent, sleep) {
    agent.asleep = sleep;
    if (sleep) {
      agent.targetEmissive = 0;
      // Tinge todos materials (incluindo 6 da cabeça) com cinza — escurece textura
      agent.person.materials.forEach((m) => m.color.setHex(SLEEP_GRAY));
      agent.badge.style.opacity = '0.18';
      agent.badge.style.transform = 'scale(0.7)';
    } else {
      agent.targetEmissive = 0.5;
      // Restaura: body/braços voltam pra cor da camisa, cabeça volta pra
      // branco (color=white = textura intacta, sem tint)
      agent.person.body.material.color.setHex(agent.baseColor);
      agent.person.armL.material.color.setHex(agent.baseColor);
      agent.person.armR.material.color.setHex(agent.baseColor);
      // Cabeça: white = textura aparece com cores originais
      agent.person.headMaterials.forEach((m) => m.color.setHex(0xffffff));
      agent.badge.style.opacity = '1';
      agent.badge.style.transform = 'scale(1.15)';
    }
  }

  // ─── Beams ────────────────────────────────────────────────────────────────

  const activeBeams = [];

  // Origem dos beams = posição da lâmpada do supervisor (x=+9).
  // Se mover o supervisor no futuro, atualizar esta constante também.
  const SUPERVISOR_BEAM_ORIGIN = new THREE.Vector3(9, 1.6, 0);

  function makeBeam(target, tool, platformColor) {
    const start = SUPERVISOR_BEAM_ORIGIN;
    const end = new THREE.Vector3(target.pos.x, target.pos.y || 1.2, target.pos.z);
    const points = [];
    for (let i = 0; i <= 25; i++) {
      const u = i / 25;
      const x = start.x + (end.x - start.x) * u;
      const z = start.z + (end.z - start.z) * u;
      const yBase = start.y + (end.y - start.y) * u;
      const y = yBase + Math.sin(u * Math.PI) * 1.5; // arco acima da reta
      points.push(new THREE.Vector3(x, y, z));
    }
    // Beam ciano por padrão (cyberpunk), cor da plataforma se houver
    const beamColor = platformColor != null ? platformColor : 0x00ddff;
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: beamColor, transparent: true, opacity: 0.9 });
    const line = new THREE.Line(geo, mat);
    scene.add(line);
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 12, 12),
      new THREE.MeshBasicMaterial({ color: 0xaaeeff })
    );
    scene.add(orb);
    activeBeams.push({ line, mat, points, orb, target, tool, t0: performance.now(), arrived: false });
  }

  // ─── Event handlers (mapeia eventos do backend → reações visuais) ──────────

  function handleEvent(evt) {
    if (!evt || !evt.type) return;
    // Log no console pra debug — você vê cada evento que chega ao vivo
    if (evt.type !== '_backlog') {
      console.log(`[evt] ${evt.type}`, evt.agent || '-', evt.tool || '-');
    }
    switch (evt.type) {
      case 'delegation':       return onDelegation(evt);
      case 'tool_call':        return onToolCall(evt);
      case 'dispatcher_decision': return onDispatcherDecision(evt);
      case 'session_end':      return onSessionEnd(evt);
      case '_backlog':         return onBacklog(evt);
      default: console.debug('evento ignorado:', evt.type);
    }
  }

  function onBacklog(evt) {
    if (!evt.events) return;
    // Backlog NÃO simula eventos como se fossem ao vivo — só extrai estado
    // final pra contadores. Senão, ao abrir o browser após o python main.py
    // ser morto sem session_end, agentes ficam eternamente "working".
    let count = 0;
    let lastSessionEnd = null;
    const seenInHistory = new Set();
    for (const ev of evt.events) {
      count++;
      if (ev.agent) seenInHistory.add(ev.agent);
      if (ev.type === 'session_end') {
        lastSessionEnd = ev;
      }
    }
    if (lastSessionEnd) {
      // Sessão antiga já encerrou — contador volta a 0/14 (nada rodando agora)
      const meta = lastSessionEnd.metadata || {};
      cost = meta.cost_usd || 0;
      $cost.textContent = cost.toFixed(4);
      $phase.textContent = `última sessão · $${cost.toFixed(4)} · ${meta.turns || 0} turns`;
      agentsSeenThisSession.clear(); // zera — sessão acabou
    } else {
      // Não houve session_end → ainda mostra histórico de agentes vistos
      // (caso o python main.py tenha sido morto sem flush)
      seenInHistory.forEach((n) => agentsSeenThisSession.add(n));
      $phase.textContent = 'aguardando primeira query';
    }
    updateActiveCount();
    logTask(`<span style="opacity:0.6;">[backlog: ${count} eventos antigos carregados — nenhum agente ativo no momento]</span>`);
    console.log(`[backlog] ${count} eventos carregados em modo silencioso (sem ativar working)`);
  }

  function onDelegation(evt) {
    const a = agents.get(evt.agent);
    if (!a) return;
    if (a.asleep) setAsleep(a, false);
    makeBeam(a, null, null);
    agentsSeenThisSession.add(evt.agent);
    updateActiveCount();
    $phase.textContent = `delegando → ${evt.agent}`;
    logTask(`<span class="agent">${evt.agent}</span><span class="sep">acionado</span>`);

    // Troca de trabalhador: para o supervisor + agente anterior
    supervisorActive = false;
    if (currentWorker && currentWorker !== 'supervisor' && currentWorker !== evt.agent) {
      const prev = agents.get(currentWorker);
      if (prev) prev.working = false;
    }
    currentWorker = evt.agent;
    a.working = true;
    lastEventAt = performance.now();
  }

  function onToolCall(evt) {
    lastEventAt = performance.now();
    turns++;
    $turns.textContent = turns;

    // O audit.jsonl raramente preenche agent_name nas tools dentro de um
    // sub-agente, então atribuímos ao currentWorker quando ele é um agente.
    let targetAgent = null;
    let agentLabel = 'supervisor';
    if (evt.agent) {
      targetAgent = agents.get(evt.agent);
      agentLabel = evt.agent;
    } else if (currentWorker && currentWorker !== 'supervisor') {
      targetAgent = agents.get(currentWorker);
      agentLabel = currentWorker;
    }

    if (targetAgent) {
      if (targetAgent.asleep) setAsleep(targetAgent, false);
      const platColor = PLATFORM_COLORS[evt.platform];
      targetAgent.currentPlatformColor = platColor != null ? platColor : targetAgent.baseColor;
      targetAgent.working = true; // mantém working (sem decay)
      supervisorActive = false;
    } else {
      // É o Supervisor executando direto (Bash/Read/Write/Todowrite antes de delegar)
      pulseSupervisor();
    }

    const platBadge = evt.platform ? ` <span style="opacity:0.6;">[${evt.platform}]</span>` : '';
    const toolShort = shortenTool(evt.tool);
    agentsSeenThisSession.add(agentLabel);
    updateActiveCount();
    $phase.textContent = `${agentLabel} → ${toolShort}`;
    logTask(`<span class="agent">${agentLabel}</span><span class="sep">→</span><span class="tool">${evt.tool}</span>${platBadge}`);
  }

  function pulseSupervisor() {
    supervisorActive = true; // pulse contínuo, sem decay
    if (currentWorker && currentWorker !== 'supervisor') {
      const prev = agents.get(currentWorker);
      if (prev) prev.working = false;
    }
    currentWorker = 'supervisor';
  }

  function onDispatcherDecision(evt) {
    const meta = evt.metadata || {};
    const selected = new Set(meta.selected || []);
    agents.forEach((a) => setAsleep(a, !selected.has(a.name)));
    $active.textContent = `${selected.size}/${agents.size}`;
    const conf = Math.round((meta.confidence || 0) * 100);
    $dispMsg.textContent = `${selected.size}/${agents.size} agentes · conf ${conf}% · ${meta.reason || ''}`.trim();
    $disp.classList.add('visible');
    setTimeout(() => $disp.classList.remove('visible'), 5000);
    $phase.textContent = 'dispatcher selecionou subset';
    logTask(`<span style="color:#5dcaa5;">🎯 dispatcher:</span> ${
      meta.selected.map((n) => `<span class="agent">${n}</span>`).join(', ')
    }`);
  }

  function onSessionEnd(evt) {
    const meta = evt.metadata || {};
    cost = meta.cost_usd || cost;
    $cost.textContent = cost.toFixed(4);
    $phase.textContent = `sessão encerrada · ${meta.turns || 0} turns · ${(meta.duration_s || 0).toFixed(0)}s`;
    logTask(`<span style="color:#5dcaa5;">✅ sessão encerrada:</span> $${cost.toFixed(4)} · ${meta.turns} turns`);
    resetSceneAfter(3000, 'aguardando próxima query');
  }

  function resetSceneAfter(delayMs, phaseText) {
    supervisorActive = false;
    currentWorker = null;
    // Reset IMEDIATO de tudo: working flag + halos + braços + nameplate +
    // monitor emissive. Sem decay gradual (que ficava com halos acesos
    // depois do session_end por 1-2s e ainda pegava tool_calls atrasados).
    agents.forEach((a) => {
      a.working = false;
      a.pulse = 0;
      a.currentPlatformColor = null;
      a.halo.material.opacity = 0;
      a.person.armL.rotation.x = 0;
      a.person.armR.rotation.x = 0;
      a.person.head.rotation.x = 0;
      a.nameplate.sprite.scale.set(2.0, 0.5, 1);
      a.desk.screenMat.emissiveIntensity = 0.5;
      a.lastBeamAt = 0;
    });
    setTimeout(() => {
      agents.forEach((a) => setAsleep(a, false));
      agentsSeenThisSession.clear();
      $active.textContent = `${agents.size}/${agents.size}`;
      $phase.textContent = phaseText;
    }, delayMs);
  }

  // Detector de inatividade — backend agora emite session_end via sessions.jsonl,
  // mas mantemos fallback pra 60s caso o sistema trave sem flush. Não dispara
  // quando há sessão ativa rodando (60s permite que o supervisor pense por
  // bastante tempo entre tool calls sem ser resetado).
  const IDLE_TIMEOUT_MS = 60000;
  setInterval(() => {
    if (!currentWorker && !supervisorActive) return;
    if (performance.now() - lastEventAt > IDLE_TIMEOUT_MS) {
      logTask(`<span style="color:#94a3b8;">⏸ sessão inativa há ${(IDLE_TIMEOUT_MS / 1000)}s — reset automático</span>`);
      resetSceneAfter(500, 'aguardando próxima query');
    }
  }, 5000);

  // ─── Bootstrap ─────────────────────────────────────────────────────────────

  async function bootstrap() {
    $loadingText.textContent = 'carregando agentes...';
    try {
      const res = await fetch('/agents');
      const data = await res.json();
      const list = data.agents || [];
      // Ordena por tier + nome pra layout estável
      list.sort((a, b) => (a.tier + a.name).localeCompare(b.tier + b.name));

      list.forEach((a, idx) => {
        const agent = createAgent(a.name, a.tier, idx, list.length);
        // Badge
        const b = document.createElement('div');
        b.className = 'badge';
        b.style.background = '#' + agent.baseColor.toString(16).padStart(6, '0');
        b.title = a.name;
        $badgeRow.appendChild(b);
        agent.badge = b;
        agents.set(a.name, agent);
        agentList.push(agent);
      });
      $active.textContent = `${agents.size}/${agents.size}`;
      $loading.classList.add('hidden');
      connectWs();
    } catch (e) {
      $loadingText.textContent = 'erro ao carregar agentes: ' + e.message;
      console.error(e);
    }
  }

  // ─── WebSocket connection com auto-reconnect ──────────────────────────────

  let ws = null;
  let reconnectDelay = 1000;

  function connectWs() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${location.host}/events`;
    setConnStatus('connecting', 'conectando');
    try {
      ws = new WebSocket(url);
    } catch (e) {
      setConnStatus('disconnected', 'erro');
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      reconnectDelay = 1000;
      setConnStatus('connected', 'conectado');
    };
    ws.onmessage = (e) => {
      try {
        handleEvent(JSON.parse(e.data));
      } catch (err) {
        console.error('erro parseando evento:', err);
      }
    };
    ws.onerror = () => {
      setConnStatus('disconnected', 'erro');
    };
    ws.onclose = () => {
      setConnStatus('disconnected', 'desconectado');
      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    setTimeout(() => {
      connectWs();
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    }, reconnectDelay);
  }

  // ─── Câmera — pan + zoom (isométrica fixa) ────────────────────────────────

  let isDragging = false, prevX = 0, prevY = 0, panX = 0, panY = 0, zoom = 1;
  let cameraFollowX = 0, cameraFollowZ = 0; // lerp suave pro agente ativo
  renderer.domElement.addEventListener('mousedown', (e) => {
    isDragging = true; prevX = e.clientX; prevY = e.clientY;
    sceneEl.classList.add('dragging');
  });
  window.addEventListener('mouseup', () => {
    isDragging = false;
    sceneEl.classList.remove('dragging');
  });
  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    panX += (e.clientX - prevX) * 0.02;
    panY += (e.clientY - prevY) * 0.02;
    panX = Math.max(-8, Math.min(8, panX));
    panY = Math.max(-4, Math.min(4, panY));
    prevX = e.clientX; prevY = e.clientY;
  });
  renderer.domElement.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoom = Math.max(0.5, Math.min(2.2, zoom - e.deltaY * 0.001));
  }, { passive: false });

  // ─── Render loop ───────────────────────────────────────────────────────────

  const t0 = performance.now();
  function animate() {
    requestAnimationFrame(animate);
    const tNow = performance.now();
    const elapsed = (tNow - t0) / 1000;

    // Hologramas: rotação contínua + flutuação vertical (cyberpunk vibe)
    _holograms.forEach((h, i) => {
      h.rotation.y = elapsed * 0.7 + i * 0.3;
      h.rotation.x = Math.sin(elapsed * 0.5 + i) * 0.15;
      h.position.y = 0.65 + Math.sin(elapsed * 1.2 + i * 0.8) * 0.05;
    });

    // Câmera — follow sutil do agente ativo (desloca ~0.5 na direção dele)
    aspect = window.innerWidth / window.innerHeight;
    camera.left = -FRUSTUM * aspect / 2 / zoom;
    camera.right = FRUSTUM * aspect / 2 / zoom;
    camera.top = FRUSTUM / 2 / zoom;
    camera.bottom = -FRUSTUM / 2 / zoom;
    camera.updateProjectionMatrix();

    // Calcula follow target (média dos agentes trabalhando)
    let targetFollowX = 0, targetFollowZ = 0, activeCount = 0;
    agents.forEach((a) => {
      if (a.working) {
        targetFollowX += a.pos.x * 0.06;
        targetFollowZ += a.pos.z * 0.06;
        activeCount++;
      }
    });
    if (activeCount > 0) {
      targetFollowX /= activeCount;
      targetFollowZ /= activeCount;
    }
    // Lerp suave (5% por frame ≈ 1.5s pra estabilizar)
    cameraFollowX += (targetFollowX - cameraFollowX) * 0.05;
    cameraFollowZ += (targetFollowZ - cameraFollowZ) * 0.05;

    camera.position.set(14 - panX + cameraFollowX, 14, 14 + panY + cameraFollowZ);
    camera.lookAt(-panX + cameraFollowX, 0, panY + cameraFollowZ);

    // Supervisor — pulse CONTÍNUO enquanto supervisorActive. Sem decay.
    // Oscila em loop: lâmpada flasha, ring expande+contrai, spark sobe e some.
    if (supervisorActive) {
      const t = elapsed * 2.2;
      const p = 0.5 + Math.sin(t) * 0.5; // oscila 0..1 forever
      lampShade.material.emissiveIntensity = 0.4 + p * 4.0;
      lampShade.material.color.setHex(0xfff2cc);
      supPerson.head.position.y = 1.05 + Math.sin(t * 4) * 0.06;
      supRing.material.opacity = 0.4 + p * 0.5;
      const ringScale = 1 + p * 0.5;
      supRing.scale.set(ringScale, ringScale, 1);
      lampSpark.material.opacity = p * 0.85;
      // Spark sobe enquanto p cresce, some no topo, reaparece embaixo
      const sparkPhase = (t * 0.5) % (Math.PI * 2);
      const sparkUp = (sparkPhase / (Math.PI * 2)); // 0..1 loop
      lampSpark.position.y = 1.55 + sparkUp * 1.6;
      lampSpark.material.opacity = (1 - sparkUp) * 0.85;
      const sparkSize = 1 + sparkUp * 2.0;
      lampSpark.scale.set(sparkSize, sparkSize, sparkSize);
      // Aro pulsante expande+some em loop
      const pulsePhase = ((t * 0.7) % (Math.PI * 2)) / (Math.PI * 2);
      supPulseRing.material.opacity = (1 - pulsePhase) * 0.7;
      const pulseScale = 1 + pulsePhase * 1.5;
      supPulseRing.scale.set(pulseScale, pulseScale, 1);
    } else {
      // Idle — pulse contínuo VISÍVEL (sem precisar de sessão ativa)
      // Lâmpada respira entre 0.5 e 1.5, ring escala +/-15% com opacity
      // oscilando 0.4..0.9, e cor cicla entre dourado e ciano (cyberpunk).
      const idleT = elapsed * 1.5;
      const idleP = 0.5 + Math.sin(idleT) * 0.5; // 0..1
      lampShade.material.emissiveIntensity = 0.5 + idleP * 1.0;
      supPerson.head.position.y = 1.05 + Math.sin(elapsed * 1.5) * 0.04;
      const idleScale = 1 + idleP * 0.15;
      supRing.scale.set(idleScale, idleScale, 1);
      supRing.material.opacity = 0.4 + idleP * 0.5;
      // Cor do anel cicla entre dourado e ciano
      const goldHex = new THREE.Color(0xf4c875);
      const cyanHex = new THREE.Color(0x00ddff);
      supRing.material.color.copy(goldHex).lerp(cyanHex, idleP);
      // Spark sutil sobe lentamente em idle também
      lampSpark.material.opacity = idleP * 0.35;
      lampSpark.position.y = 1.55 + idleP * 0.5;
      supPulseRing.material.opacity *= 0.92;
    }
    // Supervisor encara -X (em direção aos agentes) com leve oscilação
    // pra dar vida (olha um pouco pra um lado e outro, +/- 35°)
    supPerson.group.rotation.y = -Math.PI / 2 + Math.sin(elapsed * 0.4) * 0.6;

    // Anel dispatcher fica visível enquanto toast estiver visível
    if ($disp.classList.contains('visible')) {
      dispRing.material.opacity = Math.min(0.85, dispRing.material.opacity + 0.04);
      dispRing.rotation.z += 0.05;
    } else {
      dispRing.material.opacity *= 0.93;
    }

    // Agentes
    agents.forEach((a) => {
      a.currentEmissive += (a.targetEmissive - a.currentEmissive) * 0.08;
      a.desk.screenMat.emissiveIntensity = a.currentEmissive;
      const emissColor = a.asleep
        ? 0x1a1a22
        : (a.currentPlatformColor != null ? a.currentPlatformColor : a.baseColor);
      a.desk.screenMat.emissive.setHex(emissColor);

      if (a.asleep) {
        a.zSprite.material.opacity = 0.4 + Math.sin(elapsed * 2 + a.idlePhase) * 0.2;
        a.zSprite.position.y = 1.85 + Math.sin(elapsed * 2 + a.idlePhase) * 0.15;
      } else {
        a.zSprite.material.opacity *= 0.85;
        // Respiração natural: cabeça sobe/desce + tronco escala vertical 1-2%
        const breath = Math.sin(elapsed * 1.2 + a.idlePhase);
        a.person.head.position.y = 1.05 + breath * 0.02;
        a.person.body.scale.y = 1 + breath * 0.015;
        a.person.body.scale.x = 1 + breath * 0.01;
      }

      if (a.working) {
        // Pulse CONTÍNUO enquanto working — agora MUITO visível:
        //   1. Monitor 3x mais brilhante (emissive até 2.5)
        //   2. Halo verde no chão pulsando
        //   3. Braços animados em loop (typing no teclado)
        //   4. Cabeça inclinada + bob ritmado
        //   5. Nameplate escala oscilando
        //   6. Z sprite some imediatamente
        //   7. Beam recorrente Supervisor → agente a cada 2.5s
        //      (simula comunicação contínua, não só na delegação inicial)
        if (tNow - a.lastBeamAt > BEAM_RECURRENCE_MS) {
          const platColor = a.currentPlatformColor;
          makeBeam(a, null, platColor);
          a.lastBeamAt = tNow;
        }
        const tPulse = elapsed * 3 + a.idlePhase;
        const p = 0.5 + Math.sin(tPulse) * 0.5;
        // 1. Monitor flasha forte
        a.desk.screenMat.emissiveIntensity = 0.5 + p * 2.0;
        // 2. Halo no chão (verde menta) pulsando
        a.halo.material.color.setHex(0x5dcaa5);
        a.halo.material.opacity = 0.4 + p * 0.5;
        // 3. Braços fazendo "typing" — alternam pra frente/trás rapidinho
        a.person.armL.rotation.x = -Math.PI / 8 + Math.sin(tPulse * 8) * 0.4;
        a.person.armR.rotation.x = -Math.PI / 8 + Math.sin(tPulse * 8 + Math.PI) * 0.4;
        // 4. Cabeça inclinada lendo o monitor + bob sutil
        a.person.head.rotation.x = 0.18 + Math.sin(tPulse * 2) * 0.06;
        // 5. Nameplate respira (escala oscila)
        const npScale = 1 + p * 0.12;
        a.nameplate.sprite.scale.set(2.0 * npScale, 0.5 * npScale, 1);
        // 6. Z sprite some quando acorda
        a.zSprite.material.opacity *= 0.85;
      } else {
        a.person.head.rotation.x *= 0.92;
        // Braços voltam à posição neutra
        a.person.armL.rotation.x *= 0.85;
        a.person.armR.rotation.x *= 0.85;
        a.halo.material.opacity *= 0.92;
        // Nameplate volta ao tamanho normal
        a.nameplate.sprite.scale.set(2.0, 0.5, 1);
        if (a.currentPlatformColor != null) a.currentPlatformColor = null;
      }
    });

    // Beams
    for (let i = activeBeams.length - 1; i >= 0; i--) {
      const b = activeBeams[i];
      const age = (tNow - b.t0) / 1000;
      const u = Math.min(1, age / 0.9);
      const idx = Math.floor(u * (b.points.length - 1));
      b.orb.position.copy(b.points[idx]);
      b.mat.opacity = 0.85 * (1 - u * 0.6);
      if (u >= 1 && !b.arrived) {
        b.arrived = true;
        b.target.working = true;
        b.target.pulse = 0;
      }
      if (age > 1.6) {
        scene.remove(b.line);
        scene.remove(b.orb);
        activeBeams.splice(i, 1);
      }
    }

    renderer.render(scene, camera);
  }

  // ─── Resize ────────────────────────────────────────────────────────────────

  window.addEventListener('resize', () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    aspect = window.innerWidth / window.innerHeight;
    camera.left = -FRUSTUM * aspect / 2 / zoom;
    camera.right = FRUSTUM * aspect / 2 / zoom;
    camera.top = FRUSTUM / 2 / zoom;
    camera.bottom = -FRUSTUM / 2 / zoom;
    camera.updateProjectionMatrix();
  });

  // ─── Go ────────────────────────────────────────────────────────────────────

  bootstrap();
  animate();
})();
