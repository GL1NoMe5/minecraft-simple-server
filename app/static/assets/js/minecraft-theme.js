/**
 * MSS (Minecraft Simple Server) — Authentic Visual FX & Ambient Engine
 * --------------------------------------------------------------------
 * Permanently enforces the Minecraft visual theme (.mc-theme) and manages:
 *  - Multi-layer ambient background canvas (#mcParticles):
 *      1. Biome spores & firefly dust (crisp pixel squares)
 *      2. Floating XP Orbs (pulsing green-gold experience orbs with soft halo)
 *      3. Enchanting Table runes (faint rising Galactic-style glyphs)
 *      4. Subtle mouse parallax depth
 *  - Title-screen style clickable yellow splash text (#mcSplash) in EN / RU
 *  - Visual FX toggle (#btnFxToggle) persisted in localStorage
 */

window.MinecraftTheme = (() => {
  const STORAGE_FX_KEY = 'mc_fx_enabled';

  // Clean up any legacy theme-disable key so Minecraft style is always active
  try {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('mc_theme_enabled');
    }
  } catch (e) {}

  let fxEnabled = (typeof localStorage !== 'undefined' && localStorage.getItem(STORAGE_FX_KEY) !== null)
    ? localStorage.getItem(STORAGE_FX_KEY) !== 'false'
    : true;

  // Particle System State
  let canvas = null;
  let ctx = null;
  let animId = null;
  let particles = [];
  let width = 0;
  let height = 0;
  let dpr = 1;
  let isRunning = false;

  // Subtle mouse parallax state
  let targetParallaxX = 0;
  let targetParallaxY = 0;
  let currentParallaxX = 0;
  let currentParallaxY = 0;

  const SPORE_COUNT = 34;
  const XP_ORB_COUNT = 5;
  const RUNE_COUNT = 7;
  const RUNE_GLYPHS = ['ᔑ', '🄱', '🄲', '🄳', '🄴', '🄵', 'ᚷ', '⚸', '⊹', '◈', '❖'];

  const SPLASH_TEXTS = {
    en: [
      '100% lag-free!',
      'Never dig straight down!',
      'Redstone inside!',
      'Creeper? Aww man!',
      'Diamonds at Y = -58!',
      'Freshly brewed potion!',
      'Eat golden apples!',
      'Java Edition vibe!',
      'RTX On!',
      'Feed the axolotl!',
      'Creepers fear cats!',
      'Sleep before phantoms come!',
      'Fortune III enchanted!',
      'Shulkers full of shulkers!',
      'Minecraft is life!',
      'Forge & Fabric ready!',
      'Furnaces glowing warm!',
      'Silk Touch approved!',
      'Watch out in the Nether!',
      'Cozy crafting server!',
      'Campfire warms the base!',
      'Torches in the offhand!',
      'Elytra & firework rockets!',
      'Mending & Unbreaking III!',
      'MSS — Simple & Fast!'
    ],
    ru: [
      '100% без лагов!',
      'Не копай под себя!',
      'Redstone inside!',
      'Creeper? Aww man!',
      'Алмазы на Y = -58!',
      'Свежесваренное зелье!',
      'Кушай золотые яблоки!',
      'Java Edition vibe!',
      'RTX On!',
      'Покорми аксолотля!',
      'Крипер боится котиков!',
      'Спи, пока не пришли фантомы!',
      'Зачаровано на Удачу III!',
      'Шалкер полон шалкеров!',
      'Майнкрафт — это жизнь!',
      'Forge & Fabric ready!',
      'Печки греют, редстоун тикает!',
      'Шёлковое касание!',
      'Будь осторожен в Незере!',
      'Уютный крафтовый сервер!',
      'Костёр согревает базу!',
      'Держи факелы в левой руке!',
      'Элитры заправлены порохом!',
      'Починка и Прочность III!',
      'MSS — просто и быстро!'
    ]
  };

  let currentSplashIdx = Math.floor(Math.random() * SPLASH_TEXTS.en.length);

  function getLang() {
    if (typeof window.getCurrentLang === 'function') {
      return window.getCurrentLang();
    }
    try {
      return localStorage.getItem('mss_lang') || 'en';
    } catch (e) {
      return 'en';
    }
  }

  function playUiSound(soundName) {
    if (window.MinecraftAudio) {
      if (soundName === 'click' && typeof window.MinecraftAudio.playClick === 'function') {
        window.MinecraftAudio.playClick();
      } else if (soundName === 'toggle' && typeof window.MinecraftAudio.playToggle === 'function') {
        window.MinecraftAudio.playToggle();
      } else if (soundName === 'enchant' && typeof window.MinecraftAudio.playGamemodeChange === 'function') {
        window.MinecraftAudio.playGamemodeChange();
      }
    }
  }

  // ---------------- PARTICLE SIMULATION ----------------
  function initCanvas() {
    canvas = document.getElementById('mcParticles');
    if (!canvas) {
      canvas = document.createElement('canvas');
      canvas.id = 'mcParticles';
      document.body.prepend(canvas);
    }
    ctx = canvas.getContext('2d', { alpha: true });
    resizeCanvas();
    window.addEventListener('resize', debounce(resizeCanvas, 150));

    window.addEventListener('mousemove', (e) => {
      if (!fxEnabled || !width || !height) return;
      const nx = (e.clientX / width) - 0.5;
      const ny = (e.clientY / height) - 0.5;
      targetParallaxX = -nx * 16;
      targetParallaxY = -ny * 12;
    }, { passive: true });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        stopParticles();
      } else if (fxEnabled) {
        startParticles();
      }
    });

    createParticles();
    if (fxEnabled) {
      startParticles();
    }
  }

  function debounce(fn, ms) {
    let timer = null;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(null, args), ms);
    };
  }

  function resizeCanvas() {
    if (!canvas) return;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    if (ctx) {
      ctx.imageSmoothingEnabled = false;
    }
  }

  function createParticles() {
    particles = [];
    const sporePalettes = [
      { r: 120, g: 235, b: 95 },   // Lush cave spore green
      { r: 255, g: 210, b: 75 },   // Torch/campfire gold spark
      { r: 195, g: 140, b: 255 },  // Amethyst crystal shimmer
      { r: 85,  g: 225, b: 245 },  // Diamond/sculk cyan glint
      { r: 240, g: 240, b: 255 }   // Cavern dust speck
    ];

    // 1. Ambient spores & dust
    for (let i = 0; i < SPORE_COUNT; i++) {
      const palette = sporePalettes[Math.floor(Math.random() * sporePalettes.length)];
      particles.push({
        kind: 'spore',
        x: Math.random() * width,
        y: Math.random() * height,
        size: Math.random() < 0.35 ? 3 : (Math.random() < 0.65 ? 2 : 4),
        vx: (Math.random() - 0.5) * 0.3,
        vy: -0.14 - Math.random() * 0.3,
        alpha: Math.random() * 0.5 + 0.25,
        phase: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.014 + Math.random() * 0.018,
        depth: 0.4 + Math.random() * 0.6,
        color: palette
      });
    }

    // 2. Floating XP Orbs (pulse between lime and gold)
    for (let i = 0; i < XP_ORB_COUNT; i++) {
      particles.push({
        kind: 'xp',
        x: Math.random() * width,
        y: Math.random() * height,
        size: 5,
        vx: (Math.random() - 0.5) * 0.22,
        vy: -0.10 - Math.random() * 0.18,
        alpha: 0.55 + Math.random() * 0.25,
        phase: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.02 + Math.random() * 0.015,
        depth: 0.75 + Math.random() * 0.35
      });
    }

    // 3. Enchanting Table Runes (subtle rising glyphs)
    for (let i = 0; i < RUNE_COUNT; i++) {
      particles.push({
        kind: 'rune',
        glyph: RUNE_GLYPHS[i % RUNE_GLYPHS.length],
        x: Math.random() * width,
        y: Math.random() * height,
        size: 11 + Math.floor(Math.random() * 3),
        vx: (Math.random() - 0.5) * 0.15,
        vy: -0.18 - Math.random() * 0.22,
        alpha: 0.18 + Math.random() * 0.14,
        phase: Math.random() * Math.PI * 2,
        wobbleSpeed: 0.012 + Math.random() * 0.012,
        depth: 0.3 + Math.random() * 0.4
      });
    }
  }

  function renderParticles() {
    if (!ctx || !fxEnabled) {
      isRunning = false;
      return;
    }

    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    currentParallaxX += (targetParallaxX - currentParallaxX) * 0.04;
    currentParallaxY += (targetParallaxY - currentParallaxY) * 0.04;

    const isDark = document.documentElement.classList.contains('dark-style');

    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];

      p.phase += p.wobbleSpeed;
      p.x += p.vx + Math.sin(p.phase) * 0.22;
      p.y += p.vy;

      if (p.y < -16) {
        p.y = height + 16;
        p.x = Math.random() * width;
      }
      if (p.x < -16) p.x = width + 16;
      if (p.x > width + 16) p.x = -16;

      const drawX = Math.round(p.x + currentParallaxX * p.depth);
      const drawY = Math.round(p.y + currentParallaxY * p.depth);
      const breath = 0.5 + 0.5 * Math.sin(p.phase * 1.4);

      if (p.kind === 'spore') {
        const curAlpha = p.alpha * breath * (isDark ? 0.82 : 0.72);
        ctx.fillStyle = `rgba(${p.color.r}, ${p.color.g}, ${p.color.b}, ${curAlpha.toFixed(2)})`;
        ctx.fillRect(drawX, drawY, p.size, p.size);
      } else if (p.kind === 'xp') {
        // Authentic Minecraft XP Orb: shifts smoothly between lime (#7fe023) and yellow-gold (#ffd83d)
        const mix = 0.5 + 0.5 * Math.sin(p.phase * 2.2);
        const r = Math.round(127 + (255 - 127) * mix);
        const g = Math.round(224 + (216 - 224) * mix);
        const b = Math.round(35 + (61 - 35) * mix);
        const orbAlpha = p.alpha * (0.65 + 0.35 * breath) * (isDark ? 0.85 : 0.75);

        // Soft outer pixel halo
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${(orbAlpha * 0.25).toFixed(2)})`;
        ctx.fillRect(drawX - 2, drawY - 2, p.size + 4, p.size + 4);

        // Core pixel orb
        ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${orbAlpha.toFixed(2)})`;
        ctx.fillRect(drawX, drawY, p.size, p.size);

        // Bright 2x2 center highlight
        ctx.fillStyle = `rgba(255, 255, 220, ${(orbAlpha * 0.9).toFixed(2)})`;
        ctx.fillRect(drawX + 1, drawY + 1, 2, 2);
      } else if (p.kind === 'rune') {
        const runeAlpha = p.alpha * breath * (isDark ? 0.9 : 0.75);
        ctx.font = `${p.size}px "Pixelify Sans", monospace`;
        ctx.fillStyle = isDark
          ? `rgba(205, 165, 255, ${runeAlpha.toFixed(2)})`
          : `rgba(255, 235, 160, ${runeAlpha.toFixed(2)})`;
        ctx.fillText(p.glyph, drawX, drawY);
      }
    }

    ctx.restore();
    animId = requestAnimationFrame(renderParticles);
  }

  function startParticles() {
    if (isRunning || !fxEnabled) return;
    isRunning = true;
    animId = requestAnimationFrame(renderParticles);
  }

  function stopParticles() {
    isRunning = false;
    if (animId) {
      cancelAnimationFrame(animId);
      animId = null;
    }
    if (ctx) {
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, width, height);
      ctx.restore();
    }
  }

  // ---------------- SPLASH TEXT ----------------
  function initSplash() {
    const brandContainer = document.querySelector('.app-brand');
    if (!brandContainer) return;

    let splashEl = document.getElementById('mcSplash');
    if (!splashEl) {
      splashEl = document.createElement('span');
      splashEl.id = 'mcSplash';
      splashEl.className = 'mc-splash';
      brandContainer.appendChild(splashEl);
    }

    if (!splashEl.dataset.boundClick) {
      splashEl.dataset.boundClick = '1';
      splashEl.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        nextSplash();
      });
    }

    updateSplashText();
  }

  function nextSplash() {
    const list = SPLASH_TEXTS[getLang()] || SPLASH_TEXTS.en;
    currentSplashIdx = (currentSplashIdx + 1 + Math.floor(Math.random() * (list.length - 1))) % list.length;
    updateSplashText();
    playUiSound('click');
  }

  function updateSplashText() {
    const splashEl = document.getElementById('mcSplash');
    if (!splashEl) return;
    const lang = getLang();
    const list = SPLASH_TEXTS[lang] || SPLASH_TEXTS.en;
    splashEl.textContent = list[currentSplashIdx % list.length];
    splashEl.title = lang === 'ru'
      ? 'Нажми, чтобы сменить сплэш!'
      : 'Click to roll a new splash!';
    splashEl.style.animation = 'none';
    void splashEl.offsetHeight;
    splashEl.style.animation = '';
  }

  // ---------------- UI & FX TOGGLE ----------------
  function applyClasses() {
    const html = document.documentElement;
    // Always enforce Minecraft theme
    html.classList.add('mc-theme');

    if (fxEnabled) {
      html.classList.add('mc-fx');
    } else {
      html.classList.remove('mc-fx');
    }

    updateNavbarButtons();
  }

  function updateNavbarButtons() {
    const fxBtn = document.getElementById('btnFxToggle');
    const fxIcon = document.getElementById('fxToggleIcon');
    const fxText = document.getElementById('fxToggleText');
    const lang = getLang();

    if (fxBtn) {
      if (fxEnabled) {
        fxBtn.classList.remove('btn-outline-secondary', 'mc-fx-off');
        fxBtn.classList.add('btn-outline-primary');
        fxBtn.setAttribute(
          'title',
          lang === 'ru'
            ? 'Визуальные эффекты Minecraft (частицы, сферы опыта, свечение) включены'
            : 'Minecraft visual FX (particles, XP orbs, glint) enabled'
        );
      } else {
        fxBtn.classList.remove('btn-outline-primary');
        fxBtn.classList.add('btn-outline-secondary', 'mc-fx-off');
        fxBtn.setAttribute(
          'title',
          lang === 'ru'
            ? 'Визуальные эффекты выключены'
            : 'Minecraft visual FX disabled'
        );
      }
    }
    if (fxIcon) {
      fxIcon.className = fxEnabled ? 'bx bxs-magic-wand text-warning' : 'bx bxs-magic-wand';
    }
    if (fxText) {
      if (lang === 'ru') {
        fxText.textContent = fxEnabled ? 'FX: Вкл' : 'FX: Выкл';
      } else {
        fxText.textContent = fxEnabled ? 'FX: ON' : 'FX: OFF';
      }
    }
  }

  function toggleFx() {
    fxEnabled = !fxEnabled;
    try {
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem(STORAGE_FX_KEY, fxEnabled ? 'true' : 'false');
      }
    } catch (e) {}
    applyClasses();

    if (fxEnabled) {
      startParticles();
      playUiSound('enchant');
    } else {
      stopParticles();
      playUiSound('toggle');
    }
  }

  function refreshLanguage() {
    updateSplashText();
    updateNavbarButtons();
  }

  // ---------------- INITIALIZATION ----------------
  function init() {
    applyClasses();
    initCanvas();
    initSplash();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 0);
  }

  return {
    toggleFx,
    nextSplash,
    refreshLanguage,
    isFxEnabled: () => fxEnabled
  };
})();
