let appConfig = null;
let autoScroll = true;
let serverPollInterval = null;
let ws = null;
let isServerRunning = false;
let cachedPresets = {};
let wsReconnectTimeout = null;
let pingInterval = null;
let propertiesModalInstance = null;
let playerInspectModalInstance = null;
let currentInspectPlayer = null;
let currentTab = 'all';
let lastPlayersPollTime = 0;

// ---------------- MINECRAFT WEB AUDIO ENGINE ----------------
const MinecraftAudio = (() => {
  let audioCtx = null;
  let isSoundEnabled = (typeof localStorage !== 'undefined' && localStorage.getItem) ? (localStorage.getItem('mc_sound_enabled') !== 'false') : true;
  const bufferCache = new Map();
  const loadingPromises = new Map();

  // Authentic Minecraft sound asset paths (OGG downloaded from official Mojang CDN)
  const SOUND_FILES = {
    // Buttons & Clicks
    wood_click: '/static/assets/audio/wood_click.ogg',
    cherry_click: '/static/assets/audio/cherrywood_click.ogg',
    bamboo_click: '/static/assets/audio/bamboo_click.ogg',
    click: '/static/assets/audio/click.ogg',

    // Tabs & Codex Navigation
    page_flip: '/static/assets/audio/page_flip.ogg',
    toast_in: '/static/assets/audio/toast_in.ogg',

    // Inventory & Slots
    pop: '/static/assets/audio/pop.ogg',
    bundle_insert: '/static/assets/audio/bundle_insert.ogg',
    bundle_drop: '/static/assets/audio/bundle_drop.ogg',
    chest_open: '/static/assets/audio/chest_open.ogg',
    chest_close: '/static/assets/audio/chest_close.ogg',
    door_close: '/static/assets/audio/door_close.ogg',
    barrel_close: '/static/assets/audio/barrel_close.ogg',

    // Server Lifecycle & Alerts
    amethyst_chime: '/static/assets/audio/amethyst_chime.ogg',
    amethyst_resonate: '/static/assets/audio/amethyst_resonate.ogg',
    amethyst_shimmer: '/static/assets/audio/amethyst_shimmer.ogg',
    amethyst_step: '/static/assets/audio/amethyst_step.ogg',
    levelup: '/static/assets/audio/levelup.ogg',
    toast_challenge: '/static/assets/audio/toast_challenge.ogg',
    note_bass: '/static/assets/audio/note_bass.ogg',
    note_pling: '/static/assets/audio/note_pling.ogg',
    note_bell: '/static/assets/audio/note_bell.ogg',
    note_harp: '/static/assets/audio/note_harp.ogg',
    note_flute: '/static/assets/audio/note_flute.ogg',

    // Autosave, Level & XP
    orb: '/static/assets/audio/orb.ogg',

    // Gamemode & Magic
    enchant: '/static/assets/audio/enchant.ogg',
    beacon_activate: '/static/assets/audio/beacon_activate.ogg',
    conduit_activate: '/static/assets/audio/conduit_activate.ogg',

    // Player Actions & Items
    liquid_splash: '/static/assets/audio/liquid_splash.ogg',
    bottle_fill: '/static/assets/audio/bottle_fill.ogg',
    honey_wax: '/static/assets/audio/honey_wax.ogg',
    villager_no: '/static/assets/audio/villager_no.ogg',
    villager_yes: '/static/assets/audio/villager_yes.ogg'
  };

  // Base gain values (balanced for pleasant, soft, cozy anti-stress experience)
  const SOUND_VOLUMES = {
    wood_click: 0.28,
    cherry_click: 0.32,
    bamboo_click: 0.26,
    click: 0.22,
    page_flip: 0.35,
    toast_in: 0.25,
    pop: 0.20,
    bundle_insert: 0.32,
    bundle_drop: 0.30,
    chest_open: 0.32,
    chest_close: 0.30,
    door_close: 0.28,
    barrel_close: 0.28,
    amethyst_chime: 0.36,
    amethyst_resonate: 0.34,
    amethyst_shimmer: 0.28,
    amethyst_step: 0.28,
    levelup: 0.30,
    toast_challenge: 0.32,
    note_bass: 0.30,
    note_pling: 0.28,
    note_bell: 0.30,
    note_harp: 0.28,
    note_flute: 0.25,
    orb: 0.30,
    enchant: 0.30,
    beacon_activate: 0.28,
    conduit_activate: 0.30,
    liquid_splash: 0.28,
    bottle_fill: 0.30,
    honey_wax: 0.30,
    villager_no: 0.30,
    villager_yes: 0.30
  };

  const throttleTimers = {};

  function getContext() {
    if (!audioCtx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        audioCtx = new AudioCtx();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {});
    }
    return audioCtx;
  }

  // Cross-browser proactive audio context unlock on first user gesture
  if (typeof window !== 'undefined' && window.addEventListener) {
    const unlockAudio = () => {
      if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume().catch(() => {});
      }
    };
    ['click', 'keydown', 'pointerdown', 'touchstart'].forEach(evt => {
      window.addEventListener(evt, unlockAudio, { capture: true, passive: true });
    });
  }

  // Pre-load and cache AudioBuffer via Web Audio API (with legacy Safari callback support)
  async function loadAudioBuffer(url) {
    if (bufferCache.has(url)) return bufferCache.get(url);
    if (loadingPromises.has(url)) return loadingPromises.get(url);

    const promise = (async () => {
      try {
        const ctx = getContext();
        if (!ctx) return null;
        const resp = await fetch(url);
        if (!resp.ok) return null;
        const arrayBuf = await resp.arrayBuffer();
        const audioBuf = await new Promise((resolve, reject) => {
          try {
            const res = ctx.decodeAudioData(arrayBuf, resolve, reject);
            if (res && typeof res.then === 'function') {
              res.then(resolve, reject);
            }
          } catch (e) {
            reject(e);
          }
        });
        bufferCache.set(url, audioBuf);
        return audioBuf;
      } catch (err) {
        return null;
      } finally {
        loadingPromises.delete(url);
      }
    })();

    loadingPromises.set(url, promise);
    return promise;
  }

  // Universal sound player with pitch variance and throttling
  async function playSound(key, opts = {}) {
    if (!isSoundEnabled) return;

    // Check throttle
    if (opts.throttleMs) {
      const now = Date.now();
      const last = throttleTimers[key] || 0;
      if (now - last < opts.throttleMs) return;
      throttleTimers[key] = now;
    }

    const url = SOUND_FILES[key];
    if (!url) return;

    try {
      const ctx = getContext();
      if (!ctx) {
        if (typeof Audio !== 'undefined') {
          const fallbackAudio = new Audio(url);
          let rate = opts.pitch ?? 1.0;
          if (opts.pitchVariation) rate += (Math.random() * 2 - 1) * opts.pitchVariation;
          try { fallbackAudio.playbackRate = Math.max(0.5, Math.min(2.0, rate)); } catch (e) {}
          fallbackAudio.volume = Math.max(0, Math.min(1, (SOUND_VOLUMES[key] || 0.25) * (opts.volume ?? 1.0)));
          fallbackAudio.play().catch(() => {});
        }
        return;
      }

      let buffer = bufferCache.get(url);
      if (!buffer) {
        buffer = await loadAudioBuffer(url);
      }

      if (!buffer) {
        if (typeof Audio !== 'undefined') {
          const fallbackAudio = new Audio(url);
          let rate = opts.pitch ?? 1.0;
          if (opts.pitchVariation) rate += (Math.random() * 2 - 1) * opts.pitchVariation;
          try { fallbackAudio.playbackRate = Math.max(0.5, Math.min(2.0, rate)); } catch (e) {}
          fallbackAudio.volume = Math.max(0, Math.min(1, (SOUND_VOLUMES[key] || 0.25) * (opts.volume ?? 1.0)));
          fallbackAudio.play().catch(() => {});
        }
        return;
      }

      const source = ctx.createBufferSource();
      source.buffer = buffer;

      // Organic micro-pitch variance for anti-stress natural feel
      let rate = opts.pitch ?? 1.0;
      if (opts.pitchVariation) {
        rate += (Math.random() * 2 - 1) * opts.pitchVariation;
      }
      source.playbackRate.value = Math.max(0.2, Math.min(3.0, rate));

      const gain = ctx.createGain();
      const baseGain = SOUND_VOLUMES[key] ?? 0.25;
      const targetGain = Math.max(0, Math.min(1.0, baseGain * (opts.volume ?? 1.0)));
      gain.gain.setValueAtTime(targetGain, ctx.currentTime);

      source.connect(gain);
      gain.connect(ctx.destination);
      source.start(0);
    } catch (e) {
      // Audio errors are non-fatal
    }
  }

  function preloadPrimarySounds() {
    const list = [
      'wood_click', 'cherry_click', 'click', 'page_flip',
      'pop', 'bundle_insert', 'bundle_drop', 'orb',
      'amethyst_chime', 'amethyst_resonate', 'door_close',
      'villager_no', 'note_bass', 'note_bell', 'note_pling'
    ];
    setTimeout(() => {
      list.forEach(k => {
        if (SOUND_FILES[k]) loadAudioBuffer(SOUND_FILES[k]);
      });
    }, 200);
  }

  // --- Distinct function implementations ---

  // UI Button Click (soft wooden/cherry/stone click with micro-variance)
  function playClick() {
    const roll = Math.random();
    const pick = roll < 0.45 ? 'wood_click' : (roll < 0.8 ? 'cherry_click' : 'click');
    playSound(pick, { pitchVariation: 0.05, volume: 1.0 });
  }

  // Menu Tab Switch (soft book/page flip)
  function playTabSwitch() {
    playSound('page_flip', { pitchVariation: 0.04, volume: 1.0, throttleMs: 80 });
  }

  // Inventory Slot Hover (gentle pop, throttled so rapid mouse moves don't clutter)
  function playSlotHover() {
    playSound('pop', { pitchVariation: 0.12, volume: 0.75, throttleMs: 50 });
  }

  // Inventory Slot Click (bundle insert/drop cloth rustle)
  function playSlotClick() {
    const pick = Math.random() < 0.5 ? 'bundle_insert' : 'bundle_drop';
    playSound(pick, { pitchVariation: 0.05, volume: 1.0, throttleMs: 40 });
  }

  // Ender Chest open / close
  function playChestOpen() {
    playSound('chest_open', { volume: 0.9, throttleMs: 150 });
  }

  function playChestClose() {
    playSound('chest_close', { volume: 0.9, throttleMs: 150 });
  }

  // Sliders (RAM, cores, view distance) delicate wooden notch tick
  function playSliderTick(val) {
    const p = val ? 0.95 + (parseInt(val, 10) % 8) * 0.02 : 1.0;
    playSound('cherry_click', { pitch: p, pitchVariation: 0.02, volume: 0.65, throttleMs: 35 });
  }

  // Checkbox / switch toggle
  function playToggle() {
    playSound('bamboo_click', { pitch: 1.15, volume: 0.85 });
  }

  // Server Start (Amethyst resonate chime)
  function playServerStart() {
    playSound('amethyst_resonate', { volume: 1.0 });
  }

  // Core Ready / Server Online (Amethyst chime + triumphant bell/levelup)
  function playServerOnline() {
    playSound('amethyst_chime', { volume: 1.0 });
  }

  function playCoreReady() {
    playSound('levelup', { volume: 0.95 });
    setTimeout(() => {
      playSound('amethyst_chime', { volume: 0.85 });
    }, 120);
  }

  // Server Stop / Pause (subtle note block bass + soft door/barrel closure)
  function playServerStop() {
    playSound('note_bass', { pitch: 0.85, volume: 0.75 });
    setTimeout(() => {
      playSound('door_close', { volume: 0.85 });
    }, 80);
  }

  // Autosave success (soft experience orb ping)
  function playAutosave() {
    playSound('orb', { pitchVariation: 0.06, volume: 1.0, throttleMs: 800 });
  }

  // Gamemode change (enchanting table / resonate)
  function playGamemodeChange(gamemode) {
    const gm = String(gamemode || '').toLowerCase();
    if (gm === 'creative' || gm === 'spectator') {
      playSound('enchant', { volume: 0.95 });
    } else {
      playSound('amethyst_resonate', { volume: 0.95 });
    }
  }

  // Player heal action (soft water splash + conduit twinkle)
  function playPlayerHeal() {
    playSound('liquid_splash', { volume: 0.85 });
    setTimeout(() => {
      playSound('conduit_activate', { volume: 0.9 });
    }, 120);
  }

  // Error toast (subtle villager "Hrrm" / low note)
  function playError() {
    playSound('villager_no', { volume: 1.0, throttleMs: 400 });
  }

  // Success toast (soft experience orb / note pling)
  function playSuccess() {
    playSound('orb', { volume: 1.0, throttleMs: 300 });
  }

  // Theme toggle
  function playThemeToggle() {
    playSound('note_flute', { pitch: 1.1, volume: 0.8 });
  }

  // Unmute acknowledgement chime
  function playUnmute() {
    playSound('note_bell', { volume: 0.9 });
  }

  function isEnabled() {
    return isSoundEnabled;
  }

  function setEnabled(val) {
    isSoundEnabled = !!val;
    if (typeof localStorage !== 'undefined' && localStorage.setItem) {
      localStorage.setItem('mc_sound_enabled', isSoundEnabled ? 'true' : 'false');
    }
  }

  return {
    playClick,
    playTabSwitch,
    playSlotHover,
    playSlotClick,
    playChestOpen,
    playChestClose,
    playSliderTick,
    playToggle,
    playServerStart,
    playServerOnline,
    playCoreReady,
    playServerStop,
    playAutosave,
    playGamemodeChange,
    playPlayerHeal,
    playError,
    playSuccess,
    playThemeToggle,
    playUnmute,
    preloadPrimarySounds,
    isEnabled,
    setEnabled
  };
})();

// ---------------- INTERNATIONALIZATION (EN / RU) ----------------
let currentLang = (typeof localStorage !== 'undefined' && localStorage.getItem('mss_lang'))
  ? localStorage.getItem('mss_lang')
  : 'en';

window.getCurrentLang = () => currentLang;

const I18N = {
  en: {
    nav_overview: 'Overview',
    nav_management: 'Management',
    nav_console: 'Console',
    nav_players: 'Players',
    nav_resources: 'Core & Resources',
    nav_world: 'World Management',
    nav_settings: 'Settings',
    nav_eula: 'EULA License',
    btn_theme: 'Theme',
    btn_start_server: 'Start Server',
    btn_stop: 'Stop',
    btn_restart: 'Restart',
    presets_title: 'Quick Presets',
    presets_subtitle: '1-Click Setup',
    telemetry_view_dist: 'View Distance',
    telemetry_uptime: 'Uptime',
    console_title: 'Server Terminal',
    btn_autoscroll: 'Auto-scroll',
    btn_clear: 'Clear',
    console_ready: 'Ready. Start the server or enter a command below...',
    console_cleared: 'Console cleared.',
    console_placeholder: 'Enter command (e.g. op Player, list, help)...',
    btn_send: 'Send',
    engine_card_title: 'Engine & Version',
    label_core: 'Server Core',
    label_version: 'Version',
    label_custom_version: 'Custom Version',
    btn_download_core: 'Download Core',
    btn_custom_jar: 'Custom .jar',
    btn_delete_core: 'Delete Core',
    limits_card_title: 'Resource Limits',
    label_min_ram: 'Min RAM (-Xms)',
    label_max_ram: 'Max RAM (-Xmx)',
    label_cpu_threads: 'CPU Threads',
    label_view_distance: 'View Distance (view-distance)',
    label_autosave: 'World Autosave',
    autosave_off: 'Disabled (0 sec)',
    autosave_5m: 'Every 5 minutes (300 sec)',
    autosave_10m: 'Every 10 minutes (600 sec)',
    autosave_15m: 'Every 15 minutes (900 sec, default)',
    autosave_20m: 'Every 20 minutes (1200 sec)',
    autosave_30m: 'Every 30 minutes (1800 sec)',
    btn_upload_jar: '+ Upload .jar',
    btn_refresh: 'Refresh',
    dropzone_addons: 'Drag & drop .jar files here',
    th_name: 'Name',
    th_size: 'Size',
    th_status: 'Status',
    th_actions: 'Actions',
    world_card_title: 'World Management',
    world_delete_heading: 'Delete Current World',
    world_delete_desc: 'Completely wipe the',
    world_delete_desc_2: 'directory.',
    btn_delete_world: 'Delete World',
    world_upload_heading: 'Upload World from ZIP',
    world_upload_desc: 'Supports .zip archives containing a world folder (with level.dat). The existing world will be replaced.',
    dropzone_world: 'Drag & drop a .zip archive here or select a file',
    btn_select_zip: 'Select .zip File',
    players_card_title: 'Player Management',
    players_card_subtitle: 'Health, inventory inspector, gamemode switcher & teleportation (Ely.by + Mojang skins)',
    tp_source_label: 'Teleport Player (Source)',
    tp_target_label: 'Destination Player (Target)',
    btn_teleport: 'Teleport',
    players_online_heading: 'Online Players',
    players_online_hint: 'Live server memory & NBT data',
    players_none_online: 'No players currently online',
    players_offline_heading: 'Known Players (Offline / World History)',
    players_none_offline: 'No known offline players in world database',
    jvm_title: 'JVM Launch Command',
    btn_verify_java: 'Verify',
    btn_copy_cmd: 'Copy Command',
    btn_copied: 'Copied!',
    props_modal_title: 'server.properties Settings',
    props_port: 'Port',
    props_view_dist: 'View Distance',
    props_auth: 'Authentication (online-mode)',
    props_difficulty: 'Difficulty',
    props_gamemode: 'Default Gamemode',
    props_max_players: 'Max Players',
    props_enabled: 'Enabled',
    props_disabled: 'Disabled',
    props_flight: 'Allow Flight (allow-flight)',
    props_flight_true: 'Allowed (True - for mods)',
    props_flight_false: 'Disallowed (False)',
    btn_cancel: 'Cancel',
    btn_save: 'Save',
    inspect_health: 'Health',
    inspect_food: 'Hunger (Food)',
    inspect_xp: 'Experience (XP)',
    inspect_gm_label: 'Switch Gamemode (1-Click):',
    gm_survival: 'Survival',
    gm_creative: 'Creative',
    gm_adventure: 'Adventure',
    gm_spectator: 'Spectator',
    btn_heal: 'Heal',
    btn_kick: 'Kick',
    inspect_inv_title: 'Inventory',
    inspect_ender_title: 'Ender Chest Contents (27 slots)',
    btn_hide: 'Hide',
    inspect_slot_hint: 'Hover or click any slot to inspect item details.',
    btn_close: 'Close',
    del_world_modal_title: 'Confirm World Deletion',
    del_world_modal_q: 'Are you sure you want to delete the world?',
    del_world_modal_body: 'This action is <strong>irreversible</strong>. All regions, player builds, entities, and inventory files inside <code class="text-danger">world/</code> will be permanently erased.',
    del_world_modal_warn: 'If you want to keep your builds, make a backup before confirming.',
    btn_confirm_delete_world: 'Yes, delete world forever',
    sound_on: 'Sound',
    sound_off: 'Muted',
    sound_title_on: 'Minecraft UI sounds enabled',
    sound_title_off: 'Minecraft UI sounds muted',
    toast_notice: 'Notice',
    toast_success: 'Success',
    toast_error: 'Error',
    toast_warning: 'Warning',
    status_stopped: 'Stopped',
    status_starting: 'Starting...',
    status_online: 'Online',
    ws_ready: 'Ready',
    ws_live: 'Live',
    ws_reconnecting: 'Reconnecting',
    plugins_title: 'Plugins',
    mods_title: 'Mods',
    dir_prefix: 'Directory:',
    chunks_unit: 'chunks',
    autosave_disabled_badge: 'DISABLED',
    autosave_every_min: 'EVERY {min} MIN',
    checking_java: 'Checking Java...',
    java_not_found: '✕ Java not found',
    java_check_err: '✕ Check error',
    no_core: 'no core',
    downloading: 'Downloading...',
    done: 'Done!',
    eula_no: 'No'
  },
  ru: {
    nav_overview: 'Обзор',
    nav_management: 'Управление',
    nav_console: 'Консоль',
    nav_players: 'Игроки',
    nav_resources: 'Ядро и Ресурсы',
    nav_world: 'Управление миром',
    nav_settings: 'Настройки',
    nav_eula: 'Лицензия EULA',
    btn_theme: 'Тема',
    btn_start_server: 'Запустить сервер',
    btn_stop: 'Остановить',
    btn_restart: 'Перезапуск',
    presets_title: 'Пресеты конфигурации',
    presets_subtitle: 'В 1 клик',
    telemetry_view_dist: 'Прорисовка',
    telemetry_uptime: 'Аптайм',
    console_title: 'Терминал сервера',
    btn_autoscroll: 'Авто-скролл',
    btn_clear: 'Очистить',
    console_ready: 'Готов к работе. Запустите сервер или введите команду ниже...',
    console_cleared: 'Консоль очищена.',
    console_placeholder: 'Введите команду (например: op Player, list, help)...',
    btn_send: 'Отправить',
    engine_card_title: 'Движок и Версия',
    label_core: 'Ядро',
    label_version: 'Версия',
    label_custom_version: 'Своя версия',
    btn_download_core: 'Скачать ядро',
    btn_custom_jar: 'Свой .jar',
    btn_delete_core: 'Удалить ядро',
    limits_card_title: 'Лимиты ресурсов',
    label_min_ram: 'Мин. ОЗУ (-Xms)',
    label_max_ram: 'Макс. ОЗУ (-Xmx)',
    label_cpu_threads: 'Потоки CPU',
    label_view_distance: 'Прорисовка (view-distance)',
    label_autosave: 'Автосохранение мира',
    autosave_off: 'Отключено (0 сек)',
    autosave_5m: '5 минут (300 сек)',
    autosave_10m: '10 минут (600 сек)',
    autosave_15m: '15 минут (900 сек, по умолчанию)',
    autosave_20m: '20 минут (1200 сек)',
    autosave_30m: '30 минут (1800 сек)',
    btn_upload_jar: '+ Загрузить .jar',
    btn_refresh: 'Обновить',
    dropzone_addons: 'Перетащите файлы .jar сюда',
    th_name: 'Название',
    th_size: 'Размер',
    th_status: 'Статус',
    th_actions: 'Действия',
    world_card_title: 'Управление миром',
    world_delete_heading: 'Удалить текущий мир',
    world_delete_desc: 'Полностью очистить папку',
    world_delete_desc_2: '.',
    btn_delete_world: 'Удалить мир',
    world_upload_heading: 'Загрузить мир из ZIP',
    world_upload_desc: 'Поддерживаются .zip архивы, внутри которых находится папка с миром (где лежит level.dat). Старый мир будет удален.',
    dropzone_world: 'Перетащите архив .zip сюда или выберите файл',
    btn_select_zip: 'Выбрать .zip файл',
    players_card_title: 'Управление игроками',
    players_card_subtitle: 'Мониторинг здоровья, инвентаря, смена режима и телепортация (скины Ely.by + Mojang)',
    tp_source_label: 'Кого телепортировать (Игрок 1)',
    tp_target_label: 'Куда / К кому (Игрок 2)',
    btn_teleport: 'Телепортировать',
    players_online_heading: 'Игроки онлайн',
    players_online_hint: 'Живые данные из памяти сервера и NBT',
    players_none_online: 'Сейчас на сервере нет игроков онлайн',
    players_offline_heading: 'Известные игроки (офлайн / история мира)',
    players_none_offline: 'Список известных игроков пуст',
    jvm_title: 'Команда запуска JVM',
    btn_verify_java: 'Проверить',
    btn_copy_cmd: 'Копировать команду',
    btn_copied: 'Скопировано!',
    props_modal_title: 'Настройки server.properties',
    props_port: 'Порт',
    props_view_dist: 'Прорисовка',
    props_auth: 'Авторизация (online-mode)',
    props_difficulty: 'Сложность',
    props_gamemode: 'Режим игры',
    props_max_players: 'Макс. игроков',
    props_enabled: 'Включен',
    props_disabled: 'Выключен',
    props_flight: 'Полёты (allow-flight)',
    props_flight_true: 'Разрешены (True - для модов)',
    props_flight_false: 'Запрещены (False)',
    btn_cancel: 'Отмена',
    btn_save: 'Сохранить',
    inspect_health: 'Здоровье (Health)',
    inspect_food: 'Сытость (Food)',
    inspect_xp: 'Опыт (XP)',
    inspect_gm_label: 'Смена игрового режима (1 клик):',
    gm_survival: 'Выживание',
    gm_creative: 'Креатив',
    gm_adventure: 'Приключение',
    gm_spectator: 'Наблюдатель',
    btn_heal: 'Исцелить',
    btn_kick: 'Кик',
    inspect_inv_title: 'Инвентарь',
    inspect_ender_title: 'Содержимое Эндер-сундука (27 слотов)',
    btn_hide: 'Скрыть',
    inspect_slot_hint: 'Наведите курсор или нажмите на любой слот, чтобы просмотреть подробную информацию о предмете.',
    btn_close: 'Закрыть',
    del_world_modal_title: 'Подтверждение удаления мира',
    del_world_modal_q: 'Вы действительно хотите удалить мир?',
    del_world_modal_body: 'Это действие <strong>необратимо</strong>. Все регионы, постройки игроков, сущности и файлы инвентарей в папке <code class="text-danger">world/</code> будут полностью стёрты.',
    del_world_modal_warn: 'Если вы хотите сохранить свои постройки, сделайте резервную копию перед подтверждением.',
    btn_confirm_delete_world: 'Да, удалить мир навсегда',
    sound_on: 'Звук',
    sound_off: 'Выкл',
    sound_title_on: 'Звуки интерфейса Minecraft включены',
    sound_title_off: 'Звуки интерфейса выключены',
    toast_notice: 'Уведомление',
    toast_success: 'Успех',
    toast_error: 'Ошибка',
    toast_warning: 'Внимание',
    status_stopped: 'Остановлен',
    status_starting: 'Запуск...',
    status_online: 'Онлайн',
    ws_ready: 'Готов',
    ws_live: 'Live',
    ws_reconnecting: 'Переподключение',
    plugins_title: 'Плагины',
    mods_title: 'Моды',
    dir_prefix: 'Директория:',
    chunks_unit: 'чанков',
    autosave_disabled_badge: 'ОТКЛЮЧЕНО',
    autosave_every_min: 'КАЖДЫЕ {min} МИН',
    checking_java: 'Проверка Java...',
    java_not_found: '✕ Java не найдена',
    java_check_err: '✕ Ошибка проверки',
    no_core: 'нет ядра',
    downloading: 'Загрузка...',
    done: 'Готово!',
    eula_no: 'Нет'
  }
};

function t(key, vars = {}) {
  const dict = I18N[currentLang] || I18N.en;
  let str = dict[key] !== undefined ? dict[key] : (I18N.en[key] || key);
  Object.entries(vars).forEach(([k, v]) => {
    str = str.replace(`{${k}}`, v);
  });
  return str;
}

function translateServerMessage(msg) {
  if (!msg || currentLang === 'ru') return msg;
  const s = String(msg);
  if (s === 'нет ядра') return 'no core';
  if (s === 'Процесс сервера запущен') return 'Server process started';
  if (s === 'Отправлена команда остановки') return 'Stop command sent';
  if (s === 'Сервер уже остановлен') return 'Server is already stopped';
  if (s === 'Сервер уже запущен') return 'Server is already running';
  if (s === 'Процесс принудительно завершен') return 'Process forcefully terminated';
  if (s === 'Запущена перезагрузка') return 'Restart initiated';
  if (s === 'Загрузка запущена в фоновом режиме') return 'Download started in background';
  if (s === 'Загрузка уже выполняется') return 'Download is already in progress';
  if (s === 'Команда отправлена') return 'Command sent';
  if (s === 'Сервер не запущен') return 'Server is not running';
  if (s === 'Мир успешно удален') return 'World deleted successfully';
  if (s === 'Папка мира еще не создана') return 'World folder does not exist yet';
  if (s === 'Мир успешно загружен и распакован') return 'World uploaded and extracted successfully';
  if (s === 'Нельзя удалить ядро при запущенном сервере') return 'Cannot delete core while server is running';
  if (s.includes('Ядро сервера и библиотеки') && s.includes('успешно удалены')) {
    return 'Server core and libraries deleted successfully';
  }
  const mGm = s.match(/^Режим игрока (.+) изменен на (.+)$/);
  if (mGm) return `Player ${mGm[1]} gamemode changed to ${mGm[2]}`;
  const mTp = s.match(/^Игрок (.+) телепортирован к (.+)$/);
  if (mTp) return `Teleported ${mTp[1]} to ${mTp[2]}`;
  const mKick = s.match(/^Игрок (.+) кикнут с сервера$/);
  if (mKick) return `Player ${mKick[1]} kicked from server`;
  const mHeal = s.match(/^Здоровье и сытость игрока (.+) восстановлены$/);
  if (mHeal) return `Restored health and hunger for ${mHeal[1]}`;
  return s;
}

function toggleLanguage() {
  currentLang = currentLang === 'en' ? 'ru' : 'en';
  try {
    localStorage.setItem('mss_lang', currentLang);
  } catch (e) {}
  MinecraftAudio.playToggle();
  applyLanguage();
}

function applyLanguage() {
  document.documentElement.lang = currentLang;

  const langText = document.getElementById('langToggleText');
  const langBtn = document.getElementById('btnLangToggle');
  if (langText) {
    langText.textContent = currentLang.toUpperCase();
  }
  if (langBtn) {
    langBtn.title = currentLang === 'en' ? 'Switch Language (EN / RU)' : 'Сменить язык (RU / EN)';
  }

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (key) el.textContent = t(key);
  });

  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.getAttribute('data-i18n-html');
    if (key) el.innerHTML = t(key);
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.placeholder = t(key);
  });

  if (window.MinecraftTheme && typeof window.MinecraftTheme.refreshLanguage === 'function') {
    window.MinecraftTheme.refreshLanguage();
  }

  updateAudioToggleUI();
  updateEngineLabels();
  const cpuSlider = document.getElementById('cpuCoresSlider');
  if (cpuSlider) updateCpuCores(cpuSlider.value, false);
  const vdSlider = document.getElementById('viewDistanceSlider');
  if (vdSlider) updateViewDistance(vdSlider.value, false);
  const autosaveSelect = document.getElementById('autosaveIntervalSelect');
  if (autosaveSelect) updateAutosaveBadge(autosaveSelect.value);
  updateCommandPreview();
  loadSystemInfo();
  loadAddonsList();
  checkEulaStatus();
  checkJavaEnvironment();
  pollStatusOnce();
  loadPlayers(false);
  if (currentInspectPlayer) {
    refreshInspectPlayer();
  }
}

function toggleSound() {
  const current = MinecraftAudio.isEnabled();
  MinecraftAudio.setEnabled(!current);
  updateAudioToggleUI();
  if (MinecraftAudio.isEnabled()) {
    MinecraftAudio.playUnmute();
  }
}

function updateAudioToggleUI() {
  const icon = document.getElementById('audioToggleIcon');
  const text = document.getElementById('audioToggleText');
  const btn = document.getElementById('btnAudioToggle');
  const enabled = MinecraftAudio.isEnabled();

  if (icon) {
    icon.className = enabled ? 'bx bx-volume-full' : 'bx bx-volume-mute';
  }
  if (text) {
    text.textContent = enabled ? t('sound_on') : t('sound_off');
  }
  if (btn) {
    if (enabled) {
      btn.classList.remove('btn-outline-secondary');
      btn.classList.add('btn-outline-primary');
      btn.setAttribute('title', t('sound_title_on'));
    } else {
      btn.classList.remove('btn-outline-primary');
      btn.classList.add('btn-outline-secondary');
      btn.setAttribute('title', t('sound_title_off'));
    }
  }
}

// ---------------- THEME SWITCHER (DAY / NIGHT) ----------------
function initTheme() {
  const savedTheme = localStorage.getItem('mc_theme');
  if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    setTheme('dark');
  } else {
    setTheme('light');
  }
}

function setTheme(mode) {
  const html = document.documentElement;
  const themeIcon = document.getElementById('themeIcon');
  html.classList.add('mc-theme');
  if (mode === 'dark') {
    html.classList.remove('light-style');
    html.classList.add('dark-style');
    if (themeIcon) {
      themeIcon.classList.remove('bx-moon');
      themeIcon.classList.add('bx-sun');
    }
    localStorage.setItem('mc_theme', 'dark');
  } else {
    html.classList.remove('dark-style');
    html.classList.add('light-style');
    if (themeIcon) {
      themeIcon.classList.remove('bx-sun');
      themeIcon.classList.add('bx-moon');
    }
    localStorage.setItem('mc_theme', 'light');
  }
}

function toggleTheme() {
  const isDark = document.documentElement.classList.contains('dark-style');
  setTheme(isDark ? 'light' : 'dark');
  MinecraftAudio.playThemeToggle();
}

// ---------------- SIDEBAR VIEW FILTERING ----------------
function switchTab(tab) {
  if (currentTab !== tab) {
    MinecraftAudio.playTabSwitch();
  }
  currentTab = tab;
  document.querySelectorAll('#layout-menu .menu-item[data-tab]').forEach(el => {
    if (el.getAttribute('data-tab') === tab) {
      el.classList.add('active');
    } else {
      el.classList.remove('active');
    }
  });

  const blocks = {
    overview: document.getElementById('block-overview'),
    telemetry: document.getElementById('block-telemetry'),
    console: document.getElementById('block-console'),
    resources: document.getElementById('block-resources'),
    addons: document.getElementById('block-addons'),
    world: document.getElementById('block-world'),
    players: document.getElementById('block-players')
  };

  Object.values(blocks).forEach(b => {
    if (b) b.style.display = 'none';
  });

  if (tab === 'all') {
    if (blocks.overview) blocks.overview.style.display = 'flex';
    if (blocks.telemetry) blocks.telemetry.style.display = 'flex';
    if (blocks.console) blocks.console.style.display = 'flex';
    if (blocks.resources) blocks.resources.style.display = 'flex';
    if (blocks.addons) blocks.addons.style.display = 'flex';
  } else if (blocks[tab]) {
    blocks[tab].style.display = 'flex';
    if (tab === 'players') {
      loadPlayers(false);
    }
  }
}

// ---------------- INITIALIZATION ----------------
window.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  applyLanguage();
  MinecraftAudio.preloadPrimarySounds();

  document.addEventListener('click', (e) => {
    if (e.target.closest('.mc-slot')) return;
    if (e.target.closest('#layout-menu .menu-item[data-tab] .menu-link, #layout-menu .menu-link')) return;
    if (e.target.closest('#btnLangToggle, #btnFxToggle, #btnAudioToggle, #themeToggleBtn, #btnStart, #btnStop, #btnRestart, #btnKill, [onclick*="toggleTheme"], [onclick*="toggleSound"], [onclick*="openPropertiesModal"], [onclick*="closePropertiesModal"]')) return;

    const target = e.target.closest('button, .btn, .nav-link');
    if (target && !target.classList.contains('no-sound')) {
      MinecraftAudio.playClick();
    }
  });

  document.addEventListener('input', (e) => {
    if (e.target.matches('input[type="range"]')) {
      MinecraftAudio.playSliderTick(e.target.value);
    }
  });

  document.addEventListener('change', (e) => {
    if (e.target.matches('input[type="checkbox"]')) {
      MinecraftAudio.playToggle();
    }
  });

  const modalEl = document.getElementById('propertiesModal');
  if (modalEl && window.bootstrap) {
    propertiesModalInstance = new bootstrap.Modal(modalEl);
    modalEl.addEventListener('show.bs.modal', () => MinecraftAudio.playChestOpen());
    modalEl.addEventListener('hide.bs.modal', () => MinecraftAudio.playChestClose());
  }
  const inspectModalEl = document.getElementById('playerInspectModal');
  if (inspectModalEl && window.bootstrap) {
    playerInspectModalInstance = new bootstrap.Modal(inspectModalEl);
    inspectModalEl.addEventListener('show.bs.modal', () => MinecraftAudio.playChestOpen());
    inspectModalEl.addEventListener('hide.bs.modal', () => MinecraftAudio.playChestClose());
  }
  await loadSystemInfo();
  await loadPresets();
  await loadAppConfig();
  await loadEngineVersions(appConfig ? appConfig.engine : 'Paper');
  await loadAddonsList();
  await checkEulaStatus();
  await loadPlayers(false);
  initWebSocket();
  checkJavaEnvironment();
  startPolling();

  const autosaveSelect = document.getElementById('autosaveIntervalSelect');
  if (autosaveSelect) {
    autosaveSelect.addEventListener('change', (e) => onAutosaveIntervalChange(e.target.value));
  }
});

// ---------------- TOAST NOTIFICATIONS ----------------
function showToast(titleOrMessage, maybeMessage, type = 'info', options = {}) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  let title = t('toast_notice');
  let message = titleOrMessage;
  if (maybeMessage !== undefined) {
    title = titleOrMessage;
    message = maybeMessage;
  }

  if (title === 'Успех' || title === 'Success') title = t('toast_success');
  if (title === 'Ошибка' || title === 'Error') title = t('toast_error');
  if (title === 'Внимание' || title === 'Warning') title = t('toast_warning');
  message = translateServerMessage(message);

  if (!options.silent) {
    if (type === 'success' || title === t('toast_success')) {
      MinecraftAudio.playSuccess();
    } else if (type === 'error' || title === t('toast_error')) {
      MinecraftAudio.playError();
    }
  }

  let bgClass = 'bg-primary';
  if (type === 'success') bgClass = 'bg-success';
  if (type === 'error') bgClass = 'bg-danger';
  if (type === 'warning') bgClass = 'bg-warning';

  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-white ${bgClass} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');

  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        <strong>${escapeHtml(title)}</strong>
        ${message ? '<br>' + escapeHtml(message) : ''}
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;
  container.appendChild(toastEl);

  if (window.bootstrap && bootstrap.Toast) {
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
  } else {
    toastEl.classList.add('show');
    setTimeout(() => {
      toastEl.classList.remove('show');
      setTimeout(() => toastEl.remove(), 200);
    }, 3000);
  }
}

// ---------------- PRESETS ----------------
async function loadPresets() {
  try {
    const res = await fetch('/api/presets');
    cachedPresets = await res.json();
  } catch (e) {}
}

function highlightPresetBtn(presetKey) {
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.className = 'btn btn-sm btn-outline-primary preset-btn';
  });
  const active = document.getElementById('preset-' + presetKey);
  if (active) {
    active.className = 'btn btn-sm btn-primary preset-btn';
  }
}

function applyPreset(presetKey) {
  const p = cachedPresets[presetKey];
  if (!p) return;

  document.getElementById('engineSelect').value = p.engine;
  document.getElementById('minRamSlider').value = p.min_ram;
  document.getElementById('maxRamSlider').value = p.max_ram;
  document.getElementById('cpuCoresSlider').value = p.cpu_cores;
  document.getElementById('viewDistanceSlider').value = p.view_distance;

  if (!appConfig) appConfig = {};
  appConfig.custom_flags = p.custom_flags;
  appConfig.preset = presetKey;

  highlightPresetBtn(presetKey);
  updateMinRam(p.min_ram, false);
  updateMaxRam(p.max_ram, false);
  updateCpuCores(p.cpu_cores, false);
  updateViewDistance(p.view_distance, false);
  updateEngineLabels();
  updateCommandPreview();
  loadEngineVersions(p.engine);
  loadAddonsList();

  const msg = currentLang === 'ru'
    ? `Пресет применен: ${p.name}`
    : `Applied preset: ${p.engine} (${p.max_ram} GB RAM)`;
  showToast(t('toast_success'), msg, 'success');
  saveAllConfig(false);
}

// ---------------- SYSTEM SPECS & VERSIONS ----------------
let cachedSystemCores = 8;
async function loadSystemInfo() {
  try {
    const res = await fetch('/api/system');
    const data = await res.json();
    cachedSystemCores = data.total_cpu_cores || 8;
    const ind = document.getElementById('sysCoresIndicator');
    if (ind) {
      ind.textContent = currentLang === 'ru' ? `${cachedSystemCores} макс` : `${cachedSystemCores} max`;
    }
    document.getElementById('cpuCoresSlider').max = Math.max(16, cachedSystemCores);
  } catch (e) {}
}

async function loadEngineVersions(engine) {
  const select = document.getElementById('versionSelect');
  const loader = document.getElementById('versionLoadingIndicator');
  const countBadge = document.getElementById('versionsCountBadge');

  if (loader) loader.classList.remove('d-none');
  try {
    const res = await fetch(`/api/versions?engine=${encodeURIComponent(engine)}`);
    const data = await res.json();
    const versions = data.versions || [];

    select.innerHTML = '';
    versions.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });

    if (countBadge) {
      countBadge.textContent = currentLang === 'ru'
        ? `${versions.length} версий`
        : `${versions.length} versions`;
    }

    const currentVer = appConfig ? appConfig.version : '1.20.4';
    if (versions.includes(currentVer)) {
      select.value = currentVer;
    } else if (versions.length > 0) {
      select.value = versions[0];
      document.getElementById('versionCustomInput').value = currentVer;
    }
  } catch (e) {
  } finally {
    if (loader) loader.classList.add('d-none');
  }
}

function onVersionSelectChange() {
  const selected = document.getElementById('versionSelect').value;
  document.getElementById('versionCustomInput').value = selected;
  if (appConfig) appConfig.version = selected;
  updateEngineLabels();
  debounceSave();
}

function onCustomVersionInputChange() {
  const val = document.getElementById('versionCustomInput').value.trim();
  if (!val) return;
  if (appConfig) appConfig.version = val;
  updateEngineLabels();
  debounceSave();
}

// ---------------- CONFIG & SLIDERS ----------------
async function loadAppConfig() {
  try {
    const res = await fetch('/api/config');
    appConfig = await res.json();

    document.getElementById('engineSelect').value = appConfig.engine;
    document.getElementById('versionCustomInput').value = appConfig.version;
    document.getElementById('minRamSlider').value = appConfig.min_ram;
    document.getElementById('maxRamSlider').value = appConfig.max_ram;
    document.getElementById('cpuCoresSlider').value = appConfig.cpu_cores;
    document.getElementById('viewDistanceSlider').value = appConfig.view_distance || 10;
    document.getElementById('javaPathInput').value = appConfig.java_path;
    document.getElementById('sidebarPortBadge').textContent = `:${appConfig.server_port || 25565}`;

    const autosaveVal = appConfig.autosave_interval_seconds !== undefined
      ? parseInt(appConfig.autosave_interval_seconds, 10)
      : (parseInt(appConfig.autosave_interval_minutes, 10) || 15) * 60;
    const autosaveSelect = document.getElementById('autosaveIntervalSelect');
    if (autosaveSelect) {
      autosaveSelect.value = String(autosaveVal);
      if (autosaveSelect.value !== String(autosaveVal) && autosaveVal > 0) {
        const opt = document.createElement('option');
        opt.value = String(autosaveVal);
        opt.textContent = currentLang === 'ru'
          ? `${Math.round(autosaveVal / 60)} мин (${autosaveVal} сек)`
          : `Every ${Math.round(autosaveVal / 60)} min (${autosaveVal} sec)`;
        autosaveSelect.appendChild(opt);
        autosaveSelect.value = String(autosaveVal);
      }
    }
    updateAutosaveBadge(autosaveVal);

    if (appConfig.preset) highlightPresetBtn(appConfig.preset);

    updateMinRam(appConfig.min_ram, false);
    updateMaxRam(appConfig.max_ram, false);
    updateCpuCores(appConfig.cpu_cores, false);
    updateViewDistance(appConfig.view_distance || 10, false);
    updateEngineLabels();
    updateCommandPreview();
  } catch (e) {}
}

function updateAutosaveBadge(seconds) {
  const badge = document.getElementById('autosaveBadge') || document.querySelector('#autosave-badge') || document.querySelector('.autosave-status-badge');
  if (!badge) return;
  const sec = parseInt(seconds, 10);
  if (isNaN(sec) || sec <= 0) {
    badge.textContent = t('autosave_disabled_badge');
    badge.className = 'badge bg-label-secondary';
    return;
  }
  const mins = Math.max(1, Math.round(sec / 60));
  badge.textContent = t('autosave_every_min', { min: mins });
  badge.className = 'badge bg-label-info';
}

async function onAutosaveIntervalChange(val) {
  const sec = parseInt(val, 10);
  updateAutosaveBadge(sec);
  if (isNaN(sec)) return;

  if (appConfig) {
    appConfig.autosave_interval_seconds = sec;
    appConfig.autosave_interval_minutes = Math.max(1, Math.round(sec / 60));
  }

  try {
    const res = await fetch('/api/server/autosave-interval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds: sec, minutes: Math.round(sec / 60) })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      const label = sec > 0
        ? (currentLang === 'ru' ? `${Math.round(sec / 60)} мин` : `${Math.round(sec / 60)} min`)
        : (currentLang === 'ru' ? 'Отключено' : 'Disabled');
      const msg = currentLang === 'ru'
        ? `Интервал автосохранения: ${label}`
        : `Autosave interval: ${label}`;
      showToast(t('toast_success'), msg, 'success');
      MinecraftAudio.playAutosave();
    } else {
      showToast(t('toast_error'), data.message || (currentLang === 'ru' ? 'Не удалось обновить интервал' : 'Failed to update interval'), 'error');
    }
  } catch (e) {
    showToast(t('toast_error'), currentLang === 'ru' ? 'Ошибка соединения' : 'Connection error', 'error');
  }
}

function updateMinRam(val, triggerSave = true) {
  val = parseInt(val);
  const maxVal = parseInt(document.getElementById('maxRamSlider').value);
  if (val > maxVal) {
    document.getElementById('maxRamSlider').value = val;
    updateMaxRam(val, false);
  }
  document.getElementById('minRamBadge').textContent = `${val} GB`;
  updateCommandPreview();
  if (triggerSave) {
    debounceSave();
  }
}

function updateMaxRam(val, triggerSave = true) {
  val = parseInt(val);
  const minVal = parseInt(document.getElementById('minRamSlider').value);
  if (val < minVal) {
    document.getElementById('minRamSlider').value = val;
    updateMinRam(val, false);
  }
  document.getElementById('maxRamBadge').textContent = `${val} GB`;
  updateCommandPreview();
  if (triggerSave) {
    debounceSave();
  }
}

function formatThreadsCount(val) {
  const n = Math.abs(parseInt(val, 10)) || 0;
  if (currentLang !== 'ru') {
    return n === 1 ? '1 thread' : `${n} threads`;
  }
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return `${n} поток`;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return `${n} потока`;
  }
  return `${n} потоков`;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function updateCpuCores(val, triggerSave = true) {
  document.getElementById('cpuCoresBadge').textContent = formatThreadsCount(val);
  updateCommandPreview();
  if (triggerSave) {
    debounceSave();
  }
}

function updateViewDistance(val, triggerSave = true) {
  val = parseInt(val);
  const unit = t('chunks_unit');
  document.getElementById('viewDistBadge').textContent = `${val} ${unit}`;
  document.getElementById('metricViewDist').textContent = `${val} ${unit}`;
  updateCommandPreview();
  if (triggerSave) {
    debounceSave();
  }
}

function onEngineChange() {
  const engine = document.getElementById('engineSelect').value;
  loadEngineVersions(engine);
  updateEngineLabels();
  updateCommandPreview();
  loadAddonsList();
  saveAllConfig(false);
}

function onConfigInputChange() {
  updateCommandPreview();
  debounceSave();
}

function updateEngineLabels() {
  const engineEl = document.getElementById('engineSelect');
  if (!engineEl) return;
  const engine = engineEl.value;
  const ver = (appConfig && appConfig.version) ? appConfig.version : (document.getElementById('versionCustomInput').value || '1.20.4');

  document.getElementById('bannerEngineTitle').textContent = `${engine} ${ver}`;
  document.getElementById('sidebarEngineTitle').textContent = `${engine} ${ver}`;

  const isPaper = engine.toLowerCase().includes('paper');
  const title = isPaper ? t('plugins_title') : t('mods_title');
  const folder = isPaper ? 'plugins/' : 'mods/';

  const cardTitle = document.getElementById('addonsCardTitle');
  if (cardTitle) cardTitle.textContent = title;

  const sidebarLabel = document.getElementById('sidebarAddonsLabel');
  if (sidebarLabel) sidebarLabel.textContent = title;

  const cardSubtitle = document.getElementById('addonsCardSubtitle');
  if (cardSubtitle) cardSubtitle.innerHTML = `${t('dir_prefix')} <code class="font-mono">${folder}</code>`;
}

function updateCommandPreview() {
  const java = document.getElementById('javaPathInput').value || 'java';
  const minRam = document.getElementById('minRamSlider').value;
  const maxRam = document.getElementById('maxRamSlider').value;
  const cpu = document.getElementById('cpuCoresSlider').value;
  const vd = document.getElementById('viewDistanceSlider').value;
  const engine = document.getElementById('engineSelect').value || '';
  const flags = (appConfig && appConfig.custom_flags) ? appConfig.custom_flags : '-XX:+UseG1GC';

  const summaryEl = document.getElementById('bannerSummaryText');
  if (summaryEl) {
    if (currentLang === 'ru') {
      summaryEl.textContent = `Выделено ${minRam}–${maxRam} GB ОЗУ, ${formatThreadsCount(cpu)} CPU, дальность прорисовки ${vd} чанков.`;
    } else {
      summaryEl.textContent = `Allocated ${minRam}–${maxRam} GB RAM, ${formatThreadsCount(cpu)} CPU, view distance ${vd} chunks.`;
    }
  }

  const targetArg = engine.toLowerCase().includes('forge') ? '@libraries/.../win_args.txt' : '-jar server.jar';
  const cmd = `${java} -Xms${minRam}G -Xmx${maxRam}G -XX:ActiveProcessorCount=${cpu} -Dfile.encoding=UTF-8 ${flags} ${targetArg} nogui`;

  const previewEl = document.getElementById('cmdPreviewText');
  if (previewEl) {
    previewEl.dataset.rawCmd = cmd;
    previewEl.innerHTML = [
      `<span class="jvm-token-bin">${escapeHtml(java)}</span>`,
      `<span class="jvm-token-mem">-Xms${escapeHtml(minRam)}G -Xmx${escapeHtml(maxRam)}G</span>`,
      `<span class="jvm-token-cpu">-XX:ActiveProcessorCount=${escapeHtml(cpu)}</span>`,
      `<span class="jvm-token-flag">-Dfile.encoding=UTF-8 ${escapeHtml(flags)}</span>`,
      `<span class="jvm-token-target">${escapeHtml(targetArg)}</span>`,
      `<span class="jvm-token-arg">nogui</span>`
    ].join(' ');
  }
}

let copyBtnTimer = null;
function copyCommandPreview() {
  const previewEl = document.getElementById('cmdPreviewText');
  if (!previewEl) return;
  const txt = (previewEl.dataset.rawCmd || previewEl.textContent || '').trim();
  navigator.clipboard.writeText(txt);

  const btn = document.getElementById('btnCopyJvmCmd');
  const icon = document.getElementById('btnCopyJvmIcon');
  const label = document.getElementById('btnCopyJvmText');

  if (btn && label) {
    clearTimeout(copyBtnTimer);
    btn.className = 'btn btn-sm btn-success text-nowrap d-inline-flex align-items-center';
    if (icon) icon.className = 'bx bx-check me-1';
    label.textContent = t('btn_copied');

    copyBtnTimer = setTimeout(() => {
      btn.className = 'btn btn-sm btn-outline-secondary text-nowrap d-inline-flex align-items-center';
      if (icon) icon.className = 'bx bx-copy me-1';
      label.textContent = t('btn_copy_cmd');
    }, 2000);
  } else {
    showToast(t('btn_copied'));
  }
}

let saveTimeout = null;
function debounceSave() {
  clearTimeout(saveTimeout);
  saveTimeout = setTimeout(() => saveAllConfig(false), 500);
}

async function saveAllConfig(showNotification = true) {
  if (!appConfig) appConfig = {};
  appConfig.engine = document.getElementById('engineSelect').value;
  appConfig.version = document.getElementById('versionCustomInput').value || document.getElementById('versionSelect').value || '1.20.4';
  appConfig.min_ram = parseInt(document.getElementById('minRamSlider').value);
  appConfig.max_ram = parseInt(document.getElementById('maxRamSlider').value);
  appConfig.cpu_cores = parseInt(document.getElementById('cpuCoresSlider').value);
  appConfig.view_distance = parseInt(document.getElementById('viewDistanceSlider').value);
  appConfig.java_path = document.getElementById('javaPathInput').value;

  const autosaveSelect = document.getElementById('autosaveIntervalSelect');
  if (autosaveSelect) {
    const sec = parseInt(autosaveSelect.value, 10);
    if (!isNaN(sec)) {
      appConfig.autosave_interval_seconds = sec;
      appConfig.autosave_interval_minutes = Math.max(1, Math.round(sec / 60));
    }
  }

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(appConfig)
    });
    const data = await res.json();
    if (data.success && showNotification) {
      showToast(currentLang === 'ru' ? 'Конфигурация сохранена' : 'Configuration saved');
    }
  } catch (e) {}
}

// ---------------- JAVA CHECK ----------------
function formatJavaBadgeLabel(rawVersion) {
  if (!rawVersion) return '✓ Java';
  const m = rawVersion.match(/"([^"]+)"/);
  if (m) {
    const verNum = m[1];
    const major = parseInt(verNum.split('.')[0], 10);
    const isLts = [8, 11, 17, 21, 25].includes(major) || rawVersion.toUpperCase().includes('LTS');
    return `✓ Java ${verNum}${isLts ? ' LTS' : ''}`;
  }
  const clean = rawVersion.replace('openjdk version', 'Java').replace('java version', 'Java').replace(/"/g, '').trim();
  return `✓ ${clean}`;
}

async function checkJavaEnvironment() {
  const chip = document.getElementById('javaStatusChip');
  const javaPathEl = document.getElementById('javaPathInput');
  const javaPath = (javaPathEl ? javaPathEl.value.trim() : '') || 'java';
  if (chip) {
    chip.className = 'badge bg-label-secondary rounded-pill px-2 py-1';
    chip.textContent = t('checking_java');
  }

  try {
    const res = await fetch('/api/java/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ java_path: javaPath })
    });
    const data = await res.json();
    if (!chip) return;
    if (data.valid) {
      chip.className = 'badge bg-label-success rounded-pill px-2 py-1';
      chip.textContent = formatJavaBadgeLabel(data.version);
      chip.title = data.version;
    } else {
      chip.className = 'badge bg-label-danger rounded-pill px-2 py-1';
      chip.textContent = t('java_not_found');
    }
  } catch (e) {
    if (chip) {
      chip.className = 'badge bg-label-danger rounded-pill px-2 py-1';
      chip.textContent = t('java_check_err');
    }
  }
}

// ---------------- SERVER CONTROLS ----------------
async function startServer() {
  await saveAllConfig(false);
  MinecraftAudio.playServerStart();
  try {
    const res = await fetch('/api/server/start', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || t('status_starting'));
    pollStatusOnce();
  } catch (e) {}
}

async function stopServer() {
  MinecraftAudio.playServerStop();
  try {
    const res = await fetch('/api/server/stop', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || (currentLang === 'ru' ? 'Остановка...' : 'Stopping...'));
    pollStatusOnce();
  } catch (e) {}
}

async function restartServer() {
  await saveAllConfig(false);
  MinecraftAudio.playServerStart();
  try {
    const res = await fetch('/api/server/restart', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || (currentLang === 'ru' ? 'Перезапуск...' : 'Restarting...'));
    pollStatusOnce();
  } catch (e) {}
}

async function killServer() {
  const promptText = currentLang === 'ru'
    ? 'Принудительно завершить процесс сервера (SIGKILL)?'
    : 'Forcefully terminate the server process (SIGKILL)?';
  if (!confirm(promptText)) return;
  MinecraftAudio.playServerStop();
  try {
    const res = await fetch('/api/server/kill', { method: 'POST' });
    const data = await res.json();
    showToast(data.message || (currentLang === 'ru' ? 'Процесс убит' : 'Process killed'));
    pollStatusOnce();
  } catch (e) {}
}

// ---------------- WEBSOCKETS LIVE CONSOLE ----------------
function initWebSocket() {
  if (ws) {
    try { ws.close(); } catch (e) {}
  }

  const loc = window.location;
  const wsProtocol = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${wsProtocol}//${loc.host}/ws/console`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById('wsStatusDot').className = 'badge badge-center rounded-pill bg-success w-px-10 h-px-10 ms-2';
    const wsText = document.getElementById('wsStatusText');
    if (wsText) {
      wsText.textContent = t('ws_live');
      wsText.className = 'badge bg-label-success';
    }

    clearInterval(pingInterval);
    pingInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 15000);
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'history' && Array.isArray(msg.data)) {
        appendConsoleLogsBatch(msg.data);
      } else if (msg.type === 'log') {
        appendConsoleLog(msg.data);
        if (typeof msg.data === 'string') {
          const isSaveSuccess = (
            (msg.data.includes('[AutoSave]') && !msg.data.includes('Ошибка') && !msg.data.includes('Error') && !msg.data.includes('отключено')) ||
            msg.data.includes('Saved the game') ||
            msg.data.includes('Saved the world') ||
            msg.data.includes('Automatic save')
          );
          if (isSaveSuccess) {
            MinecraftAudio.playAutosave();
          }
        }
      }
    } catch (e) {
      appendConsoleLog(event.data);
    }
  };

  ws.onclose = () => {
    document.getElementById('wsStatusDot').className = 'badge badge-center rounded-pill bg-danger w-px-10 h-px-10 ms-2';
    const wsText = document.getElementById('wsStatusText');
    if (wsText) {
      wsText.textContent = t('ws_reconnecting');
      wsText.className = 'badge bg-label-danger';
    }
    clearInterval(pingInterval);
    clearTimeout(wsReconnectTimeout);
    wsReconnectTimeout = setTimeout(initWebSocket, 2000);
  };

  ws.onerror = () => {
    try { ws.close(); } catch (e) {}
  };
}

const MAX_CONSOLE_LINES = 1500;

function createLogElement(line) {
  const div = document.createElement('div');
  div.className = 'log-line text-break';

  if (line.includes('[WARN]') || line.includes('WARN')) {
    div.className += ' text-warning';
  } else if (line.includes('[ERROR]') || line.includes('ERROR') || line.includes('Exception')) {
    div.className += ' text-danger';
  } else if (line.startsWith('>')) {
    div.className += ' fw-bold';
  } else if (line.includes('--- [Local MC]') || line.includes('--- [MSS]')) {
    div.className += ' text-success';
  }

  div.textContent = line;
  return div;
}

function appendConsoleLogsBatch(lines) {
  const container = document.getElementById('consoleContainer');
  if (!container || !Array.isArray(lines)) return;

  const sliceLines = lines.length > MAX_CONSOLE_LINES ? lines.slice(-MAX_CONSOLE_LINES) : lines;
  const fragment = document.createDocumentFragment();
  for (let i = 0; i < sliceLines.length; i++) {
    fragment.appendChild(createLogElement(sliceLines[i]));
  }
  container.innerHTML = '';
  container.appendChild(fragment);

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

function appendConsoleLog(line) {
  const container = document.getElementById('consoleContainer');
  if (!container) return;

  const div = createLogElement(line);
  container.appendChild(div);

  while (container.children.length > MAX_CONSOLE_LINES) {
    container.removeChild(container.firstChild);
  }

  if (autoScroll) {
    container.scrollTop = container.scrollHeight;
  }

  if (line.includes('joined the game') || line.includes('left the game')) {
    setTimeout(() => loadPlayers(false), 600);
  }
}

function toggleAutoScroll() {
  autoScroll = !autoScroll;
  const btn = document.getElementById('btnAutoScroll');
  if (autoScroll) {
    if (btn) btn.className = 'btn btn-sm btn-primary me-2';
    const container = document.getElementById('consoleContainer');
    container.scrollTop = container.scrollHeight;
  } else {
    if (btn) btn.className = 'btn btn-sm btn-outline-primary me-2';
  }
}

function clearConsole() {
  document.getElementById('consoleContainer').innerHTML = `<div class="log-line text-muted">${escapeHtml(t('console_cleared'))}</div>`;
}

function executeCommand() {
  const input = document.getElementById('commandInput');
  const cmd = input.value.trim();
  if (!cmd) return;

  MinecraftAudio.playClick();

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'command', data: cmd }));
  } else {
    fetch('/api/server/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd })
    });
  }
  input.value = '';
}

function sendQuickCommand(cmd) {
  if (!isServerRunning) {
    showToast(currentLang === 'ru' ? 'Сервер должен быть запущен' : 'Server must be running');
    return;
  }
  document.getElementById('commandInput').value = cmd;
  executeCommand();
}

// ---------------- STATUS POLLING ----------------
function startPolling() {
  clearInterval(serverPollInterval);
  pollStatusOnce();
  serverPollInterval = setInterval(pollStatusOnce, 1000);
}

async function pollStatusOnce() {
  try {
    const res = await fetch('/api/status', { cache: 'no-store' });
    const st = await res.json();
    updateUIWithStatus(st);
  } catch (e) {}
}

function formatMemory(mb, memStr) {
  if (memStr) return memStr;
  const val = parseFloat(mb) || 0;
  if (val >= 1024) {
    return `${(val / 1024).toFixed(1)} GB`;
  }
  return `${Math.round(val)} MB`;
}

let prevServerStatus = null;
let prevDlDownloading = false;

function updateUIWithStatus(st) {
  isServerRunning = st.is_running;
  const currentRunning = !!(st.is_running || st.status === 'RUNNING');
  if (prevServerStatus !== null) {
    if (!prevServerStatus && currentRunning) {
      MinecraftAudio.playServerOnline();
    } else if (prevServerStatus && !currentRunning && st.status !== 'STARTING') {
      MinecraftAudio.playServerStop();
    }
  }
  prevServerStatus = currentRunning;

  const dl = st.download;
  if (prevDlDownloading && dl && dl.status === 'done') {
    MinecraftAudio.playCoreReady();
  }
  prevDlDownloading = !!(dl && dl.is_downloading);

  const statusText = document.getElementById('statusText');
  const statusDot = document.getElementById('statusDot');

  const btnStart = document.getElementById('btnStart');
  const btnStop = document.getElementById('btnStop');
  const btnRestart = document.getElementById('btnRestart');
  const btnKill = document.getElementById('btnKill');

  const sidebarPlayersBadge = document.getElementById('sidebarPlayersCount');
  if (sidebarPlayersBadge && st.online_players_count !== undefined) {
    sidebarPlayersBadge.textContent = st.online_players_count;
  }

  if (currentTab === 'players' && Date.now() - lastPlayersPollTime > 5000) {
    loadPlayers(false);
  }

  // Autosave interval (in seconds)
  if (st.autosave_seconds !== undefined) {
    const autosaveSelect = document.getElementById('autosaveIntervalSelect');
    if (autosaveSelect && document.activeElement !== autosaveSelect) {
      autosaveSelect.value = String(st.autosave_seconds);
      if (autosaveSelect.value !== String(st.autosave_seconds) && st.autosave_seconds > 0) {
        const opt = document.createElement('option');
        opt.value = String(st.autosave_seconds);
        opt.textContent = currentLang === 'ru'
          ? `${Math.round(st.autosave_seconds / 60)} мин (${st.autosave_seconds} сек)`
          : `Every ${Math.round(st.autosave_seconds / 60)} min (${st.autosave_seconds} sec)`;
        autosaveSelect.appendChild(opt);
        autosaveSelect.value = String(st.autosave_seconds);
      }
    }
    updateAutosaveBadge(st.autosave_seconds);
  }

  // JAR / Core status
  const jarFoundBadge = document.getElementById('jarFoundBadge');
  if (st.jar_exists) {
    jarFoundBadge.className = 'badge bg-label-success';
    jarFoundBadge.textContent = translateServerMessage(st.core_label) || `server.jar · ${st.jar_size_mb} MB`;
  } else {
    jarFoundBadge.className = 'badge bg-label-danger';
    jarFoundBadge.textContent = translateServerMessage(st.core_label) || t('no_core');
  }

  // Download progress
  const dlContainer = document.getElementById('downloadProgressBarContainer');
  const dlBar = document.getElementById('downloadProgressBar');
  const dlText = document.getElementById('downloadStatusText');
  const btnDl = document.getElementById('btnDownloadJar');
  const btnDelCore = document.getElementById('btnDeleteCore');

  if (dl && dl.is_downloading) {
    dlContainer.classList.remove('d-none');
    dlBar.style.width = `${dl.percent}%`;
    dlText.textContent = translateServerMessage(dl.message) || t('downloading');
    btnDl.disabled = true;
    if (btnDelCore) btnDelCore.disabled = true;
  } else {
    if (!dlContainer.classList.contains('d-none') && dl && dl.status === 'done') {
      dlBar.style.width = '100%';
      dlText.textContent = t('done');
      setTimeout(() => dlContainer.classList.add('d-none'), 2500);
    }
    btnDl.disabled = false;
    if (btnDelCore) btnDelCore.disabled = isServerRunning;
  }

  // Process Status & Live Metrics
  if (st.is_running || st.status === 'RUNNING' || st.status === 'STARTING') {
    if (st.status === 'STARTING') {
      statusText.textContent = t('status_starting');
      statusDot.className = 'badge badge-center rounded-pill bg-warning w-px-10 h-px-10 me-2';
      btnStart.disabled = true;
      btnStop.disabled = false;
      btnRestart.disabled = true;
      btnKill.disabled = false;
    } else {
      statusText.textContent = t('status_online');
      statusDot.className = 'badge badge-center rounded-pill bg-success w-px-10 h-px-10 me-2';
      btnStart.disabled = true;
      btnStop.disabled = false;
      btnRestart.disabled = false;
      btnKill.disabled = false;
    }

    const stats = st.stats || {};
    document.getElementById('uptimeText').textContent = formatSeconds(stats.uptime_seconds);
    const cpuClamped = Math.max(0.0, Math.min(100.0, stats.cpu_percent ?? 0.0));
    document.getElementById('metricCpu').textContent = `${cpuClamped.toFixed(1)}%`;
    document.getElementById('metricRam').textContent = formatMemory(stats.memory_mb, stats.memory_str);
    document.getElementById('metricPid').textContent = st.pid ? `#${st.pid}` : '';

  } else {
    statusText.textContent = t('status_stopped');
    statusDot.className = 'badge badge-center rounded-pill bg-secondary w-px-10 h-px-10 me-2';

    btnStart.disabled = false;
    btnStop.disabled = true;
    btnRestart.disabled = true;
    btnKill.disabled = true;

    document.getElementById('uptimeText').textContent = '00:00:00';
    document.getElementById('metricCpu').textContent = '0.0%';
    document.getElementById('metricRam').textContent = '0 MB';
    document.getElementById('metricPid').textContent = '';
  }
}

function formatSeconds(sec) {
  if (!sec) return '00:00:00';
  const h = String(Math.floor(sec / 3600)).padStart(2, '0');
  const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
  const s = String(sec % 60).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

// ---------------- DOWNLOADING, UPLOADING & DELETING CORE ----------------
async function downloadServerJar() {
  const engine = document.getElementById('engineSelect').value;
  const version = (appConfig && appConfig.version) ? appConfig.version : (document.getElementById('versionCustomInput').value || '1.20.4');
  const btn = document.getElementById('btnDownloadJar');

  btn.disabled = true;

  try {
    const res = await fetch('/api/server/download-jar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine, version })
    });
    const data = await res.json();
    showToast(data.message || `${t('downloading')} ${engine} ${version}`);
  } catch (e) {
    btn.disabled = false;
  }
}

async function uploadCustomJar(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  const formData = new FormData();
  formData.append('file', file);

  showToast(`${t('downloading')} ${file.name}...`);
  try {
    const res = await fetch('/api/server/upload-jar', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      showToast(currentLang === 'ru' ? 'server.jar обновлен' : 'server.jar updated');
      pollStatusOnce();
    }
  } catch (e) {}
}

async function deleteServerCore() {
  const confirmMsg = currentLang === 'ru'
    ? 'Удалить установленное ядро сервера, папку libraries и файлы запуска (Forge / NeoForge / Vanilla / Paper / Fabric)? Папки mods, world и настройки server.properties сохранятся.'
    : 'Delete installed server core, libraries folder, and launch scripts (Forge / NeoForge / Vanilla / Paper / Fabric)? Your mods, world, and server.properties will be preserved.';
  if (!confirm(confirmMsg)) {
    return;
  }
  try {
    const res = await fetch('/api/server/core', { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast(t('toast_success'), data.message, 'success');
      pollStatusOnce();
    } else {
      showToast(t('toast_error'), data.message || (currentLang === 'ru' ? 'Не удалось удалить ядро' : 'Failed to delete core'), 'error');
    }
  } catch (e) {
    showToast(t('toast_error'), e.message, 'error');
  }
}

// ---------------- ADDONS (MODS & PLUGINS) ----------------
function onDragOver(e) {
  e.preventDefault();
  document.getElementById('dropZone').classList.add('dragover');
}

function onDragLeave(e) {
  e.preventDefault();
  document.getElementById('dropZone').classList.remove('dragover');
}

function onFileDrop(e) {
  e.preventDefault();
  document.getElementById('dropZone').classList.remove('dragover');
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    uploadAddonFiles(e.dataTransfer.files);
  }
}

function handleFileSelect(input) {
  if (input.files && input.files.length > 0) {
    uploadAddonFiles(input.files);
    input.value = '';
  }
}

async function uploadAddonFiles(fileList) {
  const formData = new FormData();
  let jarCount = 0;
  for (const f of fileList) {
    if (f.name.toLowerCase().endsWith('.jar')) {
      formData.append('files', f);
      jarCount++;
    }
  }

  if (jarCount === 0) {
    showToast(currentLang === 'ru' ? 'Выберите файлы .jar' : 'Please select .jar files');
    return;
  }

  try {
    const res = await fetch('/api/addons/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      MinecraftAudio.playSuccess();
      showToast(currentLang === 'ru' ? `Загружено файлов: ${data.saved_count}` : `Uploaded files: ${data.saved_count}`);
      loadAddonsList();
    }
  } catch (e) {}
}

async function loadAddonsList() {
  try {
    const res = await fetch('/api/addons');
    const data = await res.json();
    renderAddonsList(data.items || [], data.folder);
  } catch (e) {}
}

function renderAddonsList(items, folder) {
  const container = document.getElementById('addonsList');
  const countBadge = document.getElementById('addonsCount');
  if (countBadge) countBadge.textContent = items.length;

  const folderName = folder || 'mods';
  if (!items || items.length === 0) {
    const emptyText = currentLang === 'ru'
      ? `В папке ${folderName} пока пусто`
      : `Folder ${folderName} is currently empty`;
    container.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-4">${escapeHtml(emptyText)}</td></tr>`;
    return;
  }

  container.innerHTML = '';
  items.forEach(item => {
    const tr = document.createElement('tr');
    const badgeClass = item.enabled ? 'bg-label-success' : 'bg-label-secondary';
    const statusLabel = item.enabled
      ? (currentLang === 'ru' ? 'Активен' : 'Active')
      : (currentLang === 'ru' ? 'Отключен' : 'Disabled');
    const toggleLabel = item.enabled
      ? (currentLang === 'ru' ? 'Отключить' : 'Disable')
      : (currentLang === 'ru' ? 'Включить' : 'Enable');
    const deleteLabel = currentLang === 'ru' ? 'Удалить' : 'Delete';

    tr.innerHTML = `
      <td><strong class="${item.enabled ? '' : 'text-muted text-decoration-line-through'}">${escapeHtml(item.filename)}</strong></td>
      <td>${escapeHtml(item.size_str)}</td>
      <td><span class="badge ${badgeClass}">${statusLabel}</span></td>
      <td>
        <button onclick="toggleAddon('${escapeHtml(item.filename)}')" class="btn btn-xs btn-outline-primary me-1">
          ${toggleLabel}
        </button>
        <button onclick="deleteAddon('${escapeHtml(item.filename)}')" class="btn btn-xs btn-outline-danger" title="${deleteLabel}">
          ${deleteLabel}
        </button>
      </td>
    `;
    container.appendChild(tr);
  });
}

async function toggleAddon(filename) {
  MinecraftAudio.playToggle();
  try {
    const res = await fetch(`/api/addons/${encodeURIComponent(filename)}/toggle`, { method: 'POST' });
    const data = await res.json();
    if (data.success) loadAddonsList();
  } catch (e) {}
}

async function deleteAddon(filename) {
  const q = currentLang === 'ru' ? `Удалить ${filename}?` : `Delete ${filename}?`;
  if (!confirm(q)) return;
  MinecraftAudio.playChestClose();
  try {
    const res = await fetch(`/api/addons/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast(currentLang === 'ru' ? 'Файл удален' : 'File deleted');
      loadAddonsList();
    }
  } catch (e) {}
}

// ---------------- WORLD MANAGEMENT ----------------
function onWorldDragOver(e) {
  e.preventDefault();
  document.getElementById('worldDropZone').classList.add('dragover');
}

function onWorldDragLeave(e) {
  e.preventDefault();
  document.getElementById('worldDropZone').classList.remove('dragover');
}

function onWorldDrop(e) {
  e.preventDefault();
  document.getElementById('worldDropZone').classList.remove('dragover');
  if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
    uploadWorldZip(e.dataTransfer.files[0]);
  }
}

function handleWorldFileSelect(input) {
  if (input.files && input.files.length > 0) {
    uploadWorldZip(input.files[0]);
    input.value = '';
  }
}

async function uploadWorldZip(file) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    showToast(t('toast_error'), currentLang === 'ru' ? 'Только .zip архивы поддерживаются' : 'Only .zip archives are supported', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('file', file);

  const container = document.getElementById('worldUploadProgressContainer');
  const pBar = document.getElementById('worldUploadProgressBar');
  const pText = document.getElementById('worldUploadStatusText');

  container.classList.remove('d-none');
  pText.innerText = currentLang === 'ru' ? 'Загрузка и распаковка...' : 'Uploading and extracting...';
  pBar.style.width = '50%';

  try {
    const res = await fetch('/api/world/upload', {
      method: 'POST',
      body: formData
    });
    const json = await res.json();
    if (json.success) {
      pBar.style.width = '100%';
      pText.innerText = t('done');
      showToast(t('toast_success'), json.message, 'success');
      setTimeout(() => container.classList.add('d-none'), 2000);
    } else {
      throw new Error(json.message || (currentLang === 'ru' ? 'Ошибка распаковки архива' : 'Failed to extract world archive'));
    }
  } catch (e) {
    container.classList.add('d-none');
    showToast(t('toast_error'), e.message, 'error');
  }
}

function deleteWorld() {
  const modalEl = document.getElementById('confirmDeleteWorldModal');
  if (modalEl && window.bootstrap) {
    const modal = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
    modal.show();
  } else if (confirm(t('del_world_modal_q'))) {
    executeDeleteWorld();
  }
}

async function executeDeleteWorld() {
  const btn = document.getElementById('btnConfirmDeleteWorld');
  const originalHtml = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>${currentLang === 'ru' ? 'Удаление...' : 'Deleting...'}`;
  }

  try {
    const res = await fetch('/api/world', { method: 'DELETE' });
    const json = await res.json();
    if (json.success) {
      showToast(t('toast_success'), json.message, 'success');
    } else {
      showToast(t('toast_error'), json.message, 'error');
    }
  } catch (e) {
    showToast(t('toast_error'), e.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
    const modalEl = document.getElementById('confirmDeleteWorldModal');
    if (modalEl && window.bootstrap) {
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
    }
  }
}

// ---------------- EULA & PROPERTIES ----------------
async function checkEulaStatus() {
  try {
    const res = await fetch('/api/server/eula');
    const data = await res.json();
    const chip = document.getElementById('eulaChip');
    if (data.accepted) {
      chip.textContent = 'OK';
      chip.className = 'badge bg-label-success ms-auto';
    } else {
      chip.textContent = t('eula_no');
      chip.className = 'badge bg-label-danger ms-auto';
    }
  } catch (e) {}
}

async function toggleEulaModal() {
  const q = currentLang === 'ru'
    ? 'Принять лицензионное соглашение Minecraft EULA (eula=true)?'
    : 'Accept the Minecraft EULA license agreement (eula=true)?';
  if (confirm(q)) {
    await fetch('/api/server/eula/accept', { method: 'POST' });
    showToast(currentLang === 'ru' ? 'EULA принята' : 'EULA accepted');
    checkEulaStatus();
  }
}

async function openPropertiesModal() {
  try {
    const res = await fetch('/api/server/properties');
    const props = await res.json();

    document.getElementById('propPort').value = props['server-port'] || 25565;
    document.getElementById('propViewDistance').value = props['view-distance'] || 10;
    document.getElementById('propOnlineMode').value = props['online-mode'] || 'false';
    document.getElementById('propDifficulty').value = props['difficulty'] || 'normal';
    document.getElementById('propGamemode').value = props['gamemode'] || 'survival';
    document.getElementById('propMaxPlayers').value = props['max-players'] || 20;
    document.getElementById('propPvp').value = props['pvp'] || 'true';
    document.getElementById('propAllowFlight').value = props['allow-flight'] || 'true';
    document.getElementById('propMotd').value = props['motd'] || 'A Minecraft Server';

    if (propertiesModalInstance) {
      propertiesModalInstance.show();
    }
  } catch (e) {}
}

function closePropertiesModal() {
  if (propertiesModalInstance) {
    propertiesModalInstance.hide();
  }
}

async function saveProperties() {
  const viewDist = document.getElementById('propViewDistance').value;
  const props = {
    'server-port': document.getElementById('propPort').value,
    'view-distance': viewDist,
    'online-mode': document.getElementById('propOnlineMode').value,
    'difficulty': document.getElementById('propDifficulty').value,
    'gamemode': document.getElementById('propGamemode').value,
    'max-players': document.getElementById('propMaxPlayers').value,
    'pvp': document.getElementById('propPvp').value,
    'allow-flight': document.getElementById('propAllowFlight').value,
    'motd': document.getElementById('propMotd').value
  };

  try {
    const res = await fetch('/api/server/properties', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(props)
    });
    const data = await res.json();
    if (data.success) {
      MinecraftAudio.playAutosave();
      showToast(currentLang === 'ru' ? 'server.properties сохранен' : 'server.properties saved');
      document.getElementById('sidebarPortBadge').textContent = `:${props['server-port']}`;
      document.getElementById('viewDistanceSlider').value = viewDist;
      updateViewDistance(viewDist, false);
      closePropertiesModal();
    }
  } catch (e) {}
}

// ---------------- PLAYERS MANAGEMENT ----------------
function getGamemodeBadges() {
  return {
    survival: { label: t('gm_survival'), cls: 'bg-label-success' },
    creative: { label: t('gm_creative'), cls: 'bg-label-info' },
    adventure: { label: t('gm_adventure'), cls: 'bg-label-warning' },
    spectator: { label: t('gm_spectator'), cls: 'bg-label-secondary' }
  };
}

async function loadPlayers(showNotification = false) {
  lastPlayersPollTime = Date.now();
  try {
    const res = await fetch('/api/players', { cache: 'no-store' });
    const data = await res.json();
    renderPlayersSection(data);
    if (showNotification) {
      showToast(currentLang === 'ru' ? 'Список игроков обновлен' : 'Player list refreshed');
    }
  } catch (e) {
    if (showNotification) {
      showToast(t('toast_error'), currentLang === 'ru' ? 'Не удалось загрузить список игроков' : 'Failed to load players list', 'error');
    }
  }
}

function renderPlayersSection(data) {
  const onlinePlayers = data.online || [];
  const offlinePlayers = data.offline || [];
  const onlineCount = data.online_count ?? onlinePlayers.length;
  const totalCount = data.total_known ?? (onlinePlayers.length + offlinePlayers.length);

  const sidebarBadge = document.getElementById('sidebarPlayersCount');
  if (sidebarBadge) sidebarBadge.textContent = onlineCount;

  const onlineBadge = document.getElementById('playersOnlineCountBadge');
  if (onlineBadge) {
    onlineBadge.textContent = currentLang === 'ru' ? `Онлайн: ${onlineCount}` : `Online: ${onlineCount}`;
  }

  const totalBadge = document.getElementById('playersTotalCountBadge');
  if (totalBadge) {
    totalBadge.textContent = currentLang === 'ru' ? `Всего в базе: ${totalCount}` : `Total known: ${totalCount}`;
  }

  const srcSelect = document.getElementById('tpSourceSelect');
  const dstSelect = document.getElementById('tpTargetSelect');
  if (srcSelect && dstSelect) {
    const prevSrc = srcSelect.value;
    const prevDst = dstSelect.value;
    const allNames = [
      ...onlinePlayers.map(p => ({ name: p.name, online: true })),
      ...offlinePlayers.map(p => ({ name: p.name, online: false }))
    ];

    srcSelect.innerHTML = `<option value="">${currentLang === 'ru' ? '— Выберите игрока —' : '— Select player —'}</option>`;
    dstSelect.innerHTML = `<option value="">${currentLang === 'ru' ? '— Выберите цель —' : '— Select target —'}</option>`;

    allNames.forEach(p => {
      const suffix = p.online
        ? (currentLang === 'ru' ? ' (Онлайн)' : ' (Online)')
        : (currentLang === 'ru' ? ' (Офлайн)' : ' (Offline)');
      const opt1 = document.createElement('option');
      opt1.value = p.name;
      opt1.textContent = p.name + suffix;
      srcSelect.appendChild(opt1);

      const opt2 = document.createElement('option');
      opt2.value = p.name;
      opt2.textContent = p.name + suffix;
      dstSelect.appendChild(opt2);
    });

    if (prevSrc && allNames.some(p => p.name === prevSrc)) srcSelect.value = prevSrc;
    if (prevDst && allNames.some(p => p.name === prevDst)) dstSelect.value = prevDst;
  }

  const onlineGrid = document.getElementById('onlinePlayersGrid');
  if (onlineGrid) {
    if (onlinePlayers.length === 0) {
      const emptyMsg = data.server_running
        ? t('players_none_online')
        : (currentLang === 'ru'
            ? 'Сервер остановлен. Запустите сервер для отслеживания онлайн-игроков'
            : 'Server is stopped. Start the server to track live online players');
      onlineGrid.innerHTML = `
        <div class="col-12">
          <div class="card">
            <div class="card-body text-center py-4 text-muted">
              <i class="bx bx-user-x fs-1 mb-2 d-block"></i>
              ${escapeHtml(emptyMsg)}
            </div>
          </div>
        </div>
      `;
    } else {
      onlineGrid.innerHTML = onlinePlayers.map(p => buildPlayerCardHtml(p, true)).join('');
    }
  }

  const offlineGrid = document.getElementById('offlinePlayersGrid');
  if (offlineGrid) {
    if (offlinePlayers.length === 0) {
      offlineGrid.innerHTML = `
        <div class="col-12">
          <div class="card">
            <div class="card-body text-center py-3 text-muted">
              ${escapeHtml(t('players_none_offline'))}
            </div>
          </div>
        </div>
      `;
    } else {
      offlineGrid.innerHTML = offlinePlayers.map(p => buildPlayerCardHtml(p, false)).join('');
    }
  }
}

function formatCoords(pos) {
  if (!pos) return '0, 64, 0';
  if (Array.isArray(pos)) return `${pos[0] ?? 0}, ${pos[1] ?? 64}, ${pos[2] ?? 0}`;
  return `${pos.x ?? 0}, ${pos.y ?? 64}, ${pos.z ?? 0}`;
}

function formatDimension(dim) {
  if (!dim) return 'Overworld';
  const d = String(dim).toLowerCase();
  if (d.includes('nether')) return 'Nether';
  if (d.includes('end')) return 'The End';
  if (d.includes('overworld')) return 'Overworld';
  return dim;
}

function buildPlayerCardHtml(player, isOnline) {
  const statusBadge = isOnline
    ? `<span class="badge bg-label-success">${currentLang === 'ru' ? 'ОНЛАЙН' : 'ONLINE'}</span>`
    : `<span class="badge bg-label-secondary">${currentLang === 'ru' ? 'ОФЛАЙН' : 'OFFLINE'}</span>`;

  const gmKey = (player.gamemode || 'survival').toLowerCase();
  const badges = getGamemodeBadges();
  const gmInfo = badges[gmKey] || { label: player.gamemode || 'Survival', cls: 'bg-label-primary' };

  const hasRealNbt = Boolean(player.has_nbt && player.health !== null && player.health !== undefined);
  const hp = hasRealNbt ? Math.min(20, Math.max(0, parseFloat(player.health))) : null;
  const hpPct = hp !== null ? Math.round((hp / 20) * 100) : null;
  const xpLevel = hasRealNbt && player.xp_level !== null && player.xp_level !== undefined ? player.xp_level : null;
  const coordsStr = hasRealNbt && player.position ? formatCoords(player.position) : null;
  const dimStr = hasRealNbt && player.dimension ? formatDimension(player.dimension) : null;

  const hpLabel = currentLang === 'ru' ? 'Здоровье' : 'Health';
  const lvlUnit = currentLang === 'ru' ? 'ур. XP' : 'XP lvl';
  const itemsLabel = currentLang === 'ru' ? 'Предметов' : 'Items';
  const invBtnLabel = currentLang === 'ru' ? 'Инвентарь' : 'Inventory';
  const viewInvLabel = currentLang === 'ru' ? 'Просмотр инвентаря' : 'Inspect Inventory';

  let bodyContent = '';
  if (hasRealNbt) {
    bodyContent = `
      <div class="mb-2">
        <div class="d-flex justify-content-between small text-muted mb-1">
          <span><i class="bx bxs-heart text-danger me-1"></i>${hpLabel}: <strong class="text-body">${hp} / 20 HP</strong></span>
          ${xpLevel !== null ? `<span><i class="bx bx-star text-warning me-1"></i>${xpLevel} ${lvlUnit}</span>` : ''}
        </div>
        <div class="progress" style="height: 6px;">
          <div class="progress-bar bg-danger" role="progressbar" style="width: ${hpPct}%;"></div>
        </div>
      </div>
      ${coordsStr ? `
        <div class="d-flex justify-content-between align-items-center small text-muted mb-3">
          <span><i class="bx bx-compass me-1"></i>${dimStr || 'World'}: <code>${coordsStr}</code></span>
          <span>${itemsLabel}: <strong>${player.inventory_count ?? 0}</strong></span>
        </div>
      ` : `
        <div class="small text-muted mb-3">
          <span>${itemsLabel}: <strong>${player.inventory_count ?? 0}</strong></span>
        </div>
      `}
    `;
  } else {
    const syncText = isOnline
      ? (currentLang === 'ru' ? 'Ожидание синхронизации данных игрока...' : 'Waiting for player NBT sync...')
      : (currentLang === 'ru' ? 'Данные инвентаря и мира отсутствуют' : 'No saved world/inventory data');
    bodyContent = `
      <div class="small text-muted mb-3 py-1">
        <span>${syncText}</span>
      </div>
    `;
  }

  const buttons = isOnline ? `
    <div class="d-flex gap-2">
      <button class="btn btn-sm btn-outline-primary flex-grow-1" onclick="openPlayerInspectModal('${escapeHtml(player.name)}')">
        <i class="bx bx-grid-alt me-1"></i>${invBtnLabel}
      </button>
      <button class="btn btn-sm btn-outline-success" onclick="healPlayer('${escapeHtml(player.name)}')" title="${t('btn_heal')}">
        <i class="bx bx-plus-medical"></i>
      </button>
      <button class="btn btn-sm btn-outline-danger" onclick="kickPlayer('${escapeHtml(player.name)}')" title="${t('btn_kick')}">
        <i class="bx bx-log-out-circle"></i>
      </button>
    </div>
  ` : `
    <button class="btn btn-sm btn-outline-secondary w-100" onclick="openPlayerInspectModal('${escapeHtml(player.name)}')">
      <i class="bx bx-grid-alt me-1"></i>${viewInvLabel}
    </button>
  `;

  return `
    <div class="col-12 col-md-6 col-xl-4">
      <div class="card h-100">
        <div class="card-body">
          <div class="d-flex align-items-center justify-content-between mb-3">
            <div class="d-flex align-items-center gap-3">
              <img src="/api/players/${encodeURIComponent(player.name)}/avatar" alt="${escapeHtml(player.name)}" class="mc-avatar rounded" width="44" height="44">
              <div>
                <h6 class="mb-0 fw-semibold">${escapeHtml(player.name)}</h6>
                <div class="d-flex align-items-center gap-1 mt-1">
                  ${statusBadge}
                  <span class="badge ${gmInfo.cls}">${gmInfo.label}</span>
                </div>
              </div>
            </div>
            <button class="btn btn-sm btn-icon btn-outline-secondary" title="${invBtnLabel}" onclick="openPlayerInspectModal('${escapeHtml(player.name)}')">
              <i class="bx bx-search-alt"></i>
            </button>
          </div>

          ${bodyContent}

          ${buttons}
        </div>
      </div>
    </div>
  `;
}

async function performPlayerAction(payload, actionOptions = {}) {
  try {
    const res = await fetch('/api/players/action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showToast(t('toast_success'), data.message, 'success', { silent: !!actionOptions.silentToastSound });
      setTimeout(() => loadPlayers(false), 400);
      return true;
    } else {
      let errMsg = data.message;
      if (!errMsg && data.detail) {
        errMsg = Array.isArray(data.detail)
          ? data.detail.map(d => d.msg || JSON.stringify(d)).join(', ')
          : String(data.detail);
      }
      showToast(t('toast_error'), errMsg || (currentLang === 'ru' ? 'Не удалось выполнить действие' : 'Action failed'), 'error');
      return false;
    }
  } catch (e) {
    showToast(t('toast_error'), e.message || (currentLang === 'ru' ? 'Ошибка соединения' : 'Connection error'), 'error');
    return false;
  }
}

async function setPlayerGamemode(playerName, gamemode) {
  const ok = await performPlayerAction({
    action: 'gamemode',
    player: playerName,
    mode: gamemode,
    value: gamemode
  }, { silentToastSound: true });
  if (ok && typeof MinecraftAudio !== 'undefined' && MinecraftAudio.playGamemodeChange) {
    MinecraftAudio.playGamemodeChange(gamemode);
  }
  if (ok && typeof currentInspectPlayer !== 'undefined' && currentInspectPlayer === playerName) {
    if (typeof document !== 'undefined') {
      const gmKey = String(gamemode || '').toLowerCase();
      const badges = getGamemodeBadges();
      const gmInfo = badges[gmKey] || { label: gamemode, cls: 'bg-label-primary' };
      const gmBadge = document.getElementById('inspectPlayerGmBadge');
      if (gmBadge) {
        gmBadge.className = `badge ${gmInfo.cls}`;
        gmBadge.textContent = gmInfo.label;
      }
      const gmButtons = {
        survival: document.getElementById('btnGmSurvival'),
        creative: document.getElementById('btnGmCreative'),
        adventure: document.getElementById('btnGmAdventure'),
        spectator: document.getElementById('btnGmSpectator')
      };
      Object.entries(gmButtons).forEach(([key, btn]) => {
        if (btn) {
          if (key === gmKey) {
            btn.classList.add('active');
          } else {
            btn.classList.remove('active');
          }
        }
      });
    }
    if (typeof refreshInspectPlayer === 'function') {
      setTimeout(() => refreshInspectPlayer(), 500);
    }
  }
}

async function teleportSelectedPlayers() {
  const p1 = document.getElementById('tpSourceSelect').value;
  const p2 = document.getElementById('tpTargetSelect').value;
  if (!p1 || !p2) {
    showToast(t('toast_warning'), currentLang === 'ru' ? 'Выберите обоих игроков для телепортации' : 'Select both source and target players', 'warning');
    return;
  }
  await performPlayerAction({
    action: 'teleport',
    player: p1,
    target: p2,
    value: p2
  });
}

async function healPlayer(playerName) {
  const ok = await performPlayerAction({
    action: 'heal',
    player: playerName
  }, { silentToastSound: true });
  if (ok) {
    if (typeof MinecraftAudio !== 'undefined' && MinecraftAudio.playPlayerHeal) {
      MinecraftAudio.playPlayerHeal();
    }
    if (currentInspectPlayer === playerName) {
      setTimeout(() => refreshInspectPlayer(), 500);
    }
  }
}

async function kickPlayer(playerName) {
  const q = currentLang === 'ru'
    ? `Вы действительно хотите кикнуть игрока ${playerName} с сервера?`
    : `Are you sure you want to kick ${playerName} from the server?`;
  if (!confirm(q)) return;
  const reason = currentLang === 'ru'
    ? 'Кикнут администратором из панели управления'
    : 'Kicked by administrator from MSS panel';
  await performPlayerAction({
    action: 'kick',
    player: playerName,
    reason,
    value: reason
  });
}

// ---------------- PLAYER INSPECTION MODAL & INVENTORY GRID ----------------
async function openPlayerInspectModal(playerName) {
  currentInspectPlayer = playerName;
  if (playerInspectModalInstance) {
    playerInspectModalInstance.show();
  }
  await refreshInspectPlayer();
}

async function refreshInspectPlayer() {
  if (!currentInspectPlayer) return;
  try {
    const res = await fetch(`/api/players/${encodeURIComponent(currentInspectPlayer)}/data`, { cache: 'no-store' });
    if (!res.ok) {
      showToast(t('toast_error'), currentLang === 'ru' ? 'Не удалось получить данные игрока' : 'Failed to fetch player data', 'error');
      return;
    }
    const data = await res.json();
    populateInspectModal(data);
  } catch (e) {
    showToast(t('toast_error'), currentLang === 'ru' ? 'Ошибка чтения NBT данных игрока' : 'Error reading player NBT data', 'error');
  }
}

function setInspectPlayerGamemode(gamemode) {
  if (!currentInspectPlayer) return;
  setPlayerGamemode(currentInspectPlayer, gamemode);
}

function healInspectPlayer() {
  if (!currentInspectPlayer) return;
  healPlayer(currentInspectPlayer);
}

function kickInspectPlayer() {
  if (!currentInspectPlayer) return;
  kickPlayer(currentInspectPlayer);
}

function populateInspectModal(data) {
  const name = data.name || currentInspectPlayer;
  document.getElementById('inspectPlayerAvatar').src = `/api/players/${name}/avatar`;
  document.getElementById('inspectPlayerName').textContent = name;
  document.getElementById('inspectPlayerUuid').textContent = `UUID: ${data.uuid || '—'}`;

  const coordsWord = currentLang === 'ru' ? 'Координаты' : 'Coordinates';
  if (data.has_nbt && data.position) {
    const dim = formatDimension(data.dimension);
    const coords = formatCoords(data.position);
    document.getElementById('inspectPlayerCoords').textContent = `${dim} · ${coordsWord}: ${coords}`;
  } else {
    document.getElementById('inspectPlayerCoords').textContent = data.online
      ? `${coordsWord}: ${currentLang === 'ru' ? 'ожидание синхронизации' : 'waiting for sync'}`
      : `${coordsWord}: ${currentLang === 'ru' ? 'данные отсутствуют' : 'no data'}`;
  }

  const statusBadge = document.getElementById('inspectPlayerStatusBadge');
  if (data.online) {
    statusBadge.className = 'badge bg-label-success';
    statusBadge.textContent = currentLang === 'ru' ? 'ОНЛАЙН' : 'ONLINE';
  } else {
    statusBadge.className = 'badge bg-label-secondary';
    statusBadge.textContent = currentLang === 'ru' ? 'ОФЛАЙН' : 'OFFLINE';
  }

  const gmKey = (data.gamemode || 'survival').toLowerCase();
  const badges = getGamemodeBadges();
  const gmInfo = badges[gmKey] || { label: data.gamemode || 'Survival', cls: 'bg-label-primary' };
  const gmBadge = document.getElementById('inspectPlayerGmBadge');
  gmBadge.className = `badge ${gmInfo.cls}`;
  gmBadge.textContent = gmInfo.label;

  const gmButtons = {
    survival: document.getElementById('btnGmSurvival'),
    creative: document.getElementById('btnGmCreative'),
    adventure: document.getElementById('btnGmAdventure'),
    spectator: document.getElementById('btnGmSpectator')
  };
  Object.entries(gmButtons).forEach(([key, btn]) => {
    if (btn) {
      if (key === gmKey) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
  });

  const hp = Math.min(20, Math.max(0, parseFloat(data.health ?? 20)));
  const hpPct = Math.round((hp / 20) * 100);
  document.getElementById('inspectHealthText').textContent = `${hp} / 20 HP`;
  document.getElementById('inspectHealthBar').style.width = `${hpPct}%`;

  const food = Math.min(20, Math.max(0, parseInt(data.food ?? 20)));
  const foodPct = Math.round((food / 20) * 100);
  document.getElementById('inspectFoodText').textContent = `${food} / 20`;
  document.getElementById('inspectFoodBar').style.width = `${foodPct}%`;

  document.getElementById('inspectXpLevel').textContent = currentLang === 'ru'
    ? `${data.xp_level ?? 0} ур.`
    : `${data.xp_level ?? 0} lvl`;
  document.getElementById('inspectXpTotal').textContent = currentLang === 'ru'
    ? `${data.xp_progress ?? 0}% до след. ур.`
    : `${data.xp_progress ?? 0}% to next`;

  renderInventoryGrids(data.inventory || {});
}

let currentInspectInvSlots = {};

function toggleEnderChestView() {
  const panel = document.getElementById('inspectEnderChestPanel');
  if (!panel) return;
  const isOpening = (panel.style.display === 'none' || !panel.style.display);
  panel.style.display = isOpening ? 'block' : 'none';
  if (isOpening) {
    MinecraftAudio.playChestOpen();
  } else {
    MinecraftAudio.playChestClose();
  }
}

function renderInventoryGrids(inv) {
  currentInspectInvSlots = {};
  const hotbar = Array.isArray(inv.hotbar) ? inv.hotbar : [];
  const main = Array.isArray(inv.main) ? inv.main : [];
  const armor = inv.armor || {};
  const offhand = inv.offhand || null;
  const enderItems = Array.isArray(inv.ender_chest) ? inv.ender_chest : [];
  const enderCount = enderItems.filter(Boolean).length;
  const totalItems = inv.total_items ?? 0;

  const countBadge = document.getElementById('inspectInvCountLabel');
  if (countBadge) {
    countBadge.textContent = currentLang === 'ru'
      ? `Занято слотов: ${totalItems}`
      : `Slots used: ${totalItems}`;
  }

  const armorSlots = [
    { key: 'helmet', slot: 103, label: currentLang === 'ru' ? 'Шлем' : 'Helmet', iconFile: 'empty_armor_slot_helmet.png', item: armor.helmet },
    { key: 'chestplate', slot: 102, label: currentLang === 'ru' ? 'Нагрудник' : 'Chestplate', iconFile: 'empty_armor_slot_chestplate.png', item: armor.chestplate },
    { key: 'leggings', slot: 101, label: currentLang === 'ru' ? 'Поножи' : 'Leggings', iconFile: 'empty_armor_slot_leggings.png', item: armor.leggings },
    { key: 'boots', slot: 100, label: currentLang === 'ru' ? 'Ботинки' : 'Boots', iconFile: 'empty_armor_slot_boots.png', item: armor.boots }
  ];

  const armorContainer = document.getElementById('inspectArmorGrid');
  if (armorContainer) {
    armorContainer.innerHTML = armorSlots.map(cfg => {
      const slotKey = `armor_${cfg.key}`;
      currentInspectInvSlots[slotKey] = { slotTitle: cfg.label, item: cfg.item };
      const placeholderImg = `<img src="/static/icons/${cfg.iconFile}" alt="${escapeHtml(cfg.label)}">`;
      return buildSlotHtml(slotKey, null, cfg.label, cfg.item, placeholderImg);
    }).join('');
  }

  const enderSlotKey = 'ender_chest';
  const enderTitle = currentLang === 'ru' ? 'Эндер-сундук' : 'Ender Chest';
  const enderChestItem = {
    id: 'minecraft:ender_chest',
    name: enderTitle,
    is_vanilla: true,
    count: enderCount,
    is_ender_chest: true,
    items: enderItems
  };
  currentInspectInvSlots[enderSlotKey] = { slotTitle: enderTitle, item: enderChestItem };

  const enderContainer = document.getElementById('inspectEnderChestSlot');
  if (enderContainer) {
    enderContainer.innerHTML = `
      <div class="mc-slot filled vanilla"
           id="slot_${enderSlotKey}"
           title="${escapeHtml(enderTitle)} (${enderCount} / 27)"
           onclick="onSlotClicked('${enderSlotKey}'); toggleEnderChestView();"
           onmouseenter="onSlotHovered('${enderSlotKey}')">
        <img src="/static/icons/ender_chest.png" class="mc-item-img" alt="${escapeHtml(enderTitle)}">
      </div>
    `;
  }

  const offhandContainer = document.getElementById('inspectOffhandSlot');
  if (offhandContainer) {
    const offhandKey = 'armor_offhand';
    const offhandLabel = currentLang === 'ru' ? 'Вторая рука (Offhand)' : 'Offhand';
    currentInspectInvSlots[offhandKey] = { slotTitle: offhandLabel, item: offhand };
    const placeholderOffhand = `<img src="/static/icons/empty_armor_slot_shield.png" alt="${escapeHtml(offhandLabel)}">`;
    offhandContainer.innerHTML = buildSlotHtml(offhandKey, null, offhandLabel, offhand, placeholderOffhand);
  }

  const mainSlots = [];
  for (let i = 0; i < 27; i++) {
    const slotNum = i + 9;
    const slotKey = `main_${i}`;
    const item = main[i] || null;
    const slotLabel = currentLang === 'ru' ? `Основной инвентарь (слот ${slotNum})` : `Main Inventory (slot ${slotNum})`;
    currentInspectInvSlots[slotKey] = { slotTitle: slotLabel, item };
    mainSlots.push(buildSlotHtml(slotKey, slotNum, slotLabel, item));
  }
  const mainContainer = document.getElementById('inspectMainInvGrid');
  if (mainContainer) mainContainer.innerHTML = mainSlots.join('');

  const hotbarSlots = [];
  for (let i = 0; i < 9; i++) {
    const hotbarNum = i + 1;
    const slotKey = `hotbar_${i}`;
    const item = hotbar[i] || null;
    const slotLabel = currentLang === 'ru' ? `Хотбар (слот ${hotbarNum})` : `Hotbar (slot ${hotbarNum})`;
    currentInspectInvSlots[slotKey] = { slotTitle: slotLabel, item };
    hotbarSlots.push(buildSlotHtml(slotKey, hotbarNum, slotLabel, item));
  }
  const hotbarContainer = document.getElementById('inspectHotbarGrid');
  if (hotbarContainer) hotbarContainer.innerHTML = hotbarSlots.join('');

  const enderGridContainer = document.getElementById('inspectEnderGrid');
  if (enderGridContainer) {
    const enderSlots = [];
    for (let i = 0; i < 27; i++) {
      const slotKey = `ender_${i}`;
      const item = enderItems[i] || null;
      const slotLabel = currentLang === 'ru' ? `Эндер-сундук (слот ${i + 1})` : `Ender Chest (slot ${i + 1})`;
      currentInspectInvSlots[slotKey] = { slotTitle: slotLabel, item };
      enderSlots.push(buildSlotHtml(slotKey, i + 1, slotLabel, item));
    }
    enderGridContainer.innerHTML = enderSlots.join('');
  }
}

function getTextureSlug(rawName) {
  return rawName.toLowerCase().replace(/^minecraft:/, '').replace(/\s+/g, '_').trim();
}

function buildSlotHtml(slotKey, slotNum, slotTitle, item, placeholderIcon = null) {
  if (!item) {
    const ghostHtml = placeholderIcon ? `<span class="mc-ghost-icon">${placeholderIcon}</span>` : '';
    const emptyWord = currentLang === 'ru' ? 'Пусто' : 'Empty';
    return `
      <div class="mc-slot empty"
           id="slot_${slotKey}"
           title="${escapeHtml(slotTitle)}: ${emptyWord}"
           onclick="onSlotClicked('${slotKey}')"
           onmouseenter="onSlotHovered('${slotKey}')">
        ${ghostHtml}
      </div>
    `;
  }

  const itemId = String(item.id || '').trim();
  const isVanilla = item.is_vanilla !== false && (!itemId.includes(':') || itemId.startsWith('minecraft:'));
  const slug = getTextureSlug(itemId);
  const count = parseInt(item.count || 1, 10);
  const countBadge = count > 1 ? `<span class="mc-slot-count">${count}</span>` : '';
  const fullName = escapeHtml(`${item.name || itemId} (${itemId})${count > 1 ? ' x' + count : ''}`);

  let durabilityHtml = '';
  if (item.damage > 0) {
    let durPct = item.durability_pct;
    if (durPct == null) {
      const maxD = item.max_damage || (item.damage + 20);
      durPct = Math.max(0, Math.min(100, Math.round((1 - item.damage / maxD) * 100)));
    }
    const hue = Math.max(0, Math.min(120, Math.round(durPct * 1.2)));
    const barColor = `hsl(${hue}, 100%, 50%)`;
    durabilityHtml = `
      <div class="mc-durability-bar">
        <div class="mc-durability-fill" style="width: ${durPct}%; background-color: ${barColor};"></div>
      </div>
    `;
  }

  let itemContent = '';
  if (isVanilla) {
    itemContent = `
      <img src="/static/icons/${slug}.png"
           class="mc-item-img"
           alt="${escapeHtml(item.name || slug)}"
           onerror="this.onerror=null; this.src='/api/items/minecraft:${slug}/icon'; this.onerror=()=>{ this.src='https://assets.mcasset.cloud/1.20.2/assets/minecraft/textures/item/${slug}.png'; this.onerror=()=>{ this.style.display='none'; }; };">
    `;
  } else {
    const parts = itemId.split(':');
    const modNamespace = parts.length > 1 ? parts[0] : (item.namespace || 'MOD');
    const rawShort = parts.length > 1 ? parts[1].replace(/_/g, ' ') : (item.name || itemId);
    const shortName = item.name && item.name !== itemId ? item.name : rawShort;
    itemContent = `
      <div class="mc-mod-text">
        <span class="mc-mod-namespace">${escapeHtml(modNamespace)}</span>
        <span class="mc-mod-name">${escapeHtml(shortName)}</span>
      </div>
    `;
  }

  const hasCountClass = (!isVanilla && count > 1) ? ' has-count' : '';

  return `
    <div class="mc-slot filled ${isVanilla ? 'vanilla' : 'modded'}${hasCountClass}"
         id="slot_${slotKey}"
         title="${fullName}"
         onclick="onSlotClicked('${slotKey}')"
         onmouseenter="onSlotHovered('${slotKey}')">
      ${itemContent}
      ${durabilityHtml}
      ${countBadge}
    </div>
  `;
}

function onItemIconError(img) {
  img.style.display = 'none';
}

function onSlotClicked(slotKey) {
  highlightSelectedSlot(slotKey);
  const data = currentInspectInvSlots[slotKey];
  if (data) {
    if (slotKey === 'ender_chest') {
      // toggleEnderChestView handles chest open/close sound
    } else if (data.item) {
      MinecraftAudio.playSlotClick();
    } else {
      MinecraftAudio.playClick();
    }
    showSlotDetails(data.slotTitle, data.item);
  }
}

function onSlotHovered(slotKey) {
  const data = currentInspectInvSlots[slotKey];
  if (data) {
    if (data.item) {
      MinecraftAudio.playSlotHover();
    }
    showSlotDetails(data.slotTitle, data.item);
  }
}

function highlightSelectedSlot(slotKey) {
  document.querySelectorAll('.mc-slot.active-selected').forEach(el => el.classList.remove('active-selected'));
  const el = document.getElementById(`slot_${slotKey}`);
  if (el) el.classList.add('active-selected');
}

function showSlotDetails(slotTitle, item) {
  const box = document.getElementById('inspectSelectedSlotInfo');
  if (!box) return;

  if (!item) {
    const emptySlotMsg = currentLang === 'ru' ? 'Слот пуст' : 'Empty slot';
    box.innerHTML = `
      <div class="d-flex align-items-center gap-2 text-muted small py-1">
        <i class="bx bx-radio-circle text-secondary fs-5"></i>
        <span><strong>${escapeHtml(slotTitle)}:</strong> ${emptySlotMsg}</span>
      </div>
    `;
    return;
  }

  const itemId = String(item.id || '').trim();
  const isVanilla = item.is_vanilla !== false && (!itemId.includes(':') || itemId.startsWith('minecraft:'));
  const slug = getTextureSlug(itemId);
  const parts = itemId.split(':');
  const namespace = parts.length > 1 ? parts[0] : (item.namespace || 'minecraft');
  const rawShort = parts.length > 1 ? parts[1].replace(/_/g, ' ') : (item.name || itemId);
  const itemName = item.name && item.name !== itemId ? item.name : rawShort;

  const tagBadge = isVanilla
    ? `<span class="badge bg-label-success">Vanilla</span>`
    : `<span class="badge bg-label-warning">${escapeHtml(namespace)}</span>`;

  let durabilityInfo = '';
  if (item.damage > 0) {
    const durWord = currentLang === 'ru' ? 'Прочность' : 'Durability';
    const dmgWord = currentLang === 'ru' ? 'Урон' : 'Damage';
    const durText = item.max_damage ? `${item.max_damage - item.damage} / ${item.max_damage}` : `${dmgWord}: ${item.damage}`;
    durabilityInfo = `<span class="badge bg-label-danger ms-1">${durWord}: ${escapeHtml(durText)}</span>`;
  }

  let previewIcon = '';
  if (item.is_ender_chest) {
    previewIcon = `<img src="/static/icons/ender_chest.png" alt="Ender Chest" class="mc-item-preview-img me-3">`;
  } else if (isVanilla) {
    previewIcon = `<img src="/static/icons/${slug}.png" alt="${escapeHtml(itemName)}" class="mc-item-preview-img me-3" onerror="this.onerror=null; this.src='/api/items/minecraft:${slug}/icon'; this.onerror=()=>{ this.style.display='none'; }">`;
  } else {
    previewIcon = `<div class="mc-item-preview-box me-3"><i class="bx bx-cube-alt text-warning"></i></div>`;
  }

  let extraActions = '';
  if (item.is_ender_chest) {
    const stored = item.items ? item.items.filter(Boolean).length : 0;
    const toggleText = currentLang === 'ru'
      ? `Показать/скрыть содержимое (${stored} / 27)`
      : `Show/hide contents (${stored} / 27)`;
    extraActions = `
      <div class="mt-2">
        <button type="button" class="btn btn-xs btn-outline-info" onclick="toggleEnderChestView()">
          <i class="bx bx-folder-open me-1"></i>${toggleText}
        </button>
      </div>
    `;
  }

  const stackWord = item.is_ender_chest
    ? (currentLang === 'ru' ? 'занято слотов' : 'slots used')
    : (currentLang === 'ru' ? 'в стаке' : 'in stack');

  box.innerHTML = `
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
      <div class="d-flex align-items-center">
        ${previewIcon}
        <div>
          <div class="d-flex align-items-center gap-2">
            <span class="fw-bold text-white fs-6">${escapeHtml(itemName)}</span>
            ${tagBadge}
            ${durabilityInfo}
          </div>
          <div class="d-flex align-items-center gap-2 small text-muted mt-1">
            <span>ID: <code class="text-info">${escapeHtml(itemId)}</code></span>
            <span>·</span>
            <span>${escapeHtml(slotTitle)}</span>
          </div>
          ${extraActions}
        </div>
      </div>
      <div class="text-end">
        <span class="fs-5 fw-bold text-white font-mono">${item.is_ender_chest ? `${item.count}/27` : (item.count || 1)}</span>
        <small class="text-muted d-block" style="font-size: 11px;">${stackWord}</small>
      </div>
    </div>
  `;
}



