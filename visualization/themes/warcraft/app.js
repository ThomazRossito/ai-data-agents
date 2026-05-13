/* ============================================================
 * DOMA Guild Hall · V2 (Warcraft theme)
 *
 * FASE 1 — Shell mínimo:
 *   - Three.js scene placeholder (chão de pedra + lareira pulsante)
 *   - WebSocket conectado no mesmo broker do tema Minecraft
 *   - Event log estilo "pergaminho" no HUD
 *   - Sem agentes ainda — só infra funcional
 *
 * Próximas fases (em ordem):
 *   2. Guild hall completo (paredes, banners, lareira, trono)
 *   3. Guildmaster (Supervisor) no trono
 *   4. 5 agentes core T1 (Mage, Warlock, Druid, Rogue, Warrior)
 *   5. Resto dos 14 agentes
 *   6. Conjurações (delegation/tool_call/session_end visuals)
 *   7. HUD WC3 completo (mana, hp, gold)
 * ============================================================ */

(() => {
  "use strict";

  // ─── Three.js scene base ──────────────────────────────────────
  const sceneEl = document.getElementById('scene');
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x1a0f08);
  scene.fog = new THREE.FogExp2(0x1a0f08, 0.045);

  const camera = new THREE.PerspectiveCamera(
    52,
    window.innerWidth / window.innerHeight,
    0.1,
    100
  );
  // Câmera frontal-elevada estilo "Guild Hall WoW" — vê o U inteiro de agentes
  // e o trono ao fundo. Posicionada na "entrada" do salão olhando pra dentro.
  camera.position.set(0, 7, 8.5);
  camera.lookAt(0, 1.3, -4);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  sceneEl.appendChild(renderer.domElement);

  // ─── Iluminação (tavern warm) ─────────────────────────────────
  const ambient = new THREE.AmbientLight(0x6a4030, 0.95);
  scene.add(ambient);

  // Hemisphere: céu warm em cima, chão dourado em baixo
  const hemi = new THREE.HemisphereLight(0xffb877, 0x3a2515, 0.55);
  scene.add(hemi);

  const moonLight = new THREE.DirectionalLight(0xffd9a0, 0.75);
  moonLight.position.set(-8, 14, 6);
  moonLight.castShadow = true;
  moonLight.shadow.mapSize.set(1024, 1024);
  scene.add(moonLight);

  // Spotlight extra direcionado no trono (destaca o Guildmaster)
  const throneSpot = new THREE.SpotLight(0xfff0c8, 1.5, 22, Math.PI / 4, 0.6, 1);
  throneSpot.position.set(0, 11, -2);
  throneSpot.target.position.set(0, 0, -10);
  scene.add(throneSpot);
  scene.add(throneSpot.target);

  // Spotlight central na mesa de estratégia
  const centerSpot = new THREE.SpotLight(0xffd9a0, 1.0, 14, Math.PI / 5, 0.5, 1);
  centerSpot.position.set(0, 9, 0);
  centerSpot.target.position.set(0, 0.5, -4);
  scene.add(centerSpot);
  scene.add(centerSpot.target);

  // ─── Chão de pedra (placeholder) ──────────────────────────────
  const stoneTex = makeStoneTexture();
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(30, 30),
    new THREE.MeshStandardMaterial({
      map: stoneTex,
      roughness: 0.9,
      metalness: 0.05,
    })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);

  // ─── Tapete vermelho circular sob a mesa central ──────────────
  const carpet = new THREE.Mesh(
    new THREE.CircleGeometry(7, 48),
    new THREE.MeshStandardMaterial({
      color: 0xB91C1C,
      roughness: 0.85,
      emissive: 0x3d0808,
      emissiveIntensity: 0.15,
    })
  );
  carpet.rotation.x = -Math.PI / 2;
  carpet.position.set(0, 0.012, -4);
  carpet.receiveShadow = true;
  scene.add(carpet);
  // Borda dourada do tapete (ring)
  const carpetBorder = new THREE.Mesh(
    new THREE.RingGeometry(6.85, 7.05, 64),
    new THREE.MeshStandardMaterial({
      color: 0xD4AF37, metalness: 0.5, roughness: 0.4,
      emissive: 0x3a2a08, emissiveIntensity: 0.25,
      side: THREE.DoubleSide,
    })
  );
  carpetBorder.rotation.x = -Math.PI / 2;
  carpetBorder.position.set(0, 0.014, -4);
  scene.add(carpetBorder);

  // ─── Mesa de estratégia central (council table) ───────────────
  const centralTableGroup = new THREE.Group();
  // Base de pedra
  const tableBase = new THREE.Mesh(
    new THREE.CylinderGeometry(1.6, 1.8, 0.45, 24),
    new THREE.MeshStandardMaterial({ color: 0x5a4a3a, roughness: 0.95 })
  );
  tableBase.position.y = 0.225;
  tableBase.castShadow = true;
  tableBase.receiveShadow = true;
  centralTableGroup.add(tableBase);
  // Topo de madeira
  const tableTop = new THREE.Mesh(
    new THREE.CylinderGeometry(1.7, 1.7, 0.12, 24),
    new THREE.MeshStandardMaterial({
      color: 0x6b3e1c, roughness: 0.7,
      emissive: 0x3a2a08, emissiveIntensity: 0.1,
    })
  );
  tableTop.position.y = 0.51;
  tableTop.castShadow = true;
  tableTop.receiveShadow = true;
  centralTableGroup.add(tableTop);
  // Borda dourada do topo
  const tableTopRing = new THREE.Mesh(
    new THREE.TorusGeometry(1.7, 0.04, 8, 32),
    new THREE.MeshStandardMaterial({
      color: 0xD4AF37, metalness: 0.7, roughness: 0.35,
      emissive: 0x3a2a08, emissiveIntensity: 0.3,
    })
  );
  tableTopRing.rotation.x = Math.PI / 2;
  tableTopRing.position.y = 0.57;
  centralTableGroup.add(tableTopRing);
  // Mapa/pergaminho aberto em cima da mesa (decoração)
  const tableMap = new THREE.Mesh(
    new THREE.PlaneGeometry(1.2, 0.9),
    new THREE.MeshStandardMaterial({
      color: 0xE8D5A8, roughness: 0.85,
      emissive: 0xFCD34D, emissiveIntensity: 0.08,
      side: THREE.DoubleSide,
    })
  );
  tableMap.rotation.x = -Math.PI / 2;
  tableMap.position.y = 0.58;
  centralTableGroup.add(tableMap);
  // Símbolo central (gem dourada flutuante sobre o mapa)
  const tableGem = new THREE.Mesh(
    new THREE.OctahedronGeometry(0.18),
    new THREE.MeshStandardMaterial({
      color: 0xFCD34D, emissive: 0xFBBF24, emissiveIntensity: 1.0,
      metalness: 0.6, roughness: 0.2,
    })
  );
  tableGem.position.y = 1.0;
  centralTableGroup.add(tableGem);
  centralTableGroup.position.set(0, 0, -4);
  scene.add(centralTableGroup);

  // ─── Lareira (placeholder pulsante) ───────────────────────────
  const fireGroup = new THREE.Group();
  // Base de pedra
  const fireplaceBase = new THREE.Mesh(
    new THREE.BoxGeometry(2.5, 0.5, 1.5),
    new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.95 })
  );
  fireplaceBase.position.y = 0.25;
  fireplaceBase.castShadow = true;
  fireplaceBase.receiveShadow = true;
  fireGroup.add(fireplaceBase);

  // "Chama" — cilindro emissivo
  const flameMat = new THREE.MeshStandardMaterial({
    color: 0xff6b35,
    emissive: 0xff4500,
    emissiveIntensity: 1.2,
    transparent: true,
    opacity: 0.85,
  });
  const flame = new THREE.Mesh(
    new THREE.ConeGeometry(0.4, 0.9, 8),
    flameMat
  );
  flame.position.y = 0.85;
  fireGroup.add(flame);

  // Luz da lareira
  const fireLight = new THREE.PointLight(0xff6b35, 2.2, 14, 1.5);
  fireLight.position.y = 1.0;
  fireLight.castShadow = true;
  fireGroup.add(fireLight);

  fireGroup.position.set(0, 0, -8);
  scene.add(fireGroup);

  // ─── Trono dourado ────────────────────────────────────────────
  const throneGroup = new THREE.Group();
  // Base / degraus (3 degraus de pedra)
  for (let i = 0; i < 3; i++) {
    const step = new THREE.Mesh(
      new THREE.BoxGeometry(3.5 - i * 0.8, 0.2, 2.5 - i * 0.5),
      new THREE.MeshStandardMaterial({ color: 0x5a4a3a, roughness: 0.95 })
    );
    step.position.y = 0.1 + i * 0.2;
    step.castShadow = true;
    step.receiveShadow = true;
    throneGroup.add(step);
  }

  // Assento de madeira escura
  const throneSeat = new THREE.Mesh(
    new THREE.BoxGeometry(1.4, 0.35, 1.2),
    new THREE.MeshStandardMaterial({ color: 0x6b3e1c, roughness: 0.7 })
  );
  throneSeat.position.y = 0.92;
  throneSeat.castShadow = true;
  throneGroup.add(throneSeat);

  // Almofada vermelha sobre o assento
  const throneCushion = new THREE.Mesh(
    new THREE.BoxGeometry(1.3, 0.12, 1.1),
    new THREE.MeshStandardMaterial({
      color: 0xB91C1C,
      roughness: 0.65,
      emissive: 0x3d0808,
      emissiveIntensity: 0.15,
    })
  );
  throneCushion.position.y = 1.16;
  throneCushion.castShadow = true;
  throneGroup.add(throneCushion);

  // Encosto alto dourado
  const throneBack = new THREE.Mesh(
    new THREE.BoxGeometry(1.6, 2.6, 0.25),
    new THREE.MeshStandardMaterial({
      color: 0xD4AF37,
      roughness: 0.35,
      metalness: 0.75,
      emissive: 0x3a2a08,
      emissiveIntensity: 0.25,
    })
  );
  throneBack.position.set(0, 2.2, -0.55);
  throneBack.castShadow = true;
  throneGroup.add(throneBack);

  // 2 pontas decorativas no topo do encosto
  for (const dx of [-0.6, 0.6]) {
    const spike = new THREE.Mesh(
      new THREE.ConeGeometry(0.12, 0.5, 6),
      new THREE.MeshStandardMaterial({
        color: 0xFCD34D,
        roughness: 0.3,
        metalness: 0.85,
      })
    );
    spike.position.set(dx, 3.65, -0.55);
    spike.castShadow = true;
    throneGroup.add(spike);
  }

  // 2 braços de apoio dourados
  for (const dx of [-0.85, 0.85]) {
    const arm = new THREE.Mesh(
      new THREE.BoxGeometry(0.18, 0.18, 1.2),
      new THREE.MeshStandardMaterial({
        color: 0xD4AF37,
        roughness: 0.4,
        metalness: 0.7,
      })
    );
    arm.position.set(dx, 1.25, 0);
    arm.castShadow = true;
    throneGroup.add(arm);
  }

  // Aura dourada no chão sob o trono
  const throneAura = new THREE.Mesh(
    new THREE.RingGeometry(1.4, 1.9, 48),
    new THREE.MeshBasicMaterial({
      color: 0xFCD34D,
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
    })
  );
  throneAura.rotation.x = -Math.PI / 2;
  throneAura.position.y = 0.03;
  throneGroup.add(throneAura);

  // ─── Guildmaster (Supervisor) sentado no trono ─────────────────
  const guildmaster = makeGuildmaster();
  guildmaster.position.set(0, 1.22, 0.1);
  throneGroup.add(guildmaster);

  throneGroup.position.set(0, 0, -10);
  scene.add(throneGroup);

  // ─── Paredes do Guild Hall (pedra + vigas de madeira) ─────────
  const wallMat = new THREE.MeshStandardMaterial({
    map: makeWallTexture(),
    roughness: 0.95,
    color: 0x3a2a1a,
  });
  const WALL_H = 6;
  const HALL_W = 30;
  // Fundo (atrás do trono)
  const wallBack = new THREE.Mesh(
    new THREE.PlaneGeometry(HALL_W, WALL_H),
    wallMat
  );
  wallBack.position.set(0, WALL_H / 2, -HALL_W / 2);
  wallBack.receiveShadow = true;
  scene.add(wallBack);
  // Lados
  const wallLeft = wallBack.clone();
  wallLeft.rotation.y = Math.PI / 2;
  wallLeft.position.set(-HALL_W / 2, WALL_H / 2, 0);
  scene.add(wallLeft);
  const wallRight = wallBack.clone();
  wallRight.rotation.y = -Math.PI / 2;
  wallRight.position.set(HALL_W / 2, WALL_H / 2, 0);
  scene.add(wallRight);
  // Frente (atrás da câmera, mas ajuda na iluminação)
  const wallFront = wallBack.clone();
  wallFront.rotation.y = Math.PI;
  wallFront.position.set(0, WALL_H / 2, HALL_W / 2);
  scene.add(wallFront);

  // Vigas de madeira horizontal (topo das paredes)
  const beamMat = new THREE.MeshStandardMaterial({ color: 0x3a2515, roughness: 0.95 });
  for (const [pos, rotY, len] of [
    [[0, WALL_H - 0.2, -HALL_W / 2 + 0.15], 0, HALL_W],
    [[0, WALL_H - 0.2, HALL_W / 2 - 0.15], 0, HALL_W],
    [[-HALL_W / 2 + 0.15, WALL_H - 0.2, 0], Math.PI / 2, HALL_W],
    [[HALL_W / 2 - 0.15, WALL_H - 0.2, 0], Math.PI / 2, HALL_W],
  ]) {
    const beam = new THREE.Mesh(
      new THREE.BoxGeometry(len, 0.4, 0.4),
      beamMat
    );
    beam.position.set(pos[0], pos[1], pos[2]);
    beam.rotation.y = rotY;
    beam.castShadow = true;
    scene.add(beam);
  }

  // ─── Banners da Guilda (4 unidades nas paredes) ───────────────
  const bannerTex = makeBannerTexture();
  const banners = [];
  const bannerPositions = [
    // [x, y, z, rotationY]
    [-6, 4.0, -HALL_W / 2 + 0.05, 0],            // fundo esquerda
    [ 6, 4.0, -HALL_W / 2 + 0.05, 0],            // fundo direita
    [-HALL_W / 2 + 0.05, 4.0, -6, Math.PI / 2],  // esquerda fundo
    [-HALL_W / 2 + 0.05, 4.0,  6, Math.PI / 2],  // esquerda frente
    [ HALL_W / 2 - 0.05, 4.0, -6, -Math.PI / 2], // direita fundo
    [ HALL_W / 2 - 0.05, 4.0,  6, -Math.PI / 2], // direita frente
  ];
  for (const [x, y, z, ry] of bannerPositions) {
    const bg = new THREE.Group();
    // Mastro horizontal de madeira (menor)
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.05, 1.1, 8),
      beamMat
    );
    pole.rotation.z = Math.PI / 2;
    pole.position.y = 0.0;
    bg.add(pole);
    // Tecido do banner (menor)
    const cloth = new THREE.Mesh(
      new THREE.PlaneGeometry(0.95, 1.5),
      new THREE.MeshStandardMaterial({
        map: bannerTex,
        side: THREE.DoubleSide,
        roughness: 0.85,
      })
    );
    cloth.position.y = -0.85;
    cloth.castShadow = true;
    bg.add(cloth);

    bg.position.set(x, y, z);
    bg.rotation.y = ry;
    scene.add(bg);
    banners.push(bg);
  }

  // ─── 14 Agentes da Guilda — todas as classes RPG ──────────────
  // Cada agente é uma "classe RPG" com cor + acessório distintivo.
  // Layout em 3 anéis ao redor do trono (z=-5):
  //   T1 (5): arco interno raio 6.0, próximo ao Guildmaster — core de engenharia
  //   T2 (7): arco externo raio 9.0, segunda fileira — especialistas
  //   T3 + T0 (2): laterais raio 8.5 — intake e conversacional
  const allAgents = [
    // ── T1 — Core de engenharia (arco interno) ──
    { name: 'databricks-engineer',   tier: 'T1', cls: 'mage',        color: 0x2563EB, accent: 0x60A5FA, label: 'Mage' },
    { name: 'databricks-ai',         tier: 'T1', cls: 'warlock',     color: 0x7C3AED, accent: 0xA78BFA, label: 'Warlock' },
    { name: 'fabric-engineer',       tier: 'T1', cls: 'druid',       color: 0x16A34A, accent: 0x4ADE80, label: 'Druid' },
    { name: 'migration-expert',      tier: 'T1', cls: 'rogue',       color: 0x374151, accent: 0x9CA3AF, label: 'Rogue' },
    { name: 'python-expert',         tier: 'T1', cls: 'warrior',     color: 0xB91C1C, accent: 0xFCA5A5, label: 'Warrior' },
    // ── T2 — Especialistas (arco externo) ──
    { name: 'dbt-expert',            tier: 'T2', cls: 'engineer',    color: 0xA16207, accent: 0xFCD34D, label: 'Engineer' },
    { name: 'data-quality-steward',  tier: 'T2', cls: 'priest',      color: 0xE5E7EB, accent: 0xFCD34D, label: 'Priest' },
    { name: 'governance-auditor',    tier: 'T2', cls: 'paladin',     color: 0xD4AF37, accent: 0xFFFFFF, label: 'Paladin' },
    { name: 'data-contracts-engineer', tier: 'T2', cls: 'scribe',    color: 0x78350F, accent: 0xE8D5A8, label: 'Scribe' },
    { name: 'data-mesh-architect',   tier: 'T2', cls: 'warchief',    color: 0x9F1239, accent: 0xFCD34D, label: 'Warchief' },
    { name: 'fabric-rti',            tier: 'T2', cls: 'hunter',      color: 0x15803D, accent: 0x4ADE80, label: 'Hunter' },
    { name: 'fabric-ontology',       tier: 'T2', cls: 'loremaster',  color: 0x92400E, accent: 0xFCD34D, label: 'Loremaster' },
    // ── T3 — Intake ──
    { name: 'business-analyst',      tier: 'T3', cls: 'quest_giver', color: 0xFBBF24, accent: 0xFCD34D, label: 'Quest Giver' },
    // ── T0 — Conversacional ──
    { name: 'geral',                 tier: 'T0', cls: 'innkeeper',   color: 0xA16207, accent: 0xE8D5A8, label: 'Innkeeper' },
  ];

  const agentRegistry = {};       // name -> userData { character, halo, working, ... }
  const agentStationByName = {};  // name -> THREE.Group (a station inteira na cena)

  // Stats da sessão atual — alimenta HUD WC3
  const sessionStats = { cost: 0, turns: 0, duration: 0, events: 0 };
  function updateStatsHUD() {
    const elCost = document.getElementById('stat-mana');
    const elTurns = document.getElementById('stat-hp');
    const elGold = document.getElementById('stat-gold');
    if (elCost) elCost.textContent = `$${sessionStats.cost.toFixed(3)}`;
    if (elTurns) elTurns.textContent = `${sessionStats.turns}`;
    if (elGold) elGold.textContent = `${sessionStats.events}`;
    // Atualiza fills das barras
    const fillCost = document.getElementById('fill-mana');
    const fillHp = document.getElementById('fill-hp');
    const fillGold = document.getElementById('fill-gold');
    if (fillCost) fillCost.style.width = Math.min(100, sessionStats.cost * 200) + '%';
    if (fillHp) fillHp.style.width = Math.min(100, (sessionStats.turns / 50) * 100) + '%';
    if (fillGold) fillGold.style.width = Math.min(100, (sessionStats.events / 100) * 100) + '%';
  }

  // Centro do "U" — onde fica a mesa de estratégia central
  const U_CENTER_X = 0;
  const U_CENTER_Z = -4;
  const t1List = allAgents.filter(a => a.tier === 'T1');
  const t2List = allAgents.filter(a => a.tier === 'T2');
  const t0List = allAgents.filter(a => a.tier === 'T0');
  const t3List = allAgents.filter(a => a.tier === 'T3');

  // Helper: posiciona uma station ao redor do centro do U.
  // angle 0   = trás (z negativo, lado do trono)
  // angle π/2 = lado direito (+x)
  // angle π   = frente (+z, lado da câmera)
  // angle -π/2 = lado esquerdo (-x)
  // O U fica aberto na frente — usamos ângulos de -3π/4 a +3π/4 passando por 0 (fundo).
  function placeOnU(ag, angle, radius, nameplateY) {
    const x = U_CENTER_X + Math.sin(angle) * radius;
    const z = U_CENTER_Z - Math.cos(angle) * radius;
    // Agente olha PRO CENTRO do U (não pro trono diretamente)
    const lookAtAngle = Math.atan2(z - U_CENTER_Z, x - U_CENTER_X) + Math.PI;
    const station = makeAgentStation(ag, lookAtAngle, nameplateY);
    station.position.set(x, 0, z);
    station.rotation.y = -lookAtAngle - Math.PI / 2;
    scene.add(station);
    agentRegistry[ag.name] = station.userData;
    agentStationByName[ag.name] = station;
    return station;
  }

  // Distribuição em 2 lados com GAP central — libera a linha de visão
  // do Guildmaster no trono. Esquerda e direita são simétricos.
  const GAP_HALF = Math.PI / 12;  // ~15° de gap em cada lado do centro

  // T1 (5 agentes): 3 esquerda + 2 direita, anel interno raio 4.0
  // (assimetria mínima porque 5 é ímpar — fica natural)
  const t1Left = t1List.slice(0, 3);
  const t1Right = t1List.slice(3);
  const t1SideSpan = Math.PI / 2;  // cada lado cobre 90° (45° por agente)
  t1Left.forEach((ag, i) => {
    // i=0 mais próximo do centro, i=2 mais lateral
    const angle = -GAP_HALF - (i + 0.5) * (t1SideSpan / t1Left.length);
    placeOnU(ag, angle, 4.0, 2.4);
  });
  t1Right.forEach((ag, i) => {
    const angle = GAP_HALF + (i + 0.5) * (t1SideSpan / t1Right.length);
    placeOnU(ag, angle, 4.0, 2.4);
  });

  // T2 (7 agentes): 4 esquerda + 3 direita, anel externo raio 6.8
  const t2Left = t2List.slice(0, 4);
  const t2Right = t2List.slice(4);
  const t2SideSpan = Math.PI / 1.9;  // cada lado cobre ~95° (~23° por agente)
  t2Left.forEach((ag, i) => {
    const angle = -GAP_HALF - (i + 0.5) * (t2SideSpan / t2Left.length);
    placeOnU(ag, angle, 6.8, 3.2);
  });
  t2Right.forEach((ag, i) => {
    const angle = GAP_HALF + (i + 0.5) * (t2SideSpan / t2Right.length);
    placeOnU(ag, angle, 6.8, 3.2);
  });

  // T3 — business-analyst na ponta direita do U (mais próxima da câmera)
  t3List.forEach((ag) => {
    placeOnU(ag, (3 * Math.PI) / 4, 6.0, 2.4);
  });

  // T0 — geral na ponta esquerda do U
  t0List.forEach((ag) => {
    placeOnU(ag, -(3 * Math.PI) / 4, 6.0, 2.4);
  });

  // ─── Pilares de pedra (4 unidades) — afastados pra não bater nos agentes ──
  const pillarMat = new THREE.MeshStandardMaterial({ color: 0x4a3a2a, roughness: 0.92 });
  for (const [px, pz] of [[-9, -8], [9, -8], [-9, 6], [9, 6]]) {
    // Base
    const base = new THREE.Mesh(
      new THREE.BoxGeometry(0.8, 0.3, 0.8),
      pillarMat
    );
    base.position.set(px, 0.15, pz);
    base.castShadow = true;
    base.receiveShadow = true;
    scene.add(base);
    // Coluna
    const col = new THREE.Mesh(
      new THREE.CylinderGeometry(0.3, 0.32, WALL_H - 0.6, 12),
      pillarMat
    );
    col.position.set(px, WALL_H / 2 - 0.15, pz);
    col.castShadow = true;
    scene.add(col);
    // Capitel
    const cap = new THREE.Mesh(
      new THREE.BoxGeometry(0.9, 0.25, 0.9),
      pillarMat
    );
    cap.position.set(px, WALL_H - 0.45, pz);
    cap.castShadow = true;
    scene.add(cap);
  }

  // ─── Tochas decorativas nos cantos ────────────────────────────
  function addTorch(x, z) {
    const post = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.05, 1.6, 8),
      new THREE.MeshStandardMaterial({ color: 0x3a2a1a, roughness: 0.95 })
    );
    post.position.set(x, 0.8, z);
    post.castShadow = true;
    scene.add(post);

    const flame = new THREE.Mesh(
      new THREE.SphereGeometry(0.18, 8, 8),
      new THREE.MeshStandardMaterial({
        color: 0xffaa44,
        emissive: 0xff6b35,
        emissiveIntensity: 1.5,
      })
    );
    flame.position.set(x, 1.7, z);
    scene.add(flame);

    const flameLight = new THREE.PointLight(0xffaa44, 0.9, 7, 2);
    flameLight.position.set(x, 1.8, z);
    scene.add(flameLight);
    return { flame, flameLight };
  }
  const torches = [
    addTorch(-9, -9),
    addTorch( 9, -9),
    addTorch(-9,  9),
    addTorch( 9,  9),
  ];

  // (placeholder do centro removido — agora o Guildmaster e os agentes ocupam o salão)

  // ─── Animation loop ───────────────────────────────────────────
  let frameCount = 0;
  const t0 = Date.now();
  function animate() {
    requestAnimationFrame(animate);
    const elapsed = (Date.now() - t0) / 1000;
    frameCount++;

    // Flame pulse
    const firePulse = 1.0 + Math.sin(elapsed * 4) * 0.18 + Math.sin(elapsed * 11) * 0.06;
    flame.scale.set(firePulse, 1 + Math.sin(elapsed * 3.5) * 0.12, firePulse);
    flameMat.emissiveIntensity = 1.0 + Math.sin(elapsed * 5) * 0.4;
    fireLight.intensity = 1.8 + Math.sin(elapsed * 4) * 0.5;

    // Torches pulse
    torches.forEach((t, i) => {
      const ph = i * 1.3;
      t.flame.scale.setScalar(1 + Math.sin(elapsed * 6 + ph) * 0.1);
      t.flameLight.intensity = 0.7 + Math.sin(elapsed * 7 + ph) * 0.25;
    });

    // Trono aura pulse
    throneAura.material.opacity = 0.3 + Math.sin(elapsed * 1.5) * 0.1;
    throneAura.rotation.z += 0.003;

    // Guildmaster idle — cabeça olha lentamente pros lados, joia da coroa pulsa
    guildmaster.head.rotation.y = Math.sin(elapsed * 0.4) * 0.18;
    guildmaster.head.rotation.x = Math.sin(elapsed * 0.7) * 0.04;
    guildmaster.gem.material.emissiveIntensity = 0.5 + Math.sin(elapsed * 2.2) * 0.4;
    guildmaster.gem.rotation.y += 0.02;
    guildmaster.crownBase.material.emissiveIntensity = 0.35 + Math.sin(elapsed * 1.8) * 0.15;

    // Banners — leve ondular como ao vento
    banners.forEach((b, i) => {
      const phase = i * 0.7;
      b.rotation.z = Math.sin(elapsed * 0.8 + phase) * 0.025;
    });

    // Gem da mesa central — gira e pulsa
    tableGem.rotation.y += 0.018;
    tableGem.rotation.z += 0.008;
    tableGem.position.y = 1.0 + Math.sin(elapsed * 1.5) * 0.08;
    tableGem.material.emissiveIntensity = 0.8 + Math.sin(elapsed * 2.3) * 0.4;

    // Spells ativas — animação e cleanup quando lifetime expira
    const now = Date.now();
    for (let i = activeSpells.length - 1; i >= 0; i--) {
      const s = activeSpells[i];
      const tElapsed = now - s.t0;
      const pct = tElapsed / s.lifetime;
      if (pct >= 1) {
        scene.remove(s.mesh);
        activeSpells.splice(i, 1);
        continue;
      }
      const tSec = tElapsed / 1000;
      // Bob vertical comum a todas as spells
      s.mesh.position.y = 1.8 + Math.sin(tSec * 4) * 0.08;
      // Spin opcional
      if (s.mesh.spinSpeed) s.mesh.rotation.y += s.mesh.spinSpeed * 0.016;
      // Pulsação do main + glow
      const pulse = 0.85 + Math.sin(tSec * 6) * 0.15;
      if (s.mesh.mainMesh && s.mesh.mainMesh.scale) {
        s.mesh.mainMesh.scale.setScalar(pulse);
      }
      // Shockwave do warrior — expande e fade
      if (s.mesh.isShockwave) {
        const sc = 1 + pct * 3;
        s.mesh.mainMesh.scale.set(sc, 1, sc);
        s.mesh.mainMesh.material.opacity = 0.9 * (1 - pct);
      }
      // Vapor do innkeeper — sobe
      if (s.mesh.isVapor) {
        s.mesh.children.forEach((p, idx) => {
          p.position.y = (p.userData.basePy || 0) + tSec * 0.4;
          p.material.opacity = Math.max(0, 0.75 - idx * 0.15 - pct * 0.6);
        });
      }
      // Fade out nos últimos 30% da vida
      if (pct > 0.7) {
        const fadeOut = 1 - (pct - 0.7) / 0.3;
        s.mesh.traverse((child) => {
          if (child.material && child.material.opacity !== undefined && child.material.transparent) {
            child.material.opacity = Math.min(child.material.opacity, fadeOut * 0.95);
          }
          if (child.material && child.material.emissiveIntensity !== undefined) {
            child.material.emissiveIntensity *= fadeOut * 1.02;
          }
        });
      }
    }

    // Beams Bezier do Guildmaster — orbe viaja, depois tube + orb fade out
    for (let i = activeBeams.length - 1; i >= 0; i--) {
      const b = activeBeams[i];
      const tElapsed = now - b.t0;
      const pct = tElapsed / b.lifetime;
      if (pct >= 1) {
        scene.remove(b.tube);
        scene.remove(b.orb);
        activeBeams.splice(i, 1);
        continue;
      }
      // Orbe viaja ao longo da curva (mais rápido no início)
      const u = Math.min(1, pct * 1.2);
      const pt = b.curve.getPoint(u);
      b.orb.position.copy(pt);
      // Tube fade out gradual
      b.tube.material.opacity = 0.85 * (1 - pct);
      b.orb.material.opacity = 1.0 * (1 - pct * 0.8);
    }

    // Agentes T1 — pulse working + idle subtle
    Object.values(agentRegistry).forEach((ag) => {
      const tPulse = elapsed * 3 + ag.idlePhase;
      const breath = Math.sin(elapsed * 1.2 + ag.idlePhase) * 0.5 + 0.5;
      // Respiração sutil sempre (head é local ao character; mantém na altura padrão)
      ag.character.head.position.y = 0.5 + breath * 0.02;
      ag.character.position.y = 0.9 + breath * 0.015;

      if (ag.working) {
        const p = 0.5 + Math.sin(tPulse) * 0.5;
        // Halo aparece e pulsa
        ag.halo.material.opacity = 0.45 + p * 0.45;
        ag.halo.rotation.z += 0.02;
        // Braços typing
        ag.character.armL.rotation.x = -Math.PI / 8 + Math.sin(tPulse * 8) * 0.4;
        ag.character.armR.rotation.x = -Math.PI / 8 + Math.sin(tPulse * 8 + Math.PI) * 0.4;
        // Cabeça inclinada lendo mesa
        ag.character.head.rotation.x = 0.18 + Math.sin(tPulse * 2) * 0.06;
        // Prop em cima da mesa pulsa (orb mago, cristal druid, etc)
        if (ag.tableProp && ag.tableProp.orb) {
          ag.tableProp.orb.material.emissiveIntensity = 0.5 + p * 0.6;
          ag.tableProp.rotation.y += 0.02;
        }
        if (ag.tableProp && ag.tableProp.liquid) {
          ag.tableProp.liquid.material.emissiveIntensity = 0.4 + p * 0.6;
        }
      } else {
        // Volta neutro suave
        ag.halo.material.opacity *= 0.92;
        ag.character.armL.rotation.x *= 0.85;
        ag.character.armR.rotation.x *= 0.85;
        ag.character.head.rotation.x *= 0.92;
        if (ag.tableProp && ag.tableProp.orb) {
          ag.tableProp.orb.material.emissiveIntensity = 0.45 + Math.sin(elapsed * 1.5 + ag.idlePhase) * 0.15;
        }
      }
    });

    // Camera idle drift — leve oscilação lateral mantendo frontal
    camera.position.x = Math.sin(elapsed * 0.1) * 0.6;
    camera.position.z = 8.5 + Math.cos(elapsed * 0.08) * 0.3;
    camera.lookAt(0, 1.3, -4);

    renderer.render(scene, camera);
  }

  // Resize handler
  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // ─── WebSocket client (mesmo backend do tema Minecraft) ───────
  const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProto}//${window.location.host}/events`;
  const logEntries = document.getElementById('log-entries');
  const eventCountEl = document.getElementById('event-count');
  const connDot = document.getElementById('conn-dot');
  const connText = document.getElementById('conn-text');
  let eventCount = 0;

  function setConn(state, text) {
    connDot.className = `dot ${state}`;
    connText.textContent = text;
  }

  function addLogEntry(evt) {
    eventCount++;
    eventCountEl.textContent = eventCount;

    const entry = document.createElement('div');
    entry.className = 'entry';
    const ts = new Date().toLocaleTimeString('pt-BR', { hour12: false });
    const typeIcon = {
      delegation: '⚔️',
      tool_call: '🪄',
      dispatcher_decision: '📜',
      session_end: '🏁',
    }[evt.type] || '✨';
    entry.innerHTML = `
      <span class="type">${typeIcon} ${evt.type}</span>
      <span class="ts">${ts}</span>
      ${evt.agent ? `<div><span class="agent">${evt.agent}</span></div>` : ''}
      ${evt.tool ? `<div style="color:#B8A988;font-size:10px;">${evt.tool}</div>` : ''}
    `;
    logEntries.insertBefore(entry, logEntries.firstChild);

    // Mantém só 50 entradas
    while (logEntries.children.length > 50) {
      logEntries.removeChild(logEntries.lastChild);
    }
  }

  function connectWS() {
    setConn('connecting', 'Conjurando portal...');
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConn('connected', 'Portal aberto ✓');
      console.log('[WC] WebSocket conectado:', wsUrl);
    };

    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse(e.data);
        addLogEntry(evt);
        handleSceneEvent(evt);
      } catch (err) {
        console.warn('[WC] parse error:', err);
      }
    };

    ws.onclose = () => {
      setConn('disconnected', 'Portal fechou — reconectando...');
      setTimeout(connectWS, 2500);
    };

    ws.onerror = (err) => {
      console.error('[WC] ws error:', err);
    };
  }

  // ─── Sistema de conjurações (spells + beams) ──────────────────
  // Spells ativas (efeitos 3D acima das mesas que aparecem em tool_call)
  // Cada spell tem: mesh, t0 (timestamp), lifetime, agent ref
  const activeSpells = [];
  // Beams ativos (curva dourada Guildmaster → agente, dispara em delegation)
  const activeBeams = [];

  // Cria efeito 3D específico da classe
  function makeSpellEffect(cls, color, accent) {
    const g = new THREE.Group();

    if (cls === 'mage') {
      // Fireball azul
      const ball = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 14, 14),
        new THREE.MeshStandardMaterial({
          color, emissive: accent, emissiveIntensity: 1.4,
          transparent: true, opacity: 0.85,
        })
      );
      g.add(ball);
      const halo = new THREE.Mesh(
        new THREE.SphereGeometry(0.3, 10, 10),
        new THREE.MeshStandardMaterial({
          color: accent, emissive: accent, emissiveIntensity: 0.8,
          transparent: true, opacity: 0.25,
        })
      );
      g.add(halo);
      return Object.assign(g, { mainMesh: ball, glow: halo });
    }
    if (cls === 'warlock') {
      // Orbe de sombra roxo com pulsação dual
      const inner = new THREE.Mesh(
        new THREE.SphereGeometry(0.15, 12, 12),
        new THREE.MeshStandardMaterial({
          color: 0x18181b, emissive: accent, emissiveIntensity: 1.1,
        })
      );
      g.add(inner);
      const outer = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.28),
        new THREE.MeshStandardMaterial({
          color, emissive: color, emissiveIntensity: 0.6,
          transparent: true, opacity: 0.5, wireframe: true,
        })
      );
      g.add(outer);
      return Object.assign(g, { mainMesh: inner, glow: outer });
    }
    if (cls === 'druid') {
      // Espiral de folhas verdes
      for (let i = 0; i < 6; i++) {
        const ang = (i / 6) * Math.PI * 2;
        const leaf = new THREE.Mesh(
          new THREE.BoxGeometry(0.08, 0.02, 0.16),
          new THREE.MeshStandardMaterial({
            color: 0x4ADE80, emissive: accent, emissiveIntensity: 0.7,
            transparent: true, opacity: 0.9,
          })
        );
        leaf.position.set(Math.cos(ang) * 0.22, 0, Math.sin(ang) * 0.22);
        leaf.rotation.y = ang;
        g.add(leaf);
      }
      return Object.assign(g, { mainMesh: g, glow: null, spinSpeed: 3.5 });
    }
    if (cls === 'rogue') {
      // 2 lâminas cruzadas brilhando
      const b1 = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.36, 0.04),
        new THREE.MeshStandardMaterial({
          color: 0xE5E7EB, metalness: 0.9,
          emissive: 0xE5E7EB, emissiveIntensity: 0.6,
        })
      );
      b1.rotation.z = Math.PI / 4;
      g.add(b1);
      const b2 = b1.clone();
      b2.rotation.z = -Math.PI / 4;
      g.add(b2);
      return Object.assign(g, { mainMesh: g, glow: null, spinSpeed: 5 });
    }
    if (cls === 'warrior') {
      // Onda de choque (anel + pulsação)
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(0.25, 0.04, 8, 24),
        new THREE.MeshStandardMaterial({
          color, emissive: color, emissiveIntensity: 1.0,
          transparent: true, opacity: 0.9,
        })
      );
      ring.rotation.x = Math.PI / 2;
      g.add(ring);
      return Object.assign(g, { mainMesh: ring, glow: null, isShockwave: true });
    }
    if (cls === 'engineer') {
      // Engrenagem dourada girando
      const gear = new THREE.Mesh(
        new THREE.CylinderGeometry(0.2, 0.2, 0.05, 8),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, metalness: 0.85,
          emissive: accent, emissiveIntensity: 0.7,
        })
      );
      gear.rotation.x = Math.PI / 2;
      g.add(gear);
      return Object.assign(g, { mainMesh: gear, glow: null, spinSpeed: 6 });
    }
    if (cls === 'priest') {
      // Pilar de luz dourada subindo
      const pillar = new THREE.Mesh(
        new THREE.CylinderGeometry(0.1, 0.15, 0.6, 10),
        new THREE.MeshStandardMaterial({
          color: 0xFFFFFF, emissive: 0xFCD34D, emissiveIntensity: 1.2,
          transparent: true, opacity: 0.75,
        })
      );
      pillar.position.y = 0.3;
      g.add(pillar);
      const cross = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.18, 0.04),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, emissive: 0xFCD34D, emissiveIntensity: 1.0,
        })
      );
      cross.position.y = 0.55;
      g.add(cross);
      const crossH = new THREE.Mesh(
        new THREE.BoxGeometry(0.14, 0.04, 0.04),
        cross.material
      );
      crossH.position.y = 0.58;
      g.add(crossH);
      return Object.assign(g, { mainMesh: pillar, glow: cross });
    }
    if (cls === 'paladin') {
      // Martelo dourado pulsando
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(0.26, 0.2, 0.22),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, metalness: 0.85,
          emissive: 0xFCD34D, emissiveIntensity: 0.9,
        })
      );
      g.add(head);
      const aura = new THREE.Mesh(
        new THREE.TorusGeometry(0.32, 0.03, 8, 16),
        new THREE.MeshStandardMaterial({
          color: 0xFFFFFF, emissive: 0xFCD34D, emissiveIntensity: 0.8,
          transparent: true, opacity: 0.7,
        })
      );
      aura.rotation.x = Math.PI / 2;
      g.add(aura);
      return Object.assign(g, { mainMesh: head, glow: aura, spinSpeed: 1.5 });
    }
    if (cls === 'scribe') {
      // Runas voando (3 octahedras)
      for (let i = 0; i < 3; i++) {
        const rune = new THREE.Mesh(
          new THREE.OctahedronGeometry(0.08),
          new THREE.MeshStandardMaterial({
            color: 0xE8D5A8, emissive: 0xFCD34D, emissiveIntensity: 0.8,
            transparent: true, opacity: 0.9,
          })
        );
        const ang = (i / 3) * Math.PI * 2;
        rune.position.set(Math.cos(ang) * 0.18, 0, Math.sin(ang) * 0.18);
        g.add(rune);
      }
      return Object.assign(g, { mainMesh: g, glow: null, spinSpeed: 2.5 });
    }
    if (cls === 'warchief') {
      // Marca tribal vermelha pulsando (estrela 5 pontas tipo crystals)
      for (let i = 0; i < 5; i++) {
        const ang = (i / 5) * Math.PI * 2;
        const spike = new THREE.Mesh(
          new THREE.ConeGeometry(0.05, 0.18, 4),
          new THREE.MeshStandardMaterial({
            color, emissive: color, emissiveIntensity: 0.9,
          })
        );
        spike.position.set(Math.cos(ang) * 0.18, 0, Math.sin(ang) * 0.18);
        spike.rotation.z = -ang;
        g.add(spike);
      }
      return Object.assign(g, { mainMesh: g, glow: null, spinSpeed: 2 });
    }
    if (cls === 'hunter') {
      // Seta voando em ângulo
      const shaft = new THREE.Mesh(
        new THREE.CylinderGeometry(0.02, 0.02, 0.45, 8),
        new THREE.MeshStandardMaterial({
          color: 0xE8D5A8, emissive: accent, emissiveIntensity: 0.5,
        })
      );
      shaft.rotation.z = -Math.PI / 4;
      g.add(shaft);
      const tip = new THREE.Mesh(
        new THREE.ConeGeometry(0.04, 0.1, 6),
        new THREE.MeshStandardMaterial({
          color: 0xE5E7EB, metalness: 0.9,
          emissive: accent, emissiveIntensity: 0.8,
        })
      );
      tip.position.set(0.16, 0.16, 0);
      tip.rotation.z = Math.PI / 4;
      g.add(tip);
      return Object.assign(g, { mainMesh: g, glow: null });
    }
    if (cls === 'loremaster') {
      // Livro abrindo com luz âmbar emanando
      const book = new THREE.Mesh(
        new THREE.BoxGeometry(0.3, 0.06, 0.22),
        new THREE.MeshStandardMaterial({
          color: 0x7c2d12, emissive: 0xFCD34D, emissiveIntensity: 0.7,
        })
      );
      g.add(book);
      const glow = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 10, 10),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, emissive: 0xFBBF24, emissiveIntensity: 1.2,
          transparent: true, opacity: 0.6,
        })
      );
      glow.position.y = 0.12;
      g.add(glow);
      return Object.assign(g, { mainMesh: book, glow });
    }
    if (cls === 'quest_giver') {
      // "!" amarelo pulsante grande
      const bar = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.32, 0.08),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, emissive: 0xFBBF24, emissiveIntensity: 1.3,
        })
      );
      bar.position.y = 0.1;
      g.add(bar);
      const dot = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.08, 0.08),
        bar.material
      );
      dot.position.y = -0.14;
      g.add(dot);
      return Object.assign(g, { mainMesh: bar, glow: dot });
    }
    if (cls === 'innkeeper') {
      // Vapor saindo da jarra (3 esferas brancas)
      for (let i = 0; i < 3; i++) {
        const puff = new THREE.Mesh(
          new THREE.SphereGeometry(0.07 + i * 0.02, 8, 8),
          new THREE.MeshStandardMaterial({
            color: 0xfff8e1, emissive: 0xE8D5A8, emissiveIntensity: 0.35,
            transparent: true, opacity: 0.75 - i * 0.15,
          })
        );
        puff.position.y = i * 0.12;
        puff.userData.basePy = i * 0.12;
        g.add(puff);
      }
      return Object.assign(g, { mainMesh: g, glow: null, isVapor: true });
    }
    // Fallback genérico
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.14, 10, 10),
      new THREE.MeshStandardMaterial({
        color, emissive: accent, emissiveIntensity: 1.0,
        transparent: true, opacity: 0.85,
      })
    );
    g.add(sphere);
    return Object.assign(g, { mainMesh: sphere, glow: null });
  }

  // Cria beam dourado curvo (QuadraticBezier) do trono pra um agente
  function makeGuildmasterBeam(targetStation) {
    if (!targetStation) return null;
    const start = new THREE.Vector3(0, 2.5, -10);  // posição da coroa do Guildmaster
    const end = targetStation.position.clone().add(new THREE.Vector3(0, 1.8, 0));
    // Curva passando por cima (arco alto)
    const mid = start.clone().add(end).multiplyScalar(0.5);
    mid.y += 2.2;
    const curve = new THREE.QuadraticBezierCurve3(start, mid, end);

    const tube = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 24, 0.04, 8, false),
      new THREE.MeshStandardMaterial({
        color: 0xFCD34D, emissive: 0xFCD34D, emissiveIntensity: 1.2,
        transparent: true, opacity: 0.85,
      })
    );
    scene.add(tube);

    // Esfera luminosa que viaja ao longo da curva
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.12, 10, 10),
      new THREE.MeshStandardMaterial({
        color: 0xFFFFFF, emissive: 0xFCD34D, emissiveIntensity: 2.0,
        transparent: true, opacity: 1.0,
      })
    );
    scene.add(orb);

    return {
      tube, orb, curve,
      t0: Date.now(),
      lifetime: 1200,
      target: targetStation,
    };
  }

  // Spawna spell effect acima da mesa do agente
  function spawnSpell(agentData, agentStation) {
    if (!agentData || !agentStation) return;
    // Limita 1 spell ativa por agente — limpa anterior se houver
    const existing = activeSpells.find(s => s.agent === agentData);
    if (existing) {
      scene.remove(existing.mesh);
      activeSpells.splice(activeSpells.indexOf(existing), 1);
    }
    const ag = allAgents.find(a => a.name === agentData.nameRaw || agentData.cls === a.cls);
    // Usa cls + color do agentData
    const spell = makeSpellEffect(agentData.cls, agentData.baseColor, agentData.accent);
    if (!spell) return;
    // Posição: ~2.3m acima da cadeira do agente (mais alto agora que cadeira é mais alta)
    const worldPos = new THREE.Vector3();
    agentStation.getWorldPosition(worldPos);
    spell.position.set(worldPos.x, 2.4, worldPos.z);
    // Escala global 1.3x — visível sem ficar exagerado com câmera frontal
    spell.scale.setScalar(1.3);
    scene.add(spell);
    activeSpells.push({
      mesh: spell,
      agent: agentData,
      t0: Date.now(),
      lifetime: 2200,
    });
  }

  // ─── Handler de eventos: acende/apaga agentes ─────────────────
  function handleSceneEvent(evt) {
    if (!evt || !evt.type) return;
    const isBacklog = !!evt._backlog;
    const ag = evt.agent && agentRegistry[evt.agent];
    const stationGroup = evt.agent && agentStationByName[evt.agent];

    if (evt.type === 'delegation') {
      if (ag && !isBacklog) {
        ag.working = true;
        ag.workingStartedAt = Date.now();
        // Beam dourado do Guildmaster pro agente
        const beam = makeGuildmasterBeam(stationGroup);
        if (beam) activeBeams.push(beam);
      }
    } else if (evt.type === 'tool_call') {
      if (ag && !isBacklog) {
        ag.working = true;
        ag.workingStartedAt = Date.now();
        // Conjuração específica da classe
        spawnSpell(ag, stationGroup);
      }
    } else if (evt.type === 'session_end') {
      Object.values(agentRegistry).forEach((aa) => {
        aa.working = false;
        if (aa.halo) aa.halo.material.opacity = 0;
      });
    }

    // Atualiza HUD WC3
    if (!isBacklog && evt.type === 'session_end' && evt.metadata) {
      sessionStats.cost += (evt.metadata.cost_usd || 0);
      sessionStats.turns += (evt.metadata.turns || 0);
      sessionStats.duration += (evt.metadata.duration_s || 0);
      updateStatsHUD();
    } else if (!isBacklog) {
      sessionStats.events++;
      updateStatsHUD();
    }
  }

  // ─── Texturas procedurais (placeholders) ──────────────────────
  function makeStoneTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#3d2d20';
    ctx.fillRect(0, 0, 256, 256);
    // Pedras irregulares
    for (let i = 0; i < 30; i++) {
      const x = Math.random() * 256;
      const y = Math.random() * 256;
      const r = 18 + Math.random() * 22;
      ctx.fillStyle = `rgba(${60 + Math.random() * 30}, ${42 + Math.random() * 20}, ${30 + Math.random() * 15}, 0.85)`;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(20, 12, 8, 0.6)';
      ctx.lineWidth = 1.2;
      ctx.stroke();
    }
    const tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(6, 6);
    return tex;
  }

  function makeWallTexture() {
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const ctx = c.getContext('2d');
    // Base
    ctx.fillStyle = '#2d1f14';
    ctx.fillRect(0, 0, 256, 256);
    // Tijolos irregulares
    for (let row = 0; row < 8; row++) {
      const yOff = row * 32;
      const xShift = (row % 2) * 16;
      for (let col = -1; col < 8; col++) {
        const x = col * 32 + xShift;
        const w = 28 + Math.random() * 4;
        const h = 28 + Math.random() * 2;
        ctx.fillStyle = `rgba(${50 + Math.random() * 30}, ${35 + Math.random() * 18}, ${22 + Math.random() * 12}, 1)`;
        ctx.fillRect(x + 2, yOff + 2, w, h);
        ctx.strokeStyle = 'rgba(15, 8, 4, 0.7)';
        ctx.lineWidth = 1.5;
        ctx.strokeRect(x + 2, yOff + 2, w, h);
        // Pontinhos de musgo/sujeira
        if (Math.random() < 0.3) {
          ctx.fillStyle = `rgba(${30 + Math.random() * 40}, ${50 + Math.random() * 30}, ${20 + Math.random() * 20}, 0.4)`;
          ctx.beginPath();
          ctx.arc(x + 10 + Math.random() * 12, yOff + 10 + Math.random() * 12, 2 + Math.random() * 3, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    const tex = new THREE.CanvasTexture(c);
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(4, 1.2);
    return tex;
  }

  function makeBannerTexture() {
    const c = document.createElement('canvas');
    c.width = 256;
    c.height = 384;
    const ctx = c.getContext('2d');
    // Fundo vermelho com gradient sutil
    const grad = ctx.createLinearGradient(0, 0, 0, 384);
    grad.addColorStop(0, '#9F1239');
    grad.addColorStop(0.5, '#B91C1C');
    grad.addColorStop(1, '#7f1d1d');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 256, 384);
    // Borda dourada
    ctx.strokeStyle = '#D4AF37';
    ctx.lineWidth = 6;
    ctx.strokeRect(6, 6, 244, 372);
    ctx.lineWidth = 2;
    ctx.strokeRect(16, 16, 224, 352);
    // Brasão DOMA — círculo central
    ctx.fillStyle = '#FCD34D';
    ctx.beginPath();
    ctx.arc(128, 180, 56, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#A16207';
    ctx.lineWidth = 3;
    ctx.stroke();
    // Letra D dentro do brasão
    ctx.font = '900 80px "Cinzel", serif';
    ctx.fillStyle = '#7f1d1d';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('D', 128, 184);
    // Texto DOMA acima
    ctx.font = '700 24px "Cinzel", serif';
    ctx.fillStyle = '#FCD34D';
    ctx.fillText('DOMA', 128, 80);
    // Texto GUILD abaixo
    ctx.font = 'italic 18px "MedievalSharp", cursive';
    ctx.fillStyle = '#E8D5A8';
    ctx.fillText('~ Guild Hall ~', 128, 280);
    // Estrelas decorativas nos cantos
    for (const [sx, sy] of [[40, 50], [216, 50], [40, 334], [216, 334]]) {
      ctx.fillStyle = '#FCD34D';
      ctx.beginPath();
      ctx.arc(sx, sy, 5, 0, Math.PI * 2);
      ctx.fill();
    }
    // Pontinhas inferior em V (estilo bandeira)
    ctx.fillStyle = '#050816';
    ctx.beginPath();
    ctx.moveTo(0, 384);
    ctx.lineTo(64, 360);
    ctx.lineTo(128, 384);
    ctx.lineTo(192, 360);
    ctx.lineTo(256, 384);
    ctx.lineTo(256, 384);
    ctx.closePath();
    ctx.fill();
    return new THREE.CanvasTexture(c);
  }

  // ─── Estação de agente (mesa + cadeira + personagem + halo + nameplate) ──
  function makeAgentStation(ag, faceAngle, nameplateY = 2.6) {
    const station = new THREE.Group();

    // Mesa de madeira tipo "tavern"
    const tableTop = new THREE.Mesh(
      new THREE.BoxGeometry(1.6, 0.12, 0.9),
      new THREE.MeshStandardMaterial({ color: 0x6b3e1c, roughness: 0.75 })
    );
    tableTop.position.y = 0.95;
    tableTop.castShadow = true;
    tableTop.receiveShadow = true;
    station.add(tableTop);
    // 4 pernas
    for (const [px, pz] of [[-0.7, -0.35], [0.7, -0.35], [-0.7, 0.35], [0.7, 0.35]]) {
      const leg = new THREE.Mesh(
        new THREE.BoxGeometry(0.1, 0.95, 0.1),
        new THREE.MeshStandardMaterial({ color: 0x4a2818, roughness: 0.9 })
      );
      leg.position.set(px, 0.475, pz);
      leg.castShadow = true;
      station.add(leg);
    }

    // Cadeira alta estilo trono pequeno (assento + encosto + base dourada)
    // Estilo "council chair" do WoW Guild Hall
    const chairSeat = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 0.12, 0.55),
      new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.85 })
    );
    chairSeat.position.set(0, 0.48, -0.85);
    chairSeat.castShadow = true;
    station.add(chairSeat);
    // Almofada vermelha
    const cushion = new THREE.Mesh(
      new THREE.BoxGeometry(0.5, 0.08, 0.5),
      new THREE.MeshStandardMaterial({
        color: 0xB91C1C, roughness: 0.7,
        emissive: 0x3d0808, emissiveIntensity: 0.1,
      })
    );
    cushion.position.set(0, 0.58, -0.85);
    station.add(cushion);
    // Pernas da cadeira
    for (const [px, pz] of [[-0.22, -1.07], [0.22, -1.07], [-0.22, -0.63], [0.22, -0.63]]) {
      const leg = new THREE.Mesh(
        new THREE.BoxGeometry(0.06, 0.48, 0.06),
        new THREE.MeshStandardMaterial({ color: 0x4a2818, roughness: 0.9 })
      );
      leg.position.set(px, 0.24, pz);
      station.add(leg);
    }
    // Encosto alto
    const chairBack = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 1.1, 0.08),
      new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.85 })
    );
    chairBack.position.set(0, 1.05, -1.13);
    chairBack.castShadow = true;
    station.add(chairBack);
    // Detalhe dourado no topo do encosto
    const chairTop = new THREE.Mesh(
      new THREE.BoxGeometry(0.6, 0.08, 0.1),
      new THREE.MeshStandardMaterial({
        color: 0xD4AF37, metalness: 0.7, roughness: 0.35,
        emissive: 0x3a2a08, emissiveIntensity: 0.25,
      })
    );
    chairTop.position.set(0, 1.62, -1.13);
    station.add(chairTop);

    // Personagem sentado na cadeira
    const character = makeClassCharacter(ag.cls, ag.color, ag.accent);
    character.position.set(0, 0.9, -0.85);
    station.add(character);

    // Objeto característico em cima da mesa (varia por classe)
    const tableProp = makeClassProp(ag.cls, ag.color, ag.accent);
    if (tableProp) {
      tableProp.position.set(0.15, 1.05, 0);
      station.add(tableProp);
    }

    // Halo no chão sob a cadeira do agente
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.55, 0.78, 32),
      new THREE.MeshBasicMaterial({
        color: ag.color,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
      })
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.set(0, 0.02, -0.85);
    station.add(halo);

    // Nameplate flutuante acima da cabeça — altura varia por tier pra evitar
    // sobreposição entre anéis interno (T1) e externo (T2)
    const np = makeAgentNameplate(ag.name, ag.label, ag.color);
    np.sprite.position.set(0, nameplateY, -0.85);
    station.add(np.sprite);

    station.userData = {
      character,
      tableProp,
      halo,
      nameplate: np,
      working: false,
      baseColor: ag.color,
      accent: ag.accent,
      cls: ag.cls,
      idlePhase: Math.random() * Math.PI * 2,
    };

    return station;
  }

  // Cria personagem voxel-fantasy por classe
  function makeClassCharacter(cls, color, accent) {
    const g = new THREE.Group();
    const skinMat = new THREE.MeshStandardMaterial({ color: 0xF5D5B8, roughness: 0.75 });
    const robeMat = new THREE.MeshStandardMaterial({
      color, roughness: 0.7,
      emissive: color, emissiveIntensity: 0.05,
    });
    const accentMat = new THREE.MeshStandardMaterial({
      color: accent, roughness: 0.5, metalness: 0.3,
      emissive: accent, emissiveIntensity: 0.15,
    });

    // Corpo / robe
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.6, 0.35), robeMat);
    body.castShadow = true;
    g.add(body);

    // Cabeça
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.36, 0.36), skinMat);
    head.position.y = 0.5;
    head.castShadow = true;
    g.add(head);

    // Olhos (warlock = verde brilhante; outros = preto)
    const eyeMat = cls === 'warlock'
      ? new THREE.MeshBasicMaterial({ color: 0x4ADE80 })
      : new THREE.MeshBasicMaterial({ color: 0x0a0a0a });
    for (const dx of [-0.08, 0.08]) {
      const eye = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.02), eyeMat);
      eye.position.set(dx, 0.52, 0.185);
      g.add(eye);
    }

    // Braços (sempre, mas escondidos em alguns por capuz)
    const armMat = new THREE.MeshStandardMaterial({ color, roughness: 0.7 });
    const armL = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.45, 0.14), armMat);
    armL.position.set(-0.28, 0.05, 0);
    armL.castShadow = true;
    g.add(armL);
    const armR = armL.clone();
    armR.position.x = 0.28;
    g.add(armR);

    // Acessórios específicos por classe — em cima da cabeça
    if (cls === 'mage') {
      // Chapéu pontudo azul com banda dourada
      const hatBrim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.28, 0.05, 12),
        accentMat
      );
      hatBrim.position.y = 0.72;
      g.add(hatBrim);
      const hatCone = new THREE.Mesh(
        new THREE.ConeGeometry(0.22, 0.55, 12),
        robeMat
      );
      hatCone.position.y = 1.0;
      hatCone.castShadow = true;
      g.add(hatCone);
      // Bolinha dourada no topo
      const hatTip = new THREE.Mesh(
        new THREE.SphereGeometry(0.06, 8, 8),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, emissive: 0xFCD34D, emissiveIntensity: 0.6 })
      );
      hatTip.position.y = 1.3;
      g.add(hatTip);
    } else if (cls === 'warlock') {
      // Capuz roxo sobre a cabeça
      const hood = new THREE.Mesh(
        new THREE.ConeGeometry(0.28, 0.45, 8, 1, true),
        new THREE.MeshStandardMaterial({ color, roughness: 0.85, side: THREE.DoubleSide })
      );
      hood.position.y = 0.78;
      hood.castShadow = true;
      g.add(hood);
      // Sombra sob o capuz
      const shadow = new THREE.Mesh(
        new THREE.BoxGeometry(0.32, 0.18, 0.02),
        new THREE.MeshBasicMaterial({ color: 0x0a0a0a })
      );
      shadow.position.set(0, 0.5, 0.185);
      g.add(shadow);
    } else if (cls === 'druid') {
      // Capuz com folhas verdes
      const hood = new THREE.Mesh(
        new THREE.ConeGeometry(0.28, 0.4, 8, 1, true),
        new THREE.MeshStandardMaterial({ color, roughness: 0.9, side: THREE.DoubleSide })
      );
      hood.position.y = 0.76;
      g.add(hood);
      // Folhas decorativas
      for (let i = 0; i < 4; i++) {
        const ang = (i / 4) * Math.PI * 2;
        const leaf = new THREE.Mesh(
          new THREE.BoxGeometry(0.1, 0.04, 0.04),
          new THREE.MeshStandardMaterial({ color: 0x4ADE80, emissive: 0x16A34A, emissiveIntensity: 0.3 })
        );
        leaf.position.set(Math.cos(ang) * 0.2, 0.78, Math.sin(ang) * 0.2);
        leaf.rotation.z = ang;
        g.add(leaf);
      }
    } else if (cls === 'rogue') {
      // Capuz preto baixo cobrindo a cara
      const hood = new THREE.Mesh(
        new THREE.ConeGeometry(0.3, 0.5, 8, 1, true),
        new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.95, side: THREE.DoubleSide })
      );
      hood.position.y = 0.78;
      hood.castShadow = true;
      g.add(hood);
      // Sombra cobrindo a cara
      const shadow = new THREE.Mesh(
        new THREE.BoxGeometry(0.36, 0.36, 0.02),
        new THREE.MeshBasicMaterial({ color: 0x0a0a0a })
      );
      shadow.position.set(0, 0.5, 0.19);
      g.add(shadow);
    } else if (cls === 'warrior') {
      // Elmo de armadura
      const helm = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.18, 0.4),
        new THREE.MeshStandardMaterial({ color: 0x9CA3AF, metalness: 0.7, roughness: 0.4 })
      );
      helm.position.y = 0.78;
      helm.castShadow = true;
      g.add(helm);
      // Plume vermelha em cima
      const plume = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.22, 0.08),
        new THREE.MeshStandardMaterial({ color: 0xB91C1C, emissive: 0xB91C1C, emissiveIntensity: 0.3 })
      );
      plume.position.y = 0.99;
      g.add(plume);
    } else if (cls === 'engineer') {
      // Chapéu de tinker (aba + topo)
      const brim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.28, 0.28, 0.04, 10),
        new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.85 })
      );
      brim.position.y = 0.72;
      g.add(brim);
      const top = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.18, 0.16, 10),
        new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.85 })
      );
      top.position.y = 0.82;
      g.add(top);
      // Goggles (2 círculos pretos sobre os olhos)
      for (const dx of [-0.09, 0.09]) {
        const goggle = new THREE.Mesh(
          new THREE.CylinderGeometry(0.07, 0.07, 0.02, 12),
          new THREE.MeshStandardMaterial({
            color: 0x0a0a0a, metalness: 0.8, roughness: 0.3,
          })
        );
        goggle.rotation.x = Math.PI / 2;
        goggle.position.set(dx, 0.6, 0.19);
        g.add(goggle);
      }
    } else if (cls === 'priest') {
      // Capuz/véu branco
      const veil = new THREE.Mesh(
        new THREE.ConeGeometry(0.28, 0.42, 8, 1, true),
        new THREE.MeshStandardMaterial({ color: 0xE5E7EB, roughness: 0.95, side: THREE.DoubleSide })
      );
      veil.position.y = 0.78;
      g.add(veil);
      // Cruz no peito
      const crossV = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.16, 0.02),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, emissive: 0xFCD34D, emissiveIntensity: 0.35 })
      );
      crossV.position.set(0, 0.0, 0.185);
      g.add(crossV);
      const crossH = new THREE.Mesh(
        new THREE.BoxGeometry(0.12, 0.04, 0.02),
        crossV.material
      );
      crossH.position.set(0, 0.04, 0.185);
      g.add(crossH);
    } else if (cls === 'paladin') {
      // Elmo dourado com asa lateral
      const helm = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.22, 0.4),
        new THREE.MeshStandardMaterial({
          color: 0xD4AF37, metalness: 0.85, roughness: 0.25,
          emissive: 0x3a2a08, emissiveIntensity: 0.2,
        })
      );
      helm.position.y = 0.8;
      helm.castShadow = true;
      g.add(helm);
      // Asa lateral
      for (const dx of [-0.26, 0.26]) {
        const wing = new THREE.Mesh(
          new THREE.BoxGeometry(0.06, 0.18, 0.16),
          new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.7 })
        );
        wing.position.set(dx, 0.95, 0);
        wing.rotation.z = (dx < 0 ? -1 : 1) * Math.PI / 8;
        g.add(wing);
      }
    } else if (cls === 'scribe') {
      // Chapéu redondo de scribe + óculos
      const cap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.22, 0.22, 0.12, 10),
        new THREE.MeshStandardMaterial({ color: 0x78350F, roughness: 0.9 })
      );
      cap.position.y = 0.75;
      g.add(cap);
      // Pena na lateral (vertical fina)
      const feather = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.3, 0.04),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.8 })
      );
      feather.position.set(0.16, 0.95, 0);
      feather.rotation.z = -0.4;
      g.add(feather);
      // Óculos redondos
      for (const dx of [-0.09, 0.09]) {
        const lens = new THREE.Mesh(
          new THREE.TorusGeometry(0.05, 0.012, 6, 12),
          new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.8 })
        );
        lens.position.set(dx, 0.53, 0.2);
        g.add(lens);
      }
    } else if (cls === 'warchief') {
      // Ombreiras tribais grandes vermelhas
      for (const dx of [-0.32, 0.32]) {
        const pauldron = new THREE.Mesh(
          new THREE.BoxGeometry(0.32, 0.22, 0.38),
          new THREE.MeshStandardMaterial({
            color: 0x9F1239, metalness: 0.4, roughness: 0.6,
            emissive: 0x3d0808, emissiveIntensity: 0.25,
          })
        );
        pauldron.position.set(dx, 0.32, 0);
        pauldron.castShadow = true;
        g.add(pauldron);
        // Pico tribal em cima
        const spike = new THREE.Mesh(
          new THREE.ConeGeometry(0.06, 0.16, 6),
          new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.7 })
        );
        spike.position.set(dx, 0.5, 0);
        g.add(spike);
      }
      // Capacete tribal com chifres
      const helm = new THREE.Mesh(
        new THREE.BoxGeometry(0.38, 0.16, 0.38),
        new THREE.MeshStandardMaterial({ color: 0x4a2818, roughness: 0.9 })
      );
      helm.position.y = 0.76;
      g.add(helm);
      // 2 chifres
      for (const dx of [-0.18, 0.18]) {
        const horn = new THREE.Mesh(
          new THREE.ConeGeometry(0.05, 0.22, 6),
          new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.8 })
        );
        horn.position.set(dx, 0.92, 0);
        horn.rotation.z = (dx < 0 ? 1 : -1) * Math.PI / 4;
        g.add(horn);
      }
    } else if (cls === 'hunter') {
      // Capuz verde-floresta com penas
      const hood = new THREE.Mesh(
        new THREE.ConeGeometry(0.28, 0.42, 8, 1, true),
        new THREE.MeshStandardMaterial({ color: 0x15803D, roughness: 0.92, side: THREE.DoubleSide })
      );
      hood.position.y = 0.78;
      g.add(hood);
      // Pena lateral
      const feather = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, 0.25, 0.04),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, roughness: 0.7 })
      );
      feather.position.set(0.18, 0.92, 0.05);
      feather.rotation.z = -0.6;
      g.add(feather);
    } else if (cls === 'loremaster') {
      // Capuz com livro flutuante acima da cabeça
      const hood = new THREE.Mesh(
        new THREE.ConeGeometry(0.28, 0.4, 8, 1, true),
        new THREE.MeshStandardMaterial({ color: 0x92400E, roughness: 0.9, side: THREE.DoubleSide })
      );
      hood.position.y = 0.76;
      g.add(hood);
      // Livro flutuante
      const book = new THREE.Mesh(
        new THREE.BoxGeometry(0.2, 0.15, 0.04),
        new THREE.MeshStandardMaterial({
          color: 0x7c2d12, roughness: 0.8,
          emissive: 0xFCD34D, emissiveIntensity: 0.25,
        })
      );
      book.position.y = 1.15;
      book.rotation.x = -Math.PI / 6;
      g.add(book);
      // Óculos
      for (const dx of [-0.09, 0.09]) {
        const lens = new THREE.Mesh(
          new THREE.TorusGeometry(0.05, 0.012, 6, 12),
          new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.8 })
        );
        lens.position.set(dx, 0.53, 0.2);
        g.add(lens);
      }
    } else if (cls === 'quest_giver') {
      // Chapéu de feltro + sinal "!" flutuando acima
      const hat = new THREE.Mesh(
        new THREE.ConeGeometry(0.24, 0.32, 12),
        new THREE.MeshStandardMaterial({ color: 0xb45309, roughness: 0.85 })
      );
      hat.position.y = 0.86;
      g.add(hat);
      const brim = new THREE.Mesh(
        new THREE.CylinderGeometry(0.32, 0.32, 0.04, 12),
        new THREE.MeshStandardMaterial({ color: 0x78350F, roughness: 0.85 })
      );
      brim.position.y = 0.71;
      g.add(brim);
      // Ponto de exclamação amarelo flutuando acima (!) — usando 2 boxes
      const exclamBar = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.3, 0.08),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, emissive: 0xFBBF24, emissiveIntensity: 0.85,
        })
      );
      exclamBar.position.y = 1.4;
      g.add(exclamBar);
      const exclamDot = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.08, 0.08),
        exclamBar.material
      );
      exclamDot.position.y = 1.18;
      g.add(exclamDot);
    } else if (cls === 'innkeeper') {
      // Chapéu de cozinheiro/avental + avental claro no peito
      const apron = new THREE.Mesh(
        new THREE.PlaneGeometry(0.4, 0.55),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, side: THREE.DoubleSide, roughness: 0.85 })
      );
      apron.position.set(0, 0.0, 0.21);
      g.add(apron);
      // Boné simples (sem ponta)
      const cap = new THREE.Mesh(
        new THREE.CylinderGeometry(0.21, 0.21, 0.15, 10),
        new THREE.MeshStandardMaterial({ color: 0x78350F, roughness: 0.9 })
      );
      cap.position.y = 0.76;
      g.add(cap);
    }

    return Object.assign(g, { head, armL, armR });
  }

  // Cria objeto característico em cima da mesa por classe
  function makeClassProp(cls, color, accent) {
    if (cls === 'mage') {
      // Bola de cristal sobre base dourada
      const g = new THREE.Group();
      const base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.14, 0.05, 12),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.7, roughness: 0.3 })
      );
      g.add(base);
      const orb = new THREE.Mesh(
        new THREE.SphereGeometry(0.13, 16, 16),
        new THREE.MeshStandardMaterial({
          color: 0x60A5FA, transparent: true, opacity: 0.8,
          emissive: 0x2563EB, emissiveIntensity: 0.6,
        })
      );
      orb.position.y = 0.14;
      g.add(orb);
      return Object.assign(g, { orb });
    }
    if (cls === 'warlock') {
      // Caldeirão fumegante
      const g = new THREE.Group();
      const pot = new THREE.Mesh(
        new THREE.CylinderGeometry(0.16, 0.12, 0.18, 12),
        new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.95 })
      );
      g.add(pot);
      const liquid = new THREE.Mesh(
        new THREE.CylinderGeometry(0.13, 0.13, 0.01, 12),
        new THREE.MeshStandardMaterial({
          color: 0x7C3AED, emissive: 0xA78BFA, emissiveIntensity: 0.6,
        })
      );
      liquid.position.y = 0.085;
      g.add(liquid);
      return Object.assign(g, { liquid });
    }
    if (cls === 'druid') {
      // Cristal verde brotando
      const crystal = new THREE.Mesh(
        new THREE.OctahedronGeometry(0.16),
        new THREE.MeshStandardMaterial({
          color: 0x4ADE80, emissive: 0x16A34A, emissiveIntensity: 0.5,
          transparent: true, opacity: 0.85,
        })
      );
      crystal.position.y = 0.16;
      return Object.assign(new THREE.Group().add(crystal), { orb: crystal });
    }
    if (cls === 'rogue') {
      // Adaga + moedas
      const g = new THREE.Group();
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.02, 0.3),
        new THREE.MeshStandardMaterial({ color: 0xE5E7EB, metalness: 0.9, roughness: 0.2 })
      );
      blade.position.y = 0.06;
      g.add(blade);
      const grip = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, 0.05, 0.1),
        new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.9 })
      );
      grip.position.set(0, 0.06, -0.18);
      g.add(grip);
      // Pilha de moedas
      for (let i = 0; i < 3; i++) {
        const coin = new THREE.Mesh(
          new THREE.CylinderGeometry(0.06, 0.06, 0.015, 12),
          new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.8, roughness: 0.3 })
        );
        coin.position.set(0.22, 0.02 + i * 0.018, 0.08);
        g.add(coin);
      }
      return g;
    }
    if (cls === 'warrior') {
      // Espada + escudo
      const g = new THREE.Group();
      const sword = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.6, 0.04),
        new THREE.MeshStandardMaterial({ color: 0xE5E7EB, metalness: 0.85, roughness: 0.25 })
      );
      sword.position.set(-0.1, 0.32, 0);
      sword.rotation.z = Math.PI / 6;
      g.add(sword);
      const cross = new THREE.Mesh(
        new THREE.BoxGeometry(0.2, 0.04, 0.04),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.6 })
      );
      cross.position.set(-0.1, 0.05, 0);
      cross.rotation.z = Math.PI / 6;
      g.add(cross);
      // Escudo redondo
      const shield = new THREE.Mesh(
        new THREE.CylinderGeometry(0.18, 0.18, 0.03, 16),
        new THREE.MeshStandardMaterial({ color: 0xB91C1C, metalness: 0.4, roughness: 0.6 })
      );
      shield.rotation.x = Math.PI / 2;
      shield.position.set(0.18, 0.15, 0);
      g.add(shield);
      return g;
    }
    if (cls === 'engineer') {
      // Chave inglesa de bronze + engrenagem dourada
      const g = new THREE.Group();
      const wrench = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.04, 0.06),
        new THREE.MeshStandardMaterial({ color: 0xA16207, metalness: 0.6, roughness: 0.4 })
      );
      wrench.position.y = 0.04;
      g.add(wrench);
      // Engrenagem (cilindro com várias presas como BoxGeom radiais)
      const gear = new THREE.Mesh(
        new THREE.CylinderGeometry(0.13, 0.13, 0.04, 8),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, metalness: 0.85, roughness: 0.3,
          emissive: 0xa16207, emissiveIntensity: 0.4,
        })
      );
      gear.position.set(0.18, 0.06, 0.08);
      g.add(gear);
      return Object.assign(g, { orb: gear });
    }
    if (cls === 'priest') {
      // Cálice dourado com líquido brilhante
      const g = new THREE.Group();
      const stem = new THREE.Mesh(
        new THREE.CylinderGeometry(0.04, 0.06, 0.18, 8),
        new THREE.MeshStandardMaterial({ color: 0xD4AF37, metalness: 0.8 })
      );
      stem.position.y = 0.09;
      g.add(stem);
      const cup = new THREE.Mesh(
        new THREE.CylinderGeometry(0.1, 0.07, 0.12, 10),
        new THREE.MeshStandardMaterial({ color: 0xFCD34D, metalness: 0.85, roughness: 0.25 })
      );
      cup.position.y = 0.24;
      g.add(cup);
      // Líquido brilhante
      const liquid = new THREE.Mesh(
        new THREE.CylinderGeometry(0.08, 0.08, 0.01, 10),
        new THREE.MeshStandardMaterial({
          color: 0xE5E7EB, emissive: 0xFCD34D, emissiveIntensity: 0.7,
        })
      );
      liquid.position.y = 0.29;
      g.add(liquid);
      return Object.assign(g, { liquid });
    }
    if (cls === 'paladin') {
      // Martelo de guerra dourado
      const g = new THREE.Group();
      const haft = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, 0.5, 0.04),
        new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.85 })
      );
      haft.position.y = 0.25;
      g.add(haft);
      const head = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.16, 0.18),
        new THREE.MeshStandardMaterial({
          color: 0xD4AF37, metalness: 0.85, roughness: 0.25,
          emissive: 0x3a2a08, emissiveIntensity: 0.3,
        })
      );
      head.position.y = 0.5;
      g.add(head);
      return Object.assign(g, { orb: head });
    }
    if (cls === 'scribe') {
      // Pergaminho aberto + tinteiro
      const g = new THREE.Group();
      const scroll = new THREE.Mesh(
        new THREE.PlaneGeometry(0.35, 0.22),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.85, side: THREE.DoubleSide })
      );
      scroll.rotation.x = -Math.PI / 2;
      scroll.position.y = 0.02;
      g.add(scroll);
      // Bordas enroladas
      for (const dz of [-0.12, 0.12]) {
        const roll = new THREE.Mesh(
          new THREE.CylinderGeometry(0.03, 0.03, 0.36, 8),
          new THREE.MeshStandardMaterial({ color: 0xb45309, roughness: 0.8 })
        );
        roll.rotation.z = Math.PI / 2;
        roll.position.set(0, 0.02, dz);
        g.add(roll);
      }
      // Tinteiro
      const ink = new THREE.Mesh(
        new THREE.CylinderGeometry(0.05, 0.05, 0.08, 8),
        new THREE.MeshStandardMaterial({ color: 0x18181b, roughness: 0.9 })
      );
      ink.position.set(0.2, 0.04, 0);
      g.add(ink);
      return g;
    }
    if (cls === 'warchief') {
      // Machado tribal grande
      const g = new THREE.Group();
      const haft = new THREE.Mesh(
        new THREE.BoxGeometry(0.05, 0.55, 0.05),
        new THREE.MeshStandardMaterial({ color: 0x4a2818, roughness: 0.9 })
      );
      haft.position.y = 0.28;
      g.add(haft);
      // Lâmina dupla
      const blade = new THREE.Mesh(
        new THREE.BoxGeometry(0.3, 0.22, 0.05),
        new THREE.MeshStandardMaterial({
          color: 0xC0C0C0, metalness: 0.8, roughness: 0.3,
          emissive: 0x9F1239, emissiveIntensity: 0.15,
        })
      );
      blade.position.y = 0.5;
      g.add(blade);
      return Object.assign(g, { orb: blade });
    }
    if (cls === 'hunter') {
      // Arco + flecha
      const g = new THREE.Group();
      const bow = new THREE.Mesh(
        new THREE.TorusGeometry(0.18, 0.015, 6, 12, Math.PI),
        new THREE.MeshStandardMaterial({ color: 0x78350F, roughness: 0.85 })
      );
      bow.rotation.z = Math.PI / 2;
      bow.position.y = 0.18;
      g.add(bow);
      // Corda
      const string = new THREE.Mesh(
        new THREE.BoxGeometry(0.005, 0.36, 0.005),
        new THREE.MeshStandardMaterial({ color: 0xE5E7EB })
      );
      string.position.set(-0.18, 0.18, 0);
      g.add(string);
      // Flecha
      const arrow = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.02, 0.02),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.8 })
      );
      arrow.position.set(0, 0.05, 0);
      g.add(arrow);
      const tip = new THREE.Mesh(
        new THREE.ConeGeometry(0.025, 0.06, 4),
        new THREE.MeshStandardMaterial({ color: 0x9CA3AF, metalness: 0.8 })
      );
      tip.rotation.z = -Math.PI / 2;
      tip.position.set(0.22, 0.05, 0);
      g.add(tip);
      return g;
    }
    if (cls === 'loremaster') {
      // Livro grande aberto com brilho âmbar
      const g = new THREE.Group();
      const left = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.04, 0.22),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.85 })
      );
      left.position.set(-0.085, 0.04, 0);
      left.rotation.z = 0.1;
      g.add(left);
      const right = left.clone();
      right.position.set(0.085, 0.04, 0);
      right.rotation.z = -0.1;
      g.add(right);
      // Capa
      const cover = new THREE.Mesh(
        new THREE.BoxGeometry(0.36, 0.02, 0.24),
        new THREE.MeshStandardMaterial({ color: 0x7c2d12, roughness: 0.85 })
      );
      cover.position.y = 0.01;
      g.add(cover);
      // Brilho âmbar emanando do livro
      const glow = new THREE.Mesh(
        new THREE.SphereGeometry(0.06, 8, 8),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, emissive: 0xFBBF24, emissiveIntensity: 0.8,
          transparent: true, opacity: 0.85,
        })
      );
      glow.position.y = 0.16;
      g.add(glow);
      return Object.assign(g, { orb: glow });
    }
    if (cls === 'quest_giver') {
      // Pergaminho enrolado com selo dourado
      const g = new THREE.Group();
      const scroll = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.32, 8),
        new THREE.MeshStandardMaterial({ color: 0xE8D5A8, roughness: 0.85 })
      );
      scroll.rotation.z = Math.PI / 2;
      scroll.position.y = 0.06;
      g.add(scroll);
      // Selo dourado
      const seal = new THREE.Mesh(
        new THREE.CylinderGeometry(0.04, 0.04, 0.04, 8),
        new THREE.MeshStandardMaterial({
          color: 0xFCD34D, metalness: 0.7,
          emissive: 0xFBBF24, emissiveIntensity: 0.5,
        })
      );
      seal.rotation.z = Math.PI / 2;
      seal.position.set(0, 0.06, 0.06);
      g.add(seal);
      return Object.assign(g, { orb: seal });
    }
    if (cls === 'innkeeper') {
      // Jarra de cerveja + 2 canecas
      const g = new THREE.Group();
      const jug = new THREE.Mesh(
        new THREE.CylinderGeometry(0.1, 0.12, 0.22, 10),
        new THREE.MeshStandardMaterial({ color: 0x5a3014, roughness: 0.9 })
      );
      jug.position.y = 0.11;
      g.add(jug);
      // Espuma
      const foam = new THREE.Mesh(
        new THREE.SphereGeometry(0.1, 8, 6),
        new THREE.MeshStandardMaterial({
          color: 0xfff8e1, roughness: 0.7,
          emissive: 0xfff8e1, emissiveIntensity: 0.15,
        })
      );
      foam.scale.y = 0.5;
      foam.position.y = 0.25;
      g.add(foam);
      // Caneca pequena ao lado
      const mug = new THREE.Mesh(
        new THREE.CylinderGeometry(0.06, 0.06, 0.1, 8),
        new THREE.MeshStandardMaterial({ color: 0x78350F, roughness: 0.88 })
      );
      mug.position.set(0.22, 0.05, 0.05);
      g.add(mug);
      return g;
    }
    return null;
  }

  // Cria nameplate de agente — width adaptativo ao texto (sem espaço sobrando).
  // Versão compacta + dinâmica.
  function makeAgentNameplate(name, classLabel, color) {
    // 1) Mede largura do texto pra ajustar o canvas dinamicamente
    const measureCtx = document.createElement('canvas').getContext('2d');
    measureCtx.font = '700 17px "Cinzel", serif';
    const nameW = measureCtx.measureText(name).width;
    measureCtx.font = 'italic 11px "MedievalSharp", cursive';
    const classW = measureCtx.measureText(`~ ${classLabel} ~`).width;
    const textW = Math.max(nameW, classW);
    // 2) Width total = bolinha esquerda (32px) + texto + margem direita (14px)
    const totalW = Math.max(140, Math.ceil(textW + 32 + 14));

    const c = document.createElement('canvas');
    c.width = totalW;
    c.height = 72;
    const ctx = c.getContext('2d');
    // Fundo madeira/pergaminho — pill cobre todo o canvas
    ctx.fillStyle = 'rgba(35, 22, 13, 0.92)';
    ctx.beginPath();
    ctx.roundRect(0, 16, totalW, 40, 8);
    ctx.fill();
    // Borda dourada
    ctx.strokeStyle = '#D4AF37';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.roundRect(0, 16, totalW, 40, 8);
    ctx.stroke();
    // Bolinha colorida da classe (esquerda)
    ctx.fillStyle = '#' + color.toString(16).padStart(6, '0');
    ctx.beginPath();
    ctx.arc(18, 36, 8, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#FCD34D';
    ctx.lineWidth = 1.2;
    ctx.stroke();
    // Texto nome (negrito)
    ctx.font = '700 17px "Cinzel", serif';
    ctx.fillStyle = '#FCD34D';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillText(name, 32, 32);
    // Texto classe (itálico, abaixo)
    ctx.font = 'italic 11px "MedievalSharp", cursive';
    ctx.fillStyle = '#E8D5A8';
    ctx.fillText(`~ ${classLabel} ~`, 32, 48);

    const tex = new THREE.CanvasTexture(c);
    tex.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    // Scale proporcional ao aspect ratio — mantém altura constante (0.5m), largura adapta
    const SCALE_Y = 0.5;
    const aspect = totalW / 72;
    sprite.scale.set(SCALE_Y * aspect, SCALE_Y, 1);
    return { sprite, canvas: c, ctx, tex };
  }

  // ─── Guildmaster (Supervisor) — personagem voxel-fantasy ──────
  function makeGuildmaster() {
    const g = new THREE.Group();

    // Corpo / armadura dourada
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xD4AF37,
      roughness: 0.35,
      metalness: 0.75,
      emissive: 0x3a2a08,
      emissiveIntensity: 0.2,
    });
    const body = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.7, 0.4), bodyMat);
    body.position.y = 0.0;
    body.castShadow = true;
    g.add(body);

    // Detalhe peitoral — placa central avermelhada
    const chest = new THREE.Mesh(
      new THREE.BoxGeometry(0.25, 0.4, 0.02),
      new THREE.MeshStandardMaterial({
        color: 0xB91C1C,
        roughness: 0.6,
        emissive: 0x3d0808,
        emissiveIntensity: 0.25,
      })
    );
    chest.position.set(0, 0.05, 0.21);
    g.add(chest);

    // Ombreiras douradas
    for (const dx of [-0.32, 0.32]) {
      const shoulder = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.18, 0.32),
        bodyMat
      );
      shoulder.position.set(dx, 0.28, 0);
      shoulder.castShadow = true;
      g.add(shoulder);
    }

    // Manto vermelho atrás
    const cape = new THREE.Mesh(
      new THREE.PlaneGeometry(0.85, 1.5),
      new THREE.MeshStandardMaterial({
        color: 0xB91C1C,
        side: THREE.DoubleSide,
        roughness: 0.85,
        emissive: 0x3d0808,
        emissiveIntensity: 0.1,
      })
    );
    cape.position.set(0, -0.05, -0.22);
    cape.castShadow = true;
    g.add(cape);

    // Cabeça
    const skinMat = new THREE.MeshStandardMaterial({
      color: 0xF5D5B8,
      roughness: 0.7,
    });
    const head = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.42, 0.42), skinMat);
    head.position.y = 0.65;
    head.castShadow = true;
    g.add(head);

    // Olhos
    for (const dx of [-0.09, 0.09]) {
      const eye = new THREE.Mesh(
        new THREE.BoxGeometry(0.06, 0.06, 0.02),
        new THREE.MeshBasicMaterial({ color: 0x0a0a0a })
      );
      eye.position.set(dx, 0.68, 0.215);
      g.add(eye);
    }

    // Barba branca/grisalha (rei velho)
    const beard = new THREE.Mesh(
      new THREE.BoxGeometry(0.34, 0.22, 0.08),
      new THREE.MeshStandardMaterial({ color: 0xe5e5e0, roughness: 0.95 })
    );
    beard.position.set(0, 0.48, 0.21);
    g.add(beard);

    // Bigode
    const mustache = new THREE.Mesh(
      new THREE.BoxGeometry(0.28, 0.05, 0.05),
      new THREE.MeshStandardMaterial({ color: 0xe5e5e0, roughness: 0.95 })
    );
    mustache.position.set(0, 0.62, 0.225);
    g.add(mustache);

    // Coroa dourada
    const crownMat = new THREE.MeshStandardMaterial({
      color: 0xFCD34D,
      roughness: 0.3,
      metalness: 0.85,
      emissive: 0x5a4408,
      emissiveIntensity: 0.4,
    });
    const crownBase = new THREE.Mesh(
      new THREE.CylinderGeometry(0.22, 0.22, 0.1, 8),
      crownMat
    );
    crownBase.position.y = 0.92;
    crownBase.castShadow = true;
    g.add(crownBase);
    // Pontas da coroa
    for (let i = 0; i < 5; i++) {
      const angle = (i / 5) * Math.PI * 2;
      const spike = new THREE.Mesh(
        new THREE.ConeGeometry(0.04, 0.18, 5),
        crownMat
      );
      spike.position.set(
        Math.cos(angle) * 0.18,
        1.05,
        Math.sin(angle) * 0.18
      );
      spike.castShadow = true;
      g.add(spike);
    }
    // Joia central vermelha
    const gem = new THREE.Mesh(
      new THREE.OctahedronGeometry(0.06),
      new THREE.MeshStandardMaterial({
        color: 0xB91C1C,
        emissive: 0xff1493,
        emissiveIntensity: 0.6,
        metalness: 0.4,
        roughness: 0.2,
      })
    );
    gem.position.set(0, 0.97, 0.21);
    g.add(gem);

    // Mãos / manoplas douradas sobre os braços do trono
    for (const dx of [-0.42, 0.42]) {
      const glove = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 0.18, 0.18),
        crownMat
      );
      glove.position.set(dx, 0.05, 0.05);
      glove.castShadow = true;
      g.add(glove);
    }

    return Object.assign(g, { head, crownBase, gem });
  }

  function makePlaceholderTexture() {
    const c = document.createElement('canvas');
    c.width = 1024; c.height = 256;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, 1024, 256);
    // Sombra suave
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillRect(0, 0, 1024, 256);
    // Texto
    ctx.font = '900 90px "Cinzel", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#FCD34D';
    ctx.shadowColor = '#D4AF37';
    ctx.shadowBlur = 18;
    ctx.fillText('DOMA Guild Hall', 512, 100);
    ctx.shadowBlur = 0;
    ctx.font = 'italic 36px "MedievalSharp", cursive';
    ctx.fillStyle = '#E8D5A8';
    ctx.fillText('em construção pelos arquitetos', 512, 180);
    return new THREE.CanvasTexture(c);
  }

  // ─── Boot ──────────────────────────────────────────────────────
  animate();
  connectWS();
  console.log('[WC] DOMA Guild Hall v2 — Fase 1 booted ⚒');
})();
