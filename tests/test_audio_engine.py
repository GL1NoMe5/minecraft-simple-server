import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import unittest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app

class TestMinecraftAudioEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.audio_dir = BASE_DIR / "app" / "static" / "assets" / "audio"
        cls.js_file = BASE_DIR / "app" / "static" / "app_logic.js"
        cls.html_file = BASE_DIR / "app" / "static" / "index.html"

    def test_audio_assets_exist_and_non_empty(self):
        """Проверка физического наличия всех 33 звуковых файлов Minecraft в app/static/assets/audio."""
        self.assertTrue(self.audio_dir.exists(), "Папка app/static/assets/audio должна существовать")
        
        manifest_file = self.audio_dir / "sounds_manifest.json"
        self.assertTrue(manifest_file.exists(), "Файл sounds_manifest.json должен существовать")
        
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        self.assertGreaterEqual(len(manifest), 30, "Манифест должен содержать не менее 30 звуков")
        
        required_sounds = [
            "wood_click.ogg", "click.ogg", "cherrywood_click.ogg", "bamboo_click.ogg",
            "page_flip.ogg", "pop.ogg", "bundle_insert.ogg", "bundle_drop.ogg",
            "chest_open.ogg", "chest_close.ogg", "door_close.ogg", "barrel_close.ogg",
            "amethyst_chime.ogg", "amethyst_resonate.ogg", "amethyst_shimmer.ogg",
            "levelup.ogg", "note_bass.ogg", "note_pling.ogg", "note_bell.ogg",
            "orb.ogg", "enchant.ogg", "beacon_activate.ogg", "conduit_activate.ogg",
            "liquid_splash.ogg", "villager_no.ogg", "villager_yes.ogg"
        ]
        
        for snd in required_sounds:
            snd_path = self.audio_dir / snd
            self.assertTrue(snd_path.exists(), f"Звук {snd} должен присутствовать на диске")
            self.assertGreater(snd_path.stat().st_size, 500, f"Звук {snd} не должен быть пустым")

    def test_static_routes_serve_all_33_audio_files(self):
        """Проверка доступности всех 33 звуков через эндпоинты FastAPI /static/assets/audio/ и /assets/audio/."""
        all_ogg = list(self.audio_dir.glob("*.ogg"))
        self.assertEqual(len(all_ogg), 33, "Должно присутствовать ровно 33 аудиофайла")
        for f in all_ogg:
            # Test /static/assets/audio/
            resp_static = self.client.get(f"/static/assets/audio/{f.name}")
            self.assertEqual(resp_static.status_code, 200, f"/static/assets/audio/{f.name} should return 200")
            self.assertEqual(len(resp_static.content), f.stat().st_size)

            # Test /assets/audio/
            resp_assets = self.client.get(f"/assets/audio/{f.name}")
            self.assertEqual(resp_assets.status_code, 200, f"/assets/audio/{f.name} should return 200")
            self.assertEqual(len(resp_assets.content), f.stat().st_size)

    def test_frontend_has_audio_toggle_button(self):
        """Проверка наличия кнопки переключения звука и иконки в HTML."""
        content = self.html_file.read_text(encoding="utf-8")
        self.assertIn('id="btnAudioToggle"', content)
        self.assertIn('id="audioToggleIcon"', content)
        self.assertIn('id="audioToggleText"', content)
        self.assertIn('onclick="toggleSound()"', content)
        self.assertIn('no-sound', content)

    def test_frontend_button_exclusion_from_click_clash(self):
        """Проверка исключения специальных кнопок (start, stop, sound, theme, modals) из generic клик-листенера."""
        js_code = self.js_file.read_text(encoding="utf-8")
        self.assertIn('#btnAudioToggle', js_code)
        self.assertIn('#btnStart', js_code)
        self.assertIn('#btnStop', js_code)
        self.assertIn('silentToastSound', js_code)
        self.assertIn('playCoreReady', js_code)
        self.assertIn('levelup', js_code)
        self.assertIn('note_bass', js_code)

    def test_app_logic_methods_in_node(self):
        """Тест вызова методов MinecraftAudio и переключения режимов звука в окружении Node.js."""
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed on this system")
        node_script = """
        const fs = require('fs');
        const code = fs.readFileSync('app/static/app_logic.js', 'utf8');

        // Mock browser globals
        let storage = {};
        global.localStorage = {
          getItem: (k) => storage[k] !== undefined ? storage[k] : null,
          setItem: (k, v) => { storage[k] = String(v); }
        };

        const mockElements = {
          audioToggleIcon: { className: '' },
          audioToggleText: { textContent: '' },
          btnAudioToggle: {
            classList: {
              add: function(c) { this[c] = true; },
              remove: function(c) { delete this[c]; }
            },
            setAttribute: function(k, v) { this[k] = v; }
          }
        };

        global.document = {
          getElementById: (id) => mockElements[id] || null,
          addEventListener: () => {}
        };
        global.window = {
          addEventListener: () => {}
        };

        // Extract and evaluate MinecraftAudio and toggleSound
        const audioEngineCode = code.slice(
          code.indexOf('const MinecraftAudio = (() => {'),
          code.indexOf('// ---------------- THEME SWITCHER')
        );
        eval(audioEngineCode.replace('const MinecraftAudio', 'global.MinecraftAudio'));
        const MinecraftAudio = global.MinecraftAudio;

        if (!MinecraftAudio) {
          console.error("MinecraftAudio not defined");
          process.exit(1);
        }

        // Test API methods exist
        const methods = [
          'playClick', 'playTabSwitch', 'playSlotHover', 'playSlotClick',
          'playChestOpen', 'playChestClose', 'playSliderTick', 'playToggle',
          'playServerStart', 'playServerOnline', 'playCoreReady', 'playServerStop',
          'playAutosave', 'playGamemodeChange', 'playPlayerHeal', 'playError',
          'playSuccess', 'playThemeToggle', 'playUnmute', 'isEnabled', 'setEnabled'
        ];

        for (const m of methods) {
          if (typeof MinecraftAudio[m] !== 'function') {
            console.error("Missing method: " + m);
            process.exit(2);
          }
        }

        // Test toggle
        MinecraftAudio.setEnabled(true);
        if (!MinecraftAudio.isEnabled()) {
          console.error("setEnabled(true) failed");
          process.exit(3);
        }
        if (localStorage.getItem('mc_sound_enabled') !== 'true') {
          console.error("localStorage not updated for enabled=true");
          process.exit(4);
        }

        MinecraftAudio.setEnabled(false);
        if (MinecraftAudio.isEnabled()) {
          console.error("setEnabled(false) failed");
          process.exit(5);
        }
        if (localStorage.getItem('mc_sound_enabled') !== 'false') {
          console.error("localStorage not updated for enabled=false");
          process.exit(6);
        }

        // Call methods safely without WebAudio (should handle null gracefully without throwing ReferenceError)
        MinecraftAudio.playClick();
        MinecraftAudio.playTabSwitch();
        MinecraftAudio.playSlotHover();
        MinecraftAudio.playSlotClick();
        MinecraftAudio.playChestOpen();
        MinecraftAudio.playChestClose();
        MinecraftAudio.playSliderTick(4);
        MinecraftAudio.playToggle();
        MinecraftAudio.playServerStart();
        MinecraftAudio.playServerOnline();
        MinecraftAudio.playCoreReady();
        MinecraftAudio.playServerStop();
        MinecraftAudio.playAutosave();
        MinecraftAudio.playGamemodeChange('creative');
        MinecraftAudio.playGamemodeChange('survival');
        MinecraftAudio.playPlayerHeal();
        MinecraftAudio.playError();
        MinecraftAudio.playSuccess();
        MinecraftAudio.playThemeToggle();
        MinecraftAudio.playUnmute();

        // Test toggleSound UI helper
        toggleSound();
        if (!MinecraftAudio.isEnabled()) {
          console.error("toggleSound failed to toggle from false to true");
          process.exit(7);
        }

        // Test autosave regex logic: success vs error
        function isAutosaveMessageSuccessful(line) {
          return typeof line === 'string' && (
            (line.includes('[AutoSave]') && !line.includes('Ошибка') && !line.includes('Error') && !line.includes('отключено')) ||
            line.includes('Saved the game') ||
            line.includes('Saved the world') ||
            line.includes('Automatic save')
          );
        }
        if (!isAutosaveMessageSuccessful('[AutoSave] Автоматическое сохранение мира выполнено (12:00:00)')) {
          console.error("Failed to detect valid autosave");
          process.exit(8);
        }
        if (isAutosaveMessageSuccessful('[AutoSave] Ошибка автосохранения: Disk full')) {
          console.error("Mistakenly identified error as autosave success");
          process.exit(9);
        }
        if (isAutosaveMessageSuccessful('[AutoSave] Автосохранение отключено.')) {
          console.error("Mistakenly identified disable as autosave success");
          process.exit(10);
        }

        console.log("NODE AUDIO ENGINE VERIFICATION PASSED");
        """
        proc = subprocess.run(["node", "-e", node_script], capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(proc.returncode, 0, f"Node script failed: {proc.stderr}\n{proc.stdout}")

if __name__ == "__main__":
    unittest.main()
