/* ============================================================
 * DOMA · Datacenter NOC (V3 theme)
 *
 * Conceito: o salão é um datacenter cyberpunk.
 *  - Cada agente é um SERVIDOR-HUMANÓIDE rackeado.
 *  - Supervisor é o NOC (Network Operations Center) elevado no fundo.
 *  - 2 fileiras de racks face a face com aisle central.
 *  - Cabos de fibra ótica brilhantes correm pelo chão.
 *
 * Eventos mapeados:
 *  - delegation  → link de rede acende do NOC pro rack (linha pulsante)
 *  - tool_call   → pacote de dados luminoso voa do rack pro NOC
 *  - session_end → flash global "DEPLOY COMPLETE"
 * ============================================================ */

(() => {
  "use strict";

  // ─── Declarações antecipadas (hoisting consciente) ────────────
  // allAgents/agentRegistry/etc são usados por funções que rodam ANTES
  // da declaração natural (ex: makeScreenTexture chama drawLoadsScreen
  // que itera em allAgents). Declarar aqui evita ReferenceError.
  const allAgents = [
    { name: 'databricks-engineer',   tier: 'T1', color: 0x2563EB, accent: 0x60A5FA, label: 'SPARK NODE',       row: 'L', slot: 0 },
    { name: 'databricks-ai',         tier: 'T1', color: 0x7C3AED, accent: 0xA78BFA, label: 'VECTOR DB',        row: 'L', slot: 1 },
    { name: 'fabric-engineer',       tier: 'T1', color: 0x16A34A, accent: 0x4ADE80, label: 'LAKEHOUSE',        row: 'L', slot: 2 },
    { name: 'fabric-rti',            tier: 'T2', color: 0x06B6D4, accent: 0x67E8F9, label: 'STREAM',           row: 'L', slot: 3 },
    { name: 'fabric-ontology',       tier: 'T2', color: 0x92400E, accent: 0xFCD34D, label: 'ONTOLOGY',         row: 'L', slot: 4 },
    { name: 'business-analyst',      tier: 'T3', color: 0xFBBF24, accent: 0xFCD34D, label: 'INTAKE',           row: 'L', slot: 5 },
    { name: 'geral',                 tier: 'T0', color: 0x94A3B8, accent: 0xE0F2FE, label: 'HELP DESK',        row: 'L', slot: 6 },
    { name: 'python-expert',         tier: 'T1', color: 0xB91C1C, accent: 0xFCA5A5, label: 'APP SERVER',       row: 'R', slot: 0 },
    { name: 'migration-expert',      tier: 'T1', color: 0xFF6B35, accent: 0xFFAA66, label: 'MIGRATION',        row: 'R', slot: 1 },
    { name: 'dbt-expert',            tier: 'T2', color: 0xA16207, accent: 0xFCD34D, label: 'TRANSFORM',        row: 'R', slot: 2 },
    { name: 'data-quality-steward',  tier: 'T2', color: 0xE5E7EB, accent: 0xFCD34D, label: 'QA / DQ',          row: 'R', slot: 3 },
    { name: 'governance-auditor',    tier: 'T2', color: 0xD4AF37, accent: 0xFFFFFF, label: 'AUDIT',            row: 'R', slot: 4 },
    { name: 'data-contracts-engineer', tier: 'T2', color: 0x78350F, accent: 0xE8D5A8, label: 'CONTRACTS',      row: 'R', slot: 5 },
    { name: 'data-mesh-architect',   tier: 'T2', color: 0xFF1493, accent: 0xF9A8D4, label: 'MESH ROUTER',      row: 'R', slot: 6 },
  ];
  const agentRegistry = {};
  const agentRackByName = {};
  const recentEvents = [];
  const costHistory = [];
  const sessionStats = { cost: 0, turns: 0, events: 0 };

  // ─── Setup Three.js ───────────────────────────────────────────
  const sceneEl = document.getElementById('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a1428);
  scene.fog = new THREE.FogExp2(0x0a1428, 0.028);

  const camera = new THREE.PerspectiveCamera(
    52, window.innerWidth / window.innerHeight, 0.1, 100
  );
  // Câmera isométrica ao longo do aisle, olhando pro NOC ao fundo
  camera.position.set(0, 6.5, 9);
  camera.lookAt(0, 1.4, -3);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  sceneEl.appendChild(renderer.domElement);

  // ─── OrbitControls — drag/zoom/orbit livre do mouse ───────────
  // Carregado via CDN no index.html. Se falhar, cai pro auto-drift.
  let controls = null;
  let userInteracted = false;
  let lastUserInteractionAt = 0;
  if (typeof THREE.OrbitControls === 'function') {
    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 1.4, -3);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 4;
    controls.maxDistance = 18;
    controls.maxPolarAngle = Math.PI / 2.05; // não passa do chão
    controls.minPolarAngle = Math.PI / 6;    // não chega ao topo (ângulo confortável)
    controls.enablePan = false;              // pan desabilitado (mantém foco na cena)
    controls.rotateSpeed = 0.55;
    controls.zoomSpeed = 0.85;
    controls.addEventListener('start', () => {
      userInteracted = true;
      lastUserInteractionAt = Date.now();
    });
    controls.addEventListener('end', () => {
      lastUserInteractionAt = Date.now();
    });
  } else {
    console.warn('[DC] OrbitControls não carregou — auto-drift apenas.');
  }

  // ─── Iluminação datacenter — bem mais clara que antes ────────
  const ambient = new THREE.AmbientLight(0x3a4868, 1.05);
  scene.add(ambient);
  const hemi = new THREE.HemisphereLight(0x88d8ff, 0x1a2540, 0.75);
  scene.add(hemi);
  // 6 spots brancos no teto (era 4) com mais intensidade
  for (const [sx, sz] of [[-6, 3], [0, 3], [6, 3], [-6, -3], [0, -3], [6, -3]]) {
    const spot = new THREE.SpotLight(0xfff0d0, 1.4, 18, Math.PI / 4.5, 0.4, 1);
    spot.position.set(sx, 7, sz);
    spot.target.position.set(sx, 0, sz);
    scene.add(spot);
    scene.add(spot.target);
  }
  // Spot ciano destacando o NOC ao fundo
  const noсSpot = new THREE.SpotLight(0x00E5FF, 2.2, 22, Math.PI / 4, 0.5, 1);
  noсSpot.position.set(0, 10, -3);
  noсSpot.target.position.set(0, 0, -9);
  scene.add(noсSpot);
  scene.add(noсSpot.target);
  // Luz frontal fria pra preencher sombras pesadas dos racks
  const fillLight = new THREE.DirectionalLight(0x9bb8d4, 0.5);
  fillLight.position.set(0, 5, 12);
  scene.add(fillLight);

  // ─── Piso elevado de datacenter (tiles 60x60cm) ───────────────
  const floorTex = makeFloorTexture();
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(40, 40),
    new THREE.MeshStandardMaterial({
      map: floorTex, roughness: 0.65, metalness: 0.2,
    })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // ─── Paredes laterais (dim metallic, mais claras que antes) ──
  const wallMat = new THREE.MeshStandardMaterial({
    color: 0x1a2438, roughness: 0.8, metalness: 0.45,
  });
  for (const cfg of [
    { x: -10, z:  0, ry:  Math.PI / 2 },
    { x:  10, z:  0, ry: -Math.PI / 2 },
    { x:   0, z:-11, ry: 0 },
    { x:   0, z: 11, ry: Math.PI },
  ]) {
    const wall = new THREE.Mesh(
      new THREE.PlaneGeometry(22, 7),
      wallMat
    );
    wall.position.set(cfg.x, 3.5, cfg.z);
    wall.rotation.y = cfg.ry;
    wall.receiveShadow = true;
    scene.add(wall);
  }
  // Linhas neon horizontais nas paredes laterais (estética cyberpunk)
  const lineMat = new THREE.MeshBasicMaterial({
    color: 0x00E5FF, transparent: true, opacity: 0.55,
  });
  for (const [x, ry] of [[-9.95, Math.PI / 2], [9.95, -Math.PI / 2]]) {
    for (const y of [1.2, 2.8, 4.4]) {
      const line = new THREE.Mesh(
        new THREE.PlaneGeometry(22, 0.04),
        lineMat
      );
      line.position.set(x, y, 0);
      line.rotation.y = ry;
      scene.add(line);
    }
  }

  // ─── Banners institucionais na parede do fundo (atrás do NOC) ──
  // Usa TextureLoader pra carregar PNGs reais (banner DATA AGENTS + Autor).
  // Posicionados ligeiramente à frente da parede (z=-10.85) pra evitar z-fighting.
  const textureLoader = new THREE.TextureLoader();

  // Banner DATA AGENTS — banner horizontal no topo
  // Imagem real: 1824×394 = aspect 4.63:1
  const dataAgentsTex = textureLoader.load('/datacenter/static/assets/banner.png');
  dataAgentsTex.minFilter = THREE.LinearFilter;
  dataAgentsTex.colorSpace = THREE.SRGBColorSpace || THREE.sRGBEncoding;
  const dataAgentsBanner = new THREE.Mesh(
    new THREE.PlaneGeometry(9.0, 1.95),  // 9.0 / 4.63 ≈ 1.95
    new THREE.MeshBasicMaterial({
      map: dataAgentsTex,
      transparent: true,
      side: THREE.DoubleSide,
    })
  );
  dataAgentsBanner.position.set(0, 5.6, -10.85);
  scene.add(dataAgentsBanner);

  // Banner Autor — abaixo do DATA AGENTS, menor
  // Imagem real: 1618×380 = aspect 4.26:1
  const authorTex = textureLoader.load('/datacenter/static/assets/author.png');
  authorTex.minFilter = THREE.LinearFilter;
  authorTex.colorSpace = THREE.SRGBColorSpace || THREE.sRGBEncoding;
  const authorBanner = new THREE.Mesh(
    new THREE.PlaneGeometry(6.0, 1.41),  // 6.0 / 4.26 ≈ 1.41
    new THREE.MeshBasicMaterial({
      map: authorTex,
      transparent: true,
      side: THREE.DoubleSide,
    })
  );
  authorBanner.position.set(0, 3.85, -10.85);
  scene.add(authorBanner);

  // Spot dedicado iluminando os banners (sutil, mantém leitura)
  const bannerSpot = new THREE.SpotLight(0xffffff, 0.8, 14, Math.PI / 4, 0.6, 1);
  bannerSpot.position.set(0, 8, -7);
  bannerSpot.target.position.set(0, 4.5, -10.85);
  scene.add(bannerSpot);
  scene.add(bannerSpot.target);

  // ─── NOC (Network Operations Center) ao fundo ─────────────────
  const nocGroup = new THREE.Group();
  // Pedestal de aço escovado
  const pedestal = new THREE.Mesh(
    new THREE.BoxGeometry(5.4, 0.4, 2.0),
    new THREE.MeshStandardMaterial({
      color: 0x1f2937, metalness: 0.7, roughness: 0.3,
    })
  );
  pedestal.position.y = 0.2;
  pedestal.castShadow = true;
  pedestal.receiveShadow = true;
  nocGroup.add(pedestal);
  // 3 telas curvas com conteúdos DIFERENTES (cada uma um tipo de telemetria)
  const nocScreens = [
    { tex: makeScreenTexture('loads'), kind: 'loads' },
    { tex: makeScreenTexture('network'), kind: 'network' },
    { tex: makeScreenTexture('events'), kind: 'events' },
  ];
  for (let i = 0; i < 3; i++) {
    const dx = (i - 1) * 1.6;
    const screen = new THREE.Mesh(
      new THREE.PlaneGeometry(1.5, 0.9),
      new THREE.MeshStandardMaterial({
        map: nocScreens[i].tex, emissiveMap: nocScreens[i].tex,
        emissive: 0xffffff, emissiveIntensity: 0.9,
        transparent: true, opacity: 0.97,
      })
    );
    screen.position.set(dx, 1.6, 0);
    screen.rotation.y = -dx * 0.18;
    nocGroup.add(screen);
    // Frame metálico em volta
    const frame = new THREE.Mesh(
      new THREE.BoxGeometry(1.6, 1.0, 0.05),
      new THREE.MeshStandardMaterial({
        color: 0x1f2937, metalness: 0.8, roughness: 0.3,
      })
    );
    frame.position.set(dx, 1.6, -0.03);
    frame.rotation.y = -dx * 0.18;
    nocGroup.add(frame);
  }
  // "Supervisor figure" minimalista — uma silhueta humana com headphones e tela
  const supBody = new THREE.Mesh(
    new THREE.BoxGeometry(0.5, 0.6, 0.4),
    new THREE.MeshStandardMaterial({
      color: 0x14224F, metalness: 0.4, roughness: 0.6,
      emissive: 0x00E5FF, emissiveIntensity: 0.25,
    })
  );
  supBody.position.y = 0.75;
  supBody.castShadow = true;
  nocGroup.add(supBody);
  const supHead = new THREE.Mesh(
    new THREE.BoxGeometry(0.36, 0.36, 0.36),
    new THREE.MeshStandardMaterial({ color: 0xF5D5B8, roughness: 0.7 })
  );
  supHead.position.y = 1.22;
  supHead.castShadow = true;
  nocGroup.add(supHead);
  // Visor "cyber" sobre os olhos (faixa horizontal emissiva)
  const visor = new THREE.Mesh(
    new THREE.BoxGeometry(0.34, 0.08, 0.02),
    new THREE.MeshStandardMaterial({
      color: 0x00E5FF, emissive: 0x00E5FF, emissiveIntensity: 1.5,
    })
  );
  visor.position.set(0, 1.24, 0.19);
  nocGroup.add(visor);
  // Aura no chão sob o supervisor
  const supAura = new THREE.Mesh(
    new THREE.RingGeometry(0.7, 1.0, 32),
    new THREE.MeshBasicMaterial({
      color: 0x00E5FF, transparent: true, opacity: 0.35,
      side: THREE.DoubleSide,
    })
  );
  supAura.rotation.x = -Math.PI / 2;
  supAura.position.y = 0.41;
  nocGroup.add(supAura);

  nocGroup.position.set(0, 0, -9);
  scene.add(nocGroup);

  // ─── Cabos de fibra ótica correndo no aisle central ───────────
  const CABLE_COLORS = [0x00E5FF, 0xFF1493, 0x00FF88, 0xFFB300, 0xA78BFA];
  const cableXOffsets = [];
  for (let i = 0; i < 5; i++) {
    const c = new THREE.Mesh(
      new THREE.BoxGeometry(0.04, 0.01, 18),
      new THREE.MeshStandardMaterial({
        color: CABLE_COLORS[i],
        emissive: CABLE_COLORS[i],
        emissiveIntensity: 0.7,
      })
    );
    const cableX = -0.4 + i * 0.2;
    c.position.set(cableX, 0.03, 0);
    scene.add(c);
    cableXOffsets.push(cableX);
  }

  // ─── Particle flow: pacotes de dados viajando constantemente ──
  // Cada cabo tem 3 partículas em loop infinito, espaçadas no tempo.
  const cableParticles = [];
  for (let cableIdx = 0; cableIdx < 5; cableIdx++) {
    for (let p = 0; p < 3; p++) {
      const particle = new THREE.Mesh(
        new THREE.SphereGeometry(0.07, 8, 8),
        new THREE.MeshStandardMaterial({
          color: CABLE_COLORS[cableIdx],
          emissive: CABLE_COLORS[cableIdx],
          emissiveIntensity: 2.0,
          transparent: true, opacity: 0.95,
        })
      );
      particle.position.set(cableXOffsets[cableIdx], 0.08, 0);
      scene.add(particle);
      cableParticles.push({
        mesh: particle,
        cableIdx,
        x: cableXOffsets[cableIdx],
        // tOffset distribui as 3 partículas ao longo do cabo
        tOffset: (p / 3) + (Math.random() * 0.1),
        // Direções alternadas: cabos pares vão NOC→entrada, ímpares vice-versa
        direction: cableIdx % 2 === 0 ? -1 : 1,
        speed: 2.5 + Math.random() * 0.8, // unidades/seg
      });
    }
  }

  // ─── 14 Racks de servidor (agentes) ───────────────────────────
  // (allAgents/agentRegistry/agentRackByName/sessionStats declarados no topo)

  function updateStatsHUD() {
    document.getElementById('stat-mana').textContent = `$${sessionStats.cost.toFixed(3)}`;
    document.getElementById('stat-hp').textContent = sessionStats.turns;
    document.getElementById('stat-gold').textContent = sessionStats.events;
    document.getElementById('fill-mana').style.width = Math.min(100, sessionStats.cost * 200) + '%';
    document.getElementById('fill-hp').style.width = Math.min(100, (sessionStats.turns / 50) * 100) + '%';
    document.getElementById('fill-gold').style.width = Math.min(100, (sessionStats.events / 100) * 100) + '%';
    document.getElementById('event-count').textContent = sessionStats.events;
  }

  // Posiciona cada rack — fileiras em "V" abrindo em direção à câmera
  // + tilt em direção à câmera pra mostrar mais a frente do servidor
  const RACK_TILT = Math.PI / 10;  // ~18° (era π/14 = 13°, agora mais visível)
  allAgents.forEach((ag) => {
    const rack = makeServerRack(ag);
    const sign = ag.row === 'L' ? -1 : 1;
    // xRow varia com slot — slot 0 = ±3.0 (era 2.7, dá mais respiro perto do NOC)
    // slot 6 = ±5.1 (mantido)
    const xRow = sign * (3.0 + ag.slot * 0.35);
    const zSlot = -6.5 + ag.slot * 1.9;
    rack.position.set(xRow, 0, zSlot);
    rack.rotation.y = ag.row === 'L'
      ? Math.PI / 2 - RACK_TILT
      : -Math.PI / 2 + RACK_TILT;
    scene.add(rack);

    // ─── Branch cable + connection dot em COORDS GLOBAIS ───────────
    // Antes da DC21, esses meshes eram filhos do grupo do rack — herdavam
    // a rotação ±π/2 ± tilt e desalinhavam dos cabos do aisle. Agora cada
    // rack escolhe um dos 5 cabos centrais (slot % 5) e o branch vai do
    // lateral do rack até EXATAMENTE esse cabo, perpendicular ao aisle.
    rack.updateMatrixWorld(true);
    // Ponto onde o branch sai do rack — meio da face que olha pro aisle,
    // ligeiramente acima do chão.
    const sideLocal = new THREE.Vector3(0, 0.45, 0.55);
    const sideWorld = sideLocal.clone().applyMatrix4(rack.matrixWorld);
    // Distribui os 14 racks pelos 5 cabos centrais. Slots 0-4 = cabos 0-4,
    // slot 5 reusa cabo 0, slot 6 reusa cabo 1. Empilha sem cruzar.
    const targetCableX = cableXOffsets[ag.slot % cableXOffsets.length];
    const cableHook = new THREE.Vector3(targetCableX, 0.05, sideWorld.z);

    const branchLen = Math.max(0.01, sideWorld.distanceTo(cableHook));
    const branchMid = sideWorld.clone().lerp(cableHook, 0.5);
    const branch = new THREE.Mesh(
      new THREE.BoxGeometry(0.06, 0.04, branchLen),
      new THREE.MeshStandardMaterial({
        color: ag.color, emissive: ag.color, emissiveIntensity: 1.5,
        transparent: true, opacity: 0,
      })
    );
    branch.position.copy(branchMid);
    branch.lookAt(cableHook);  // alinha +Z do box com o vetor side→hook
    scene.add(branch);

    const branchDot = new THREE.Mesh(
      new THREE.SphereGeometry(0.09, 12, 12),
      new THREE.MeshStandardMaterial({
        color: 0xFFFFFF, emissive: ag.color, emissiveIntensity: 2.0,
        transparent: true, opacity: 0,
      })
    );
    branchDot.position.copy(cableHook);
    scene.add(branchDot);

    rack.userData.branch = branch;
    rack.userData.branchDot = branchDot;

    agentRegistry[ag.name] = rack.userData;
    agentRackByName[ag.name] = rack;
  });

  // ─── Construção de um rack ────────────────────────────────────
  function makeServerRack(ag) {
    const g = new THREE.Group();

    // Estrutura do rack (caixa de aço escovado preta)
    const cabinet = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 2.0, 1.0),
      new THREE.MeshStandardMaterial({
        color: 0x1f2937, metalness: 0.7, roughness: 0.4,
      })
    );
    cabinet.position.y = 1.0;
    cabinet.castShadow = true;
    cabinet.receiveShadow = true;
    g.add(cabinet);
    // Painel frontal com gradiente preto-azulado
    const front = new THREE.Mesh(
      new THREE.PlaneGeometry(0.86, 1.92),
      new THREE.MeshStandardMaterial({
        color: 0x0a0e1a, roughness: 0.5, metalness: 0.5,
      })
    );
    front.position.set(0, 1.0, 0.51);
    g.add(front);

    // Slots horizontais de 1U/2U (linhas finas decorativas no painel frontal)
    for (const slotY of [0.15, 0.30, 1.30, 1.65, 1.78]) {
      const slot = new THREE.Mesh(
        new THREE.BoxGeometry(0.78, 0.02, 0.01),
        new THREE.MeshStandardMaterial({
          color: 0x374151, metalness: 0.7, roughness: 0.5,
        })
      );
      slot.position.set(0, slotY, 0.525);
      g.add(slot);
    }

    // Porta de ventilação no topo (3 fileiras de furos pequenos)
    const ventMat = new THREE.MeshStandardMaterial({
      color: 0x050816, roughness: 0.95,
    });
    for (let row = 0; row < 3; row++) {
      for (let col = 0; col < 6; col++) {
        const hole = new THREE.Mesh(
          new THREE.CylinderGeometry(0.025, 0.025, 0.04, 6),
          ventMat
        );
        hole.rotation.x = Math.PI / 2;
        hole.position.set(-0.3 + col * 0.12, 1.95, 0.52 - row * 0.04);
        g.add(hole);
      }
    }

    // Parafusos nos 4 cantos do painel frontal (esferas pequenas metálicas)
    for (const [sx, sy] of [[-0.38, 0.07], [0.38, 0.07], [-0.38, 1.93], [0.38, 1.93]]) {
      const screw = new THREE.Mesh(
        new THREE.SphereGeometry(0.025, 6, 6),
        new THREE.MeshStandardMaterial({
          color: 0x6b7280, metalness: 0.9, roughness: 0.3,
        })
      );
      screw.position.set(sx, sy, 0.53);
      g.add(screw);
    }

    // 4 "slot" indicators (LEDs verticais empilhados no painel frontal)
    const leds = [];
    for (let i = 0; i < 4; i++) {
      const led = new THREE.Mesh(
        new THREE.BoxGeometry(0.6, 0.08, 0.02),
        new THREE.MeshStandardMaterial({
          color: ag.color, emissive: ag.color, emissiveIntensity: 0.6,
          transparent: true, opacity: 0.95,
        })
      );
      led.position.set(0, 0.5 + i * 0.18, 0.53);
      g.add(led);
      leds.push(led);
    }

    // Mini display LCD verde abaixo dos LEDs (canvas dinâmico)
    const lcdTex = makeLcdTexture(ag);
    const lcd = new THREE.Mesh(
      new THREE.PlaneGeometry(0.7, 0.32),
      new THREE.MeshStandardMaterial({
        map: lcdTex, emissiveMap: lcdTex,
        emissive: 0xffffff, emissiveIntensity: 0.65,
        transparent: true, opacity: 0.98,
      })
    );
    lcd.position.set(0, 1.55, 0.525);
    g.add(lcd);

    // "Status orb" — esfera grande emissiva no topo do rack (cabeça simbólica)
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.18, 14, 14),
      new THREE.MeshStandardMaterial({
        color: ag.color, emissive: ag.accent, emissiveIntensity: 0.9,
      })
    );
    orb.position.y = 2.15;
    orb.castShadow = true;
    g.add(orb);

    // Label canvas (nome do agente + label de função) — sprite acima do rack
    const labelSprite = makeRackLabel(ag.name, ag.label, ag.color);
    labelSprite.position.y = 2.55;
    g.add(labelSprite);

    // Halo no chão sob o rack
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.55, 0.78, 32),
      new THREE.MeshBasicMaterial({
        color: ag.color, transparent: true, opacity: 0,
        side: THREE.DoubleSide,
      })
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.02;
    g.add(halo);

    // Branch cable e branchDot NÃO são mais filhos do grupo do rack — eles
    // são criados depois (em coords globais) no loop principal, alinhados
    // perpendicularmente aos 5 cabos centrais do aisle. Ver DC21.

    // Vapor — 3 puffs subindo do topo do rack (ar quente da refrigeração)
    // Sutil: opacity baixo + cor azulada+branco
    const vaporPuffs = [];
    for (let i = 0; i < 3; i++) {
      const puff = new THREE.Mesh(
        new THREE.SphereGeometry(0.08 + i * 0.02, 8, 8),
        new THREE.MeshStandardMaterial({
          color: 0xb3e5fc, transparent: true, opacity: 0,
          emissive: 0xb3e5fc, emissiveIntensity: 0.1,
        })
      );
      // x ligeiramente aleatório pra não ficar enfileirado
      const offsetX = (Math.random() - 0.5) * 0.25;
      puff.position.set(offsetX, 2.0, 0);
      puff.userData = {
        baseX: offsetX,
        tOffset: Math.random() * 3,  // fase inicial aleatória
      };
      g.add(puff);
      vaporPuffs.push(puff);
    }

    g.userData = {
      cabinet, front, orb, leds, halo, lcd, lcdTex, vaporPuffs,
      labelSprite,
      // branch e branchDot setados depois (são meshes em coords GLOBAIS,
      // criados após scene.add(rack) — ver loop principal logo abaixo).
      branch: null,
      branchDot: null,
      working: false,
      baseColor: ag.color,
      accent: ag.accent,
      idlePhase: Math.random() * Math.PI * 2,
      heat: 0,
      lastToolCallAt: 0,
    };
    return g;
  }

  // Mini display LCD do rack — texto verde monocromático estilo terminal antigo
  function makeLcdTexture(ag) {
    const c = document.createElement('canvas');
    c.width = 256; c.height = 116;
    const ctx = c.getContext('2d');
    // Fundo preto profundo
    ctx.fillStyle = '#020a05';
    ctx.fillRect(0, 0, c.width, c.height);
    // Scanlines suaves
    ctx.fillStyle = 'rgba(0, 255, 136, 0.04)';
    for (let y = 0; y < c.height; y += 3) {
      ctx.fillRect(0, y, c.width, 1);
    }
    // Borda fina verde
    ctx.strokeStyle = '#0f5132';
    ctx.lineWidth = 2;
    ctx.strokeRect(2, 2, c.width - 4, c.height - 4);
    // Conteúdo: status + uptime + ms
    ctx.font = '700 20px "JetBrains Mono", monospace';
    ctx.fillStyle = '#00FF88';
    ctx.shadowColor = '#00FF88';
    ctx.shadowBlur = 4;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('● ' + ag.label, 12, 14);
    ctx.shadowBlur = 0;
    ctx.font = '16px "JetBrains Mono", monospace';
    ctx.fillStyle = '#4ade80';
    ctx.fillText('STATUS OK', 12, 50);
    ctx.fillStyle = '#84cc16';
    ctx.fillText('● 12ms · 99.9%', 12, 78);

    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    tex._canvas = c;
    tex._agent = ag;
    return tex;
  }

  // Atualiza um LCD individual (chamado pelo loop quando o agente muda de estado)
  function redrawLcd(lcdTex, ag, working, heatLevel) {
    const c = lcdTex._canvas;
    if (!c) return;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#020a05';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = 'rgba(0, 255, 136, 0.04)';
    for (let y = 0; y < c.height; y += 3) ctx.fillRect(0, y, c.width, 1);

    const lineColor = working ? '#FFB300' : (heatLevel > 0.6 ? '#FF3060' : '#0f5132');
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.strokeRect(2, 2, c.width - 4, c.height - 4);

    ctx.font = '700 20px "JetBrains Mono", monospace';
    const topColor = working ? '#FFB300' : (heatLevel > 0.6 ? '#FF3060' : '#00FF88');
    ctx.fillStyle = topColor;
    ctx.shadowColor = topColor;
    ctx.shadowBlur = 4;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('● ' + lcdTex._agent.label, 12, 14);
    ctx.shadowBlur = 0;

    ctx.font = '16px "JetBrains Mono", monospace';
    if (working) {
      ctx.fillStyle = '#FCD34D';
      ctx.fillText('PROCESSING...', 12, 50);
      ctx.fillStyle = '#FFB300';
      ctx.fillText('● ACTIVE', 12, 78);
    } else if (heatLevel > 0.6) {
      ctx.fillStyle = '#FCA5A5';
      ctx.fillText('HIGH LOAD ⚠', 12, 50);
      ctx.fillStyle = '#FF3060';
      ctx.fillText('● COOLING', 12, 78);
    } else {
      ctx.fillStyle = '#4ade80';
      ctx.fillText('STATUS OK', 12, 50);
      ctx.fillStyle = '#84cc16';
      ctx.fillText('● IDLE · 99.9%', 12, 78);
    }
    lcdTex.needsUpdate = true;
  }

  // Label sprite acima do rack — fundo metálico + texto monospace
  function makeRackLabel(name, label, color) {
    const measureCtx = document.createElement('canvas').getContext('2d');
    measureCtx.font = '700 17px "JetBrains Mono", monospace';
    const nameW = measureCtx.measureText(name).width;
    measureCtx.font = '12px "JetBrains Mono", monospace';
    const labelW = measureCtx.measureText(label).width;
    const totalW = Math.max(140, Math.ceil(Math.max(nameW, labelW) + 40));

    const c = document.createElement('canvas');
    c.width = totalW; c.height = 64;
    const ctx = c.getContext('2d');

    // Fundo metálico semi-transparente
    ctx.fillStyle = 'rgba(14, 20, 36, 0.92)';
    ctx.beginPath();
    ctx.roundRect(0, 12, totalW, 40, 4);
    ctx.fill();
    // Borda neon
    ctx.strokeStyle = '#00E5FF';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(0, 12, totalW, 40, 4);
    ctx.stroke();

    // Status LED esquerda
    ctx.fillStyle = '#' + color.toString(16).padStart(6, '0');
    ctx.shadowColor = '#' + color.toString(16).padStart(6, '0');
    ctx.shadowBlur = 8;
    ctx.beginPath();
    ctx.arc(16, 32, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    // Nome
    ctx.font = '700 17px "JetBrains Mono", monospace';
    ctx.fillStyle = '#E0F2FE';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(name, 30, 28);
    // Label de função
    ctx.font = '12px "JetBrains Mono", monospace';
    ctx.fillStyle = '#00E5FF';
    ctx.fillText('▸ ' + label, 30, 44);

    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    const aspect = totalW / 64;
    sprite.scale.set(0.55 * aspect, 0.55, 1);
    return sprite;
  }

  // ─── Pacotes de dados (spells) e links de rede (beams) ────────
  const activePackets = [];   // tool_call: pacote viaja do rack pro NOC
  const activeBeams = [];     // delegation: linha do NOC pro rack

  function spawnPacket(rack, color, accent) {
    const start = new THREE.Vector3();
    rack.getWorldPosition(start);
    start.y = 1.5;
    const end = new THREE.Vector3(0, 1.6, -9);  // NOC center

    // Esfera de "pacote" voadora
    const packet = new THREE.Mesh(
      new THREE.SphereGeometry(0.12, 10, 10),
      new THREE.MeshStandardMaterial({
        color: accent, emissive: accent, emissiveIntensity: 1.8,
        transparent: true, opacity: 1.0,
      })
    );
    packet.position.copy(start);
    scene.add(packet);

    // Trail luminoso (cilindro inicial)
    const dir = end.clone().sub(start);
    const len = dir.length();
    const tube = new THREE.Mesh(
      new THREE.CylinderGeometry(0.02, 0.02, len, 8),
      new THREE.MeshStandardMaterial({
        color: accent, emissive: accent, emissiveIntensity: 1.0,
        transparent: true, opacity: 0.4,
      })
    );
    tube.position.copy(start).add(dir.clone().multiplyScalar(0.5));
    tube.lookAt(end);
    tube.rotateX(Math.PI / 2);
    scene.add(tube);

    activePackets.push({
      packet, tube, start, end,
      t0: Date.now(), lifetime: 900,
    });
  }

  function spawnBeam(rack, color) {
    const start = new THREE.Vector3(0, 1.6, -9);
    const end = new THREE.Vector3();
    rack.getWorldPosition(end);
    end.y = 1.5;

    const dir = end.clone().sub(start);
    const len = dir.length();
    const tube = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.05, len, 8),
      new THREE.MeshStandardMaterial({
        color: 0xFFB300, emissive: 0xFFB300, emissiveIntensity: 1.6,
        transparent: true, opacity: 0.85,
      })
    );
    tube.position.copy(start).add(dir.clone().multiplyScalar(0.5));
    tube.lookAt(end);
    tube.rotateX(Math.PI / 2);
    scene.add(tube);

    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 10, 10),
      new THREE.MeshStandardMaterial({
        color: 0xFFFFFF, emissive: 0xFFB300, emissiveIntensity: 2.0,
      })
    );
    orb.position.copy(start);
    scene.add(orb);

    activeBeams.push({
      tube, orb, start, end,
      t0: Date.now(), lifetime: 1100,
    });
  }

  // ─── Deploy overlay (Apollo-style "MISSION ACCOMPLISHED") ─────
  let deployOverlayTimer = null;
  function showDeployOverlay(metadata) {
    const overlay = document.getElementById('deploy-overlay');
    const stats = document.getElementById('deploy-stats');
    if (!overlay) return;
    const cost = (metadata.cost_usd || 0).toFixed(3);
    const turns = metadata.turns || 0;
    const dur = (metadata.duration_s || 0).toFixed(1);
    stats.innerHTML = `$${cost} · ${turns} turns · ${dur}s`;
    overlay.style.display = 'flex';
    requestAnimationFrame(() => {
      overlay.style.opacity = '1';
    });
    clearTimeout(deployOverlayTimer);
    deployOverlayTimer = setTimeout(() => {
      overlay.style.opacity = '0';
      setTimeout(() => { overlay.style.display = 'none'; }, 600);
    }, 2500);
  }

  // ─── Handler de eventos ───────────────────────────────────────
  function handleSceneEvent(evt) {
    if (!evt || !evt.type) return;
    const isBacklog = !!evt._backlog;
    const ag = evt.agent && agentRegistry[evt.agent];
    const rack = evt.agent && agentRackByName[evt.agent];

    if (evt.type === 'delegation') {
      if (ag && !isBacklog) {
        ag.working = true;
        ag.workingStartedAt = Date.now();
        spawnBeam(rack, ag.baseColor);
      }
    } else if (evt.type === 'tool_call') {
      if (ag && !isBacklog) {
        ag.working = true;
        ag.workingStartedAt = Date.now();
        // Heat aumenta a cada tool_call rápido em sequência
        const now = Date.now();
        const dt = (now - (ag.lastToolCallAt || 0)) / 1000;
        if (dt < 3) {
          // Tool calls em < 3s aumentam mais o heat
          ag.heat = Math.min(1.0, (ag.heat || 0) + 0.25);
        } else {
          ag.heat = Math.min(1.0, (ag.heat || 0) + 0.12);
        }
        ag.lastToolCallAt = now;
        spawnPacket(rack, ag.baseColor, ag.accent);
      }
    } else if (evt.type === 'session_end') {
      Object.values(agentRegistry).forEach((aa) => {
        aa.working = false;
        if (aa.halo) aa.halo.material.opacity = 0;
      });
      // Mostra overlay "DEPLOY COMPLETE"
      if (!isBacklog) showDeployOverlay(evt.metadata || {});
    }

    if (!isBacklog && evt.type === 'session_end' && evt.metadata) {
      sessionStats.cost += (evt.metadata.cost_usd || 0);
      sessionStats.turns += (evt.metadata.turns || 0);
      costHistory.push(sessionStats.cost);
      if (costHistory.length > 120) costHistory.shift();
      updateStatsHUD();
    } else if (!isBacklog) {
      sessionStats.events++;
      updateStatsHUD();
    }
    // Tracking pra "EVENT LOG" tela do NOC
    if (!isBacklog && evt.type) {
      recentEvents.push({ type: evt.type, agent: evt.agent || '', t: Date.now() });
      if (recentEvents.length > 20) recentEvents.shift();
    }
  }

  // ─── Animation loop ───────────────────────────────────────────
  const t0 = Date.now();
  function animate() {
    requestAnimationFrame(animate);
    const elapsed = (Date.now() - t0) / 1000;
    const now = Date.now();

    // Camera drift sutil — só se o usuário NÃO está orbitando
    // Após 5s de inatividade, retoma o drift
    const idleMs = Date.now() - lastUserInteractionAt;
    if (!userInteracted || idleMs > 5000) {
      if (controls) {
        controls.target.set(0, 1.4, -3);
      } else {
        camera.position.x = Math.sin(elapsed * 0.08) * 0.5;
        camera.position.z = 9 + Math.cos(elapsed * 0.06) * 0.3;
        camera.lookAt(0, 1.4, -3);
      }
    }
    if (controls) controls.update();

    // NOC aura pulse
    supAura.material.opacity = 0.3 + Math.sin(elapsed * 1.4) * 0.12;
    supAura.rotation.z += 0.004;
    visor.material.emissiveIntensity = 1.2 + Math.sin(elapsed * 2.4) * 0.4;

    // Particle flow nos cabos — loop contínuo
    // Cabo vai de z=-9 a z=+9 (18 unidades). Partículas viajam em loop.
    for (const p of cableParticles) {
      const cycleTime = 18 / p.speed; // tempo pra atravessar todo o cabo
      const t = ((elapsed + p.tOffset * cycleTime) / cycleTime) % 1;
      // direção: -1 = NOC→entrada (z aumenta), +1 = entrada→NOC (z diminui)
      const z = p.direction < 0 ? -9 + t * 18 : 9 - t * 18;
      p.mesh.position.set(p.x, 0.08, z);
      // Fade nas pontas (smooth in/out)
      let opacity = 1;
      if (t < 0.05) opacity = t / 0.05;
      else if (t > 0.95) opacity = (1 - t) / 0.05;
      p.mesh.material.opacity = opacity * 0.95;
    }

    // Pacotes — voam do rack pro NOC + fade no fim
    for (let i = activePackets.length - 1; i >= 0; i--) {
      const p = activePackets[i];
      const pct = (now - p.t0) / p.lifetime;
      if (pct >= 1) {
        scene.remove(p.packet);
        scene.remove(p.tube);
        activePackets.splice(i, 1);
        continue;
      }
      // Easing cubic-out
      const eased = 1 - Math.pow(1 - pct, 3);
      p.packet.position.lerpVectors(p.start, p.end, eased);
      p.tube.material.opacity = 0.4 * (1 - pct);
      p.packet.material.opacity = 1 - pct * 0.5;
    }

    // Beams — orbe viaja, tube fade
    for (let i = activeBeams.length - 1; i >= 0; i--) {
      const b = activeBeams[i];
      const pct = (now - b.t0) / b.lifetime;
      if (pct >= 1) {
        scene.remove(b.tube);
        scene.remove(b.orb);
        activeBeams.splice(i, 1);
        continue;
      }
      const eased = 1 - Math.pow(1 - pct, 2);
      b.orb.position.lerpVectors(b.start, b.end, eased);
      b.tube.material.opacity = 0.85 * (1 - pct);
      b.orb.material.opacity = 1 - pct * 0.6;
    }

    // Animação dos racks
    Object.values(agentRegistry).forEach((ag) => {
      const tPulse = elapsed * 3 + ag.idlePhase;

      // Heat decay — diminui ~0.06/segundo se não houver tool_call recente
      const now = Date.now();
      const sinceLast = (now - (ag.lastToolCallAt || 0)) / 1000;
      if (sinceLast > 1.5 && ag.heat > 0) {
        ag.heat = Math.max(0, ag.heat - 0.001); // decay por frame (~0.06/s a 60fps)
      }

      // Cor do orb: interpola entre baseColor → vermelho-quente conforme heat
      const heatColor = new THREE.Color(0xFF3060);
      const baseColor = new THREE.Color(ag.baseColor);
      const orbColor = baseColor.clone().lerp(heatColor, ag.heat);
      ag.orb.material.color.copy(orbColor);
      ag.orb.material.emissive.copy(orbColor);

      if (ag.working) {
        const p = 0.5 + Math.sin(tPulse * 2) * 0.5;
        // Orb pulsa forte
        ag.orb.material.emissiveIntensity = 1.2 + p * 1.5 + ag.heat * 0.8;
        ag.orb.scale.setScalar(1.0 + p * 0.15 + ag.heat * 0.2);
        ag.leds.forEach((led, i) => {
          const ledPulse = 0.5 + Math.sin(tPulse * 6 + i * 1.3) * 0.5;
          led.material.emissiveIntensity = 0.6 + ledPulse * 1.4;
          led.material.opacity = 0.7 + ledPulse * 0.3;
        });
        ag.halo.material.opacity = 0.4 + p * 0.4;
        ag.halo.rotation.z += 0.025;
        // Branch cable acende com pulse — fibra ligando aisle ao rack
        if (ag.branch) {
          const target = 0.7 + p * 0.3;
          ag.branch.material.opacity = ag.branch.material.opacity * 0.85 + target * 0.15;
          ag.branch.material.emissiveIntensity = 1.0 + p * 1.5;
        }
        if (ag.branchDot) {
          ag.branchDot.material.opacity = ag.branchDot.material.opacity * 0.85 + (0.85 + p * 0.15) * 0.15;
          ag.branchDot.material.emissiveIntensity = 1.5 + p * 1.5;
          ag.branchDot.scale.setScalar(1.0 + p * 0.4);
        }
      } else {
        const idle = 0.5 + Math.sin(elapsed * 1.2 + ag.idlePhase) * 0.5;
        ag.orb.material.emissiveIntensity = 0.5 + idle * 0.4 + ag.heat * 0.5;
        ag.orb.scale.setScalar(1.0 + ag.heat * 0.12);
        ag.leds.forEach((led, i) => {
          const ledIdle = 0.5 + Math.sin(elapsed * 1.5 + ag.idlePhase + i * 0.5) * 0.5;
          led.material.emissiveIntensity = 0.4 + ledIdle * 0.2;
          led.material.opacity = 0.7;
        });
        ag.halo.material.opacity *= 0.92;
        // Branch cable apaga
        if (ag.branch) {
          ag.branch.material.opacity *= 0.92;
          ag.branch.material.emissiveIntensity = Math.max(0, ag.branch.material.emissiveIntensity * 0.92);
        }
        if (ag.branchDot) {
          ag.branchDot.material.opacity *= 0.92;
          ag.branchDot.material.emissiveIntensity = Math.max(0, ag.branchDot.material.emissiveIntensity * 0.92);
          ag.branchDot.scale.setScalar(1.0);
        }
      }

      // Atualiza LCD periodicamente (a cada ~30 frames pra economizar CPU)
      if (frameCount % 30 === ((ag.idlePhase * 30) | 0) % 30) {
        if (ag.lcdTex && ag.lcdTex._agent) {
          redrawLcd(ag.lcdTex, ag.lcdTex._agent, ag.working, ag.heat);
        }
      }

      // Vapor — puffs sobem lentamente do topo do rack
      // Heat aumenta a velocidade e a opacidade do vapor (mais carga = mais ar quente)
      if (ag.vaporPuffs) {
        ag.vaporPuffs.forEach((puff, idx) => {
          const speed = 0.35 + ag.heat * 0.8;  // mais quente = sobe mais rápido
          const t = ((elapsed + puff.userData.tOffset + idx * 0.7) * speed) % 2.5;
          // Range Y: 2.0 → 4.0 (2m de subida ao longo do ciclo)
          puff.position.y = 2.0 + t * 0.8;
          // Drift lateral sutil
          puff.position.x = puff.userData.baseX + Math.sin(elapsed * 1.2 + idx) * 0.04;
          // Fade in nos primeiros 20%, fade out nos últimos 40%
          const lifePct = t / 2.5;
          let opacity = 0;
          if (lifePct < 0.2) opacity = lifePct / 0.2 * 0.25;
          else if (lifePct < 0.6) opacity = 0.25;
          else opacity = (1 - lifePct) / 0.4 * 0.25;
          // Heat aumenta opacity (mais visível quando rack tá com carga)
          opacity *= (0.6 + ag.heat * 0.8);
          puff.material.opacity = opacity;
          // Cresce levemente ao subir
          puff.scale.setScalar(1.0 + lifePct * 0.5);
        });
      }
    });

    // NOC screens — atualizam canvas dinamicamente a cada 30 frames pra economizar CPU
    if (frameCount % 30 === 0) {
      for (const s of nocScreens) redrawNocScreen(s.tex, elapsed, sessionStats);
    }
    frameCount++;

    renderer.render(scene, camera);
  }
  let frameCount = 0;

  // Resize
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // ─── WebSocket client (mesmo broker dos outros temas) ─────────
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProto}//${window.location.host}/events`;
  const logEntries = document.getElementById('log-entries');
  const connDot = document.getElementById('conn-dot');
  const connText = document.getElementById('conn-text');

  function setConn(state, text) {
    connDot.className = `dot ${state}`;
    connText.textContent = text;
  }

  function addLogEntry(evt) {
    const entry = document.createElement('div');
    entry.className = 'entry';
    const ts = new Date().toLocaleTimeString('pt-BR', { hour12: false });
    const typeIcon = {
      delegation: '⇨',
      tool_call: '⚡',
      dispatcher_decision: '◈',
      session_end: '✓',
    }[evt.type] || '∙';
    entry.innerHTML = `
      <span class="type">${typeIcon} ${evt.type}</span>
      <span class="ts">${ts}</span>
      ${evt.agent ? `<div><span class="agent">${evt.agent}</span></div>` : ''}
      ${evt.tool ? `<div class="tool">${evt.tool}</div>` : ''}
    `;
    logEntries.insertBefore(entry, logEntries.firstChild);
    // Limita a 5 entradas mais recentes (HUD enxuto)
    while (logEntries.children.length > 5) {
      logEntries.removeChild(logEntries.lastChild);
    }
  }

  function connectWS() {
    setConn('connecting', 'Establishing link...');
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => {
      setConn('connected', 'Link active ✓');
      console.log('[DC] WebSocket connected:', wsUrl);
    };
    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        addLogEntry(evt);
        handleSceneEvent(evt);
      } catch (err) {
        console.warn('[DC] parse error:', err);
      }
    };
    ws.onclose = () => {
      setConn('disconnected', 'Link severed — reconnecting...');
      setTimeout(connectWS, 2500);
    };
    ws.onerror = (err) => console.error('[DC] ws error:', err);
  }

  // ─── Texturas procedurais ─────────────────────────────────────
  function makeFloorTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const ctx = c.getContext('2d');
    // Base mais clara que antes (era #080c14)
    ctx.fillStyle = '#14202e';
    ctx.fillRect(0, 0, 256, 256);
    // Tiles 60x60cm — desenha grade mais visível
    const tileSize = 64;
    ctx.strokeStyle = '#2a3a52';
    ctx.lineWidth = 1.5;
    for (let i = 0; i <= 256; i += tileSize) {
      ctx.beginPath();
      ctx.moveTo(i, 0); ctx.lineTo(i, 256);
      ctx.moveTo(0, i); ctx.lineTo(256, i);
      ctx.stroke();
    }
    // Vents nos cruzamentos
    ctx.fillStyle = 'rgba(0, 229, 255, 0.18)';
    for (let x = tileSize; x < 256; x += tileSize) {
      for (let y = tileSize; y < 256; y += tileSize) {
        ctx.beginPath();
        ctx.arc(x, y, 3.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    const tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(8, 8);
    return tex;
  }

  function makeScreenTexture(kind) {
    const c = document.createElement('canvas');
    c.width = 512; c.height = 320;
    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    tex._canvas = c;
    tex._kind = kind;
    redrawNocScreen(tex, 0, { cost: 0, turns: 0, events: 0 });
    return tex;
  }

  // (recentEvents e costHistory declarados no topo)

  function formatUptime(seconds) {
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function drawUptimeBadge(ctx, c, elapsed) {
    // Badge no canto superior direito de cada tela: "UPTIME HH:MM:SS"
    const uptime = formatUptime(elapsed);
    ctx.font = '11px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    // Background do badge
    const text = `▸ UP ${uptime}`;
    const w = ctx.measureText(text).width + 14;
    ctx.fillStyle = 'rgba(0,255,136,0.12)';
    ctx.fillRect(c.width - w - 8, 6, w, 18);
    ctx.strokeStyle = '#00FF88';
    ctx.lineWidth = 1;
    ctx.strokeRect(c.width - w - 8, 6, w, 18);
    // Texto
    ctx.fillStyle = '#00FF88';
    ctx.shadowColor = '#00FF88';
    ctx.shadowBlur = 3;
    ctx.fillText(text, c.width - 14, 9);
    ctx.shadowBlur = 0;
    ctx.textAlign = 'left';  // reset
  }

  function redrawNocScreen(tex, elapsed, stats) {
    const c = tex._canvas;
    if (!c) return;
    const ctx = c.getContext('2d');
    // Limpa
    ctx.fillStyle = '#04060d';
    ctx.fillRect(0, 0, c.width, c.height);
    // Grid base
    ctx.strokeStyle = 'rgba(0, 229, 255, 0.1)';
    ctx.lineWidth = 1;
    for (let i = 0; i < c.width; i += 40) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, c.height); ctx.stroke();
    }
    for (let i = 0; i < c.height; i += 40) {
      ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(c.width, i); ctx.stroke();
    }

    // Renderiza por kind
    if (tex._kind === 'loads') {
      drawLoadsScreen(ctx, c, elapsed);
    } else if (tex._kind === 'network') {
      drawNetworkScreen(ctx, c, elapsed);
    } else if (tex._kind === 'events') {
      drawEventsScreen(ctx, c, elapsed, stats);
    }

    // Uptime badge — comum a todas as 3 telas
    drawUptimeBadge(ctx, c, elapsed);

    tex.needsUpdate = true;
  }

  function drawLoadsScreen(ctx, c, elapsed) {
    ctx.font = '700 18px "Orbitron", sans-serif';
    ctx.fillStyle = '#00E5FF';
    ctx.shadowColor = '#00E5FF'; ctx.shadowBlur = 6;
    ctx.textAlign = 'center';
    ctx.fillText('▌ NODE LOAD', c.width / 2, 26);
    ctx.shadowBlur = 0;

    // Top 5 por heat
    const ranked = allAgents
      .map((ag) => ({ ag, data: agentRegistry[ag.name] }))
      .sort((a, b) => (b.data?.heat || 0) - (a.data?.heat || 0))
      .slice(0, 6);

    ctx.font = '12px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';
    ranked.forEach((entry, i) => {
      const y = 60 + i * 36;
      const heat = (entry.data?.heat || 0);
      const working = entry.data?.working || false;
      const barW = Math.max(8, Math.min(360, heat * 360 + (working ? 80 : 0)));
      // Label nome
      ctx.fillStyle = '#E0F2FE';
      ctx.fillText(entry.ag.name.toUpperCase(), 20, y);
      // Bar bg
      ctx.fillStyle = 'rgba(255,255,255,0.06)';
      ctx.fillRect(20, y + 8, 360, 8);
      // Bar fill
      const barColor = heat > 0.7 ? '#FF3060' : (working ? '#FFB300' : '#00FF88');
      ctx.fillStyle = barColor;
      ctx.shadowColor = barColor; ctx.shadowBlur = 4;
      ctx.fillRect(20, y + 8, barW, 8);
      ctx.shadowBlur = 0;
      // Heat percent à direita
      ctx.fillStyle = barColor;
      ctx.font = '11px "JetBrains Mono", monospace';
      ctx.fillText(Math.round((heat + (working ? 0.2 : 0)) * 100) + '%', 390, y + 14);
      ctx.font = '12px "JetBrains Mono", monospace';
    });
  }

  function drawNetworkScreen(ctx, c, elapsed) {
    ctx.font = '700 18px "Orbitron", sans-serif';
    ctx.fillStyle = '#00E5FF';
    ctx.shadowColor = '#00E5FF'; ctx.shadowBlur = 6;
    ctx.textAlign = 'center';
    ctx.fillText('▌ NETWORK TOPOLOGY', c.width / 2, 26);
    ctx.shadowBlur = 0;

    // Nó central (NOC)
    const cx = c.width / 2, cy = c.height / 2 + 10;
    ctx.fillStyle = '#FFB300';
    ctx.shadowColor = '#FFB300'; ctx.shadowBlur = 12;
    ctx.beginPath(); ctx.arc(cx, cy, 14, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = '#FFB300';
    ctx.textAlign = 'center';
    ctx.fillText('NOC', cx, cy + 30);

    // 14 nós em volta (orbital)
    allAgents.forEach((ag, i) => {
      const ang = (i / allAgents.length) * Math.PI * 2 + elapsed * 0.06;
      const r = 110;
      const nx = cx + Math.cos(ang) * r;
      const ny = cy + Math.sin(ang) * r;
      const data = agentRegistry[ag.name];
      const active = data?.working || false;
      // Linha pro centro
      ctx.strokeStyle = active ? '#FFB30090' : 'rgba(0,229,255,0.15)';
      ctx.lineWidth = active ? 1.5 : 0.5;
      ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(nx, ny); ctx.stroke();
      // Nó
      const color = '#' + ag.color.toString(16).padStart(6, '0');
      ctx.fillStyle = color;
      ctx.shadowColor = color; ctx.shadowBlur = active ? 8 : 3;
      ctx.beginPath(); ctx.arc(nx, ny, active ? 6 : 4, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
    });
  }

  function drawEventsScreen(ctx, c, elapsed, stats) {
    ctx.font = '700 18px "Orbitron", sans-serif';
    ctx.fillStyle = '#00E5FF';
    ctx.shadowColor = '#00E5FF'; ctx.shadowBlur = 6;
    ctx.textAlign = 'center';
    ctx.fillText('▌ EVENT LOG · COST', c.width / 2, 26);
    ctx.shadowBlur = 0;

    // Cost sparkline (top half)
    ctx.strokeStyle = '#FF1493';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    const points = costHistory.length > 0 ? costHistory : [0];
    for (let i = 0; i < 60; i++) {
      const idx = Math.max(0, points.length - 60 + i);
      const v = points[idx] || 0;
      const x = 30 + (i / 60) * (c.width - 60);
      const y = 110 - Math.min(80, v * 800);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    // Label cost
    ctx.font = '11px "JetBrains Mono", monospace';
    ctx.fillStyle = '#FF1493';
    ctx.textAlign = 'left';
    ctx.fillText(`COST $${stats.cost.toFixed(3)}`, 30, 130);

    // Event log (bottom half)
    ctx.fillStyle = '#94A3B8';
    ctx.font = '12px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';
    ctx.fillText('▸ Recent events:', 30, 165);
    ctx.font = '11px "JetBrains Mono", monospace';
    const recent = recentEvents.slice(-5).reverse();
    recent.forEach((ev, i) => {
      const y = 188 + i * 22;
      const c1 = ev.type === 'delegation' ? '#FFB300' : (ev.type === 'tool_call' ? '#00E5FF' : '#00FF88');
      ctx.fillStyle = c1;
      ctx.fillText('● ' + ev.type, 30, y);
      ctx.fillStyle = '#E0F2FE';
      ctx.fillText((ev.agent || '-').substring(0, 22), 160, y);
    });
  }

  // ─── Boot ──────────────────────────────────────────────────────
  animate();
  connectWS();
  console.log('[DC] DOMA Datacenter NOC v3 — booted ⚡');
})();
