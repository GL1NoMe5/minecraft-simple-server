import os
import subprocess
import sys
from pathlib import Path
import unittest

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app

class TestMinecraftThemeAndVisuals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.static_dir = BASE_DIR / "app" / "static"
        cls.backup_dir = BASE_DIR / "backups" / "ui_original_2026-10-17" / "static"

    def test_backup_folder_exists_and_complete(self):
        """Проверка существования резервной копии оригинального интерфейса."""
        self.assertTrue(self.backup_dir.exists(), "Резервная копия backups/ui_original_2026-10-17/static должна существовать")
        backup_index = self.backup_dir / "index.html"
        backup_js = self.backup_dir / "app_logic.js"
        self.assertTrue(backup_index.exists(), "Оригинальный index.html должен присутствовать в бэкапе")
        self.assertTrue(backup_js.exists(), "Оригинальный app_logic.js должен присутствовать в бэкапе")
        self.assertGreater(backup_index.stat().st_size, 10000, "Бэкап index.html не должен быть пустым")

    def test_theme_assets_exist_on_disk(self):
        """Проверка физического наличия CSS темы, JS движка частиц и локальных шрифтов."""
        css_file = self.static_dir / "assets" / "css" / "minecraft-theme.css"
        js_file = self.static_dir / "assets" / "js" / "minecraft-theme.js"
        fonts_dir = self.static_dir / "assets" / "vendor" / "fonts" / "pixelify"
        
        self.assertTrue(css_file.exists(), "minecraft-theme.css должен существовать")
        self.assertGreater(css_file.stat().st_size, 5000, "minecraft-theme.css должен содержать правила стилей")

        self.assertTrue(js_file.exists(), "minecraft-theme.js должен существовать")
        self.assertGreater(js_file.stat().st_size, 1000, "minecraft-theme.js должен содержать код")

        for font in ["pixelify-cyrillic.woff2", "pixelify-latin.woff2", "pixelify-latin-ext.woff2"]:
            f_path = fonts_dir / font
            self.assertTrue(f_path.exists(), f"Шрифт {font} должен присутствовать локально для офлайн работы")
            self.assertGreater(f_path.stat().st_size, 1000)

    def test_block_textures_exist(self):
        """Проверка наличия текстур блоков Minecraft для фона и панелей."""
        icons_dir = self.static_dir / "icons"
        textures = ["dirt.png", "deepslate.png", "oak_planks.png", "spruce_planks.png", "stone_bricks.png", "stone.png"]
        for tex in textures:
            t_path = icons_dir / tex
            self.assertTrue(t_path.exists(), f"Текстура {tex} должна быть доступна в icons/")

    def test_fastapi_endpoints_serve_theme_files(self):
        """Проверка отдачи файлов темы через эндпоинты FastAPI с кодом 200 OK."""
        res_css = self.client.get("/assets/css/minecraft-theme.css")
        self.assertEqual(res_css.status_code, 200)
        self.assertIn("--mc-font", res_css.text)

        res_js = self.client.get("/assets/js/minecraft-theme.js")
        self.assertEqual(res_js.status_code, 200)
        self.assertIn("MinecraftTheme", res_js.text)

        res_font = self.client.get("/static/assets/vendor/fonts/pixelify/pixelify-cyrillic.woff2")
        self.assertEqual(res_font.status_code, 200)

        res_tex = self.client.get("/static/icons/dirt.png")
        self.assertEqual(res_tex.status_code, 200)

    def test_index_html_contains_minecraft_components(self):
        """Проверка разметки index.html на наличие классов mc-theme, mc-fx, канваса частиц и кнопок."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text

        self.assertIn("mc-theme", html, "HTML должен содержать класс mc-theme")
        self.assertIn("mc-fx", html, "HTML должен содержать класс mc-fx")
        self.assertIn("minecraft-theme.css", html, "index.html должен подключать minecraft-theme.css")
        self.assertIn("minecraft-theme.js", html, "index.html должен подключать minecraft-theme.js")
        self.assertIn("mcParticles", html, "index.html должен содержать canvas #mcParticles")
        self.assertIn("mcSplash", html, "index.html должен содержать элемент #mcSplash для всплывающего текста")
        self.assertIn("themeToggleBtn", html, "В навигации должна присутствовать кнопка переключения темы")
        self.assertIn("btnFxToggle", html, "В навигации должна присутствовать кнопка переключения эффектов FX")

    def test_javascript_syntax_validity(self):
        """Проверка синтаксиса minecraft-theme.js через node -c."""
        js_file = self.static_dir / "assets" / "js" / "minecraft-theme.js"
        try:
            res = subprocess.run(["node", "-c", str(js_file)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Синтаксическая ошибка в {js_file.name}: {res.stderr}")
        except FileNotFoundError:
            # Если node не установлен в среде, пропускаем тест
            pass

if __name__ == "__main__":
    unittest.main()
