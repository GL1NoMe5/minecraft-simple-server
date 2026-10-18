import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import unittest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.server_manager import server_manager


class TestI18nAndInventoryThemeFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.static_dir = BASE_DIR / "app" / "static"
        cls.app_logic_file = cls.static_dir / "app_logic.js"
        cls.theme_css_file = cls.static_dir / "assets" / "css" / "minecraft-theme.css"
        cls.index_html_file = cls.static_dir / "index.html"

    def test_world_save_chat_announcement_is_english(self):
        """Проверка отправки объявления о сохранении мира в игровой чат на английском языке [Server] World saved!"""
        for cmd in ["save-all", "/save-all", "save-all flush", "/save-all flush"]:
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.stdin = MagicMock()

            with patch.object(server_manager, "process", mock_proc):
                res = server_manager.send_command(cmd)
                self.assertTrue(res.get("success"), f"Команда {cmd} должна завершаться успешно")

                writes = [call.args[0] for call in mock_proc.stdin.write.call_args_list]
                say_calls = [w for w in writes if w.startswith("say ")]
                self.assertTrue(len(say_calls) > 0, f"Команда say должна быть отправлена в stdin при {cmd}")
                self.assertIn("[Server] World saved!", say_calls[0])
                self.assertNotIn("[Сервер] Мир успешно сохранен!", say_calls[0])

    def test_autosave_say_cmd_source_is_english(self):
        """Проверка исходного кода server_manager.py: autosave loop использует английский чат."""
        sm_file = BASE_DIR / "app" / "server_manager.py"
        content = sm_file.read_text(encoding="utf-8")
        self.assertNotIn("say §a[Сервер] Мир успешно сохранен!", content)
        self.assertIn("say §a[Server] World saved!", content)

    def test_translate_server_message_in_node(self):
        """Проверка работы функции translateServerMessage в app_logic.js через Node.js."""
        start_marker = "function translateServerMessage(msg) {"
        end_marker = "\nfunction toggleLanguage()"
        content = self.app_logic_file.read_text(encoding="utf-8")
        self.assertIn(start_marker, content)
        self.assertIn(end_marker, content)
        fn_code = content[content.index(start_marker):content.index(end_marker)]

        js_runner = f"""
        let currentLang = 'en';
        {fn_code}

        if (translateServerMessage('Сервер успешно запущен') !== 'Server successfully started') {{
            console.error('Failed to translate: Сервер успешно запущен');
            process.exit(1);
        }}
        if (translateServerMessage('Сервер уже запущен') !== 'Server is already running') {{
            console.error('Failed to translate: Сервер уже запущен');
            process.exit(2);
        }}
        if (translateServerMessage('Сервер уже остановлен') !== 'Server is already stopped') {{
            console.error('Failed to translate: Сервер уже остановлен');
            process.exit(3);
        }}
        const errMsg = translateServerMessage('Ошибка запуска процесса: Out of memory');
        if (!errMsg.includes('Server process startup error: Out of memory')) {{
            console.error('Failed to translate startup error regex:', errMsg);
            process.exit(4);
        }}
        currentLang = 'ru';
        if (translateServerMessage('Сервер успешно запущен') !== 'Сервер успешно запущен') {{
            console.error('Russian mode corrupted: translated when it should not');
            process.exit(5);
        }}
        currentLang = 'en';
        if (translateServerMessage(null) !== null) process.exit(6);
        if (translateServerMessage('') !== '') process.exit(7);
        if (translateServerMessage('Already English text') !== 'Already English text') process.exit(8);
        if (translateServerMessage('Интервал автосохранения установлен на 600 сек.') !== 'Autosave interval set to 600 sec.') process.exit(9);
        if (translateServerMessage('Команда остановки отправлена') !== 'Stop command sent') process.exit(10);
        if (translateServerMessage('Сервер Minecraft штатно остановлен') !== 'Minecraft server stopped gracefully') process.exit(11);
        if (translateServerMessage('Режим игрока Alex изменен на Survival') !== 'Player Alex gamemode changed to Survival') process.exit(12);
        if (!translateServerMessage("Java не найдена по пути '/usr/bin/java'").includes("Java not found at path '/usr/bin/java'")) process.exit(13);
        if (!translateServerMessage("Файл ядра 'server.jar' не найден").includes("Server core file 'server.jar'")) process.exit(14);
        if (translateServerMessage('Игрок Steve телепортирован к Alex') !== 'Teleported Steve to Alex') process.exit(15);
        if (translateServerMessage('Игрок Steve кикнут с сервера') !== 'Player Steve kicked from server') process.exit(16);
        if (translateServerMessage('Здоровье и сытость игрока Steve восстановлены') !== 'Restored health and hunger for Steve') process.exit(17);

        console.log('NODE I18N VERIFICATION PASSED');
        """
        proc = subprocess.run(["node"], input=js_runner, capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(proc.returncode, 0, f"Node script failed: {proc.stderr}\n{proc.stdout}")

    def test_show_toast_resolution_in_node(self):
        """Проверка разрешения заголовка и тела уведомлений showToast для EN и RU режимов."""
        content = self.app_logic_file.read_text(encoding="utf-8")
        start_marker = "function translateServerMessage(msg) {"
        end_marker = "\nfunction toggleLanguage()"
        fn_code = content[content.index(start_marker):content.index(end_marker)]

        js_runner = f"""
        let currentLang = 'en';
        const I18N = {{
            en: {{ toast_notice: 'Notice', toast_success: 'Success', toast_error: 'Error', toast_warning: 'Warning' }},
            ru: {{ toast_notice: 'Уведомление', toast_success: 'Успех', toast_error: 'Ошибка', toast_warning: 'Внимание' }}
        }};
        function t(key) {{ return (I18N[currentLang] || I18N.en)[key] || key; }}

        {fn_code}

        function resolveToast(titleOrMessage, maybeMessage, type = 'info') {{
            let title = t('toast_notice');
            let message = titleOrMessage;
            if (maybeMessage !== undefined) {{
                title = titleOrMessage;
                message = maybeMessage;
            }}
            if (title === 'Успех' || title === 'Success') title = t('toast_success');
            if (title === 'Ошибка' || title === 'Error') title = t('toast_error');
            if (title === 'Внимание' || title === 'Warning') title = t('toast_warning');
            if (title === 'Уведомление' || title === 'Notice') title = t('toast_notice');
            title = translateServerMessage(title);
            message = translateServerMessage(message);
            return {{ title, message }};
        }}

        // 1. Single argument showToast("Сервер успешно запущен") in EN
        currentLang = 'en';
        const res1 = resolveToast('Сервер успешно запущен');
        if (res1.title !== 'Notice' || res1.message !== 'Server successfully started') {{
            console.error('Test 1 failed:', res1);
            process.exit(1);
        }}

        // 2. Two arguments showToast(t('toast_notice'), "Сервер успешно запущен") in EN
        const res2 = resolveToast(t('toast_notice'), 'Сервер успешно запущен');
        if (res2.title !== 'Notice' || res2.message !== 'Server successfully started') {{
            console.error('Test 2 failed:', res2);
            process.exit(2);
        }}

        // 3. In RU mode, showToast("Сервер успешно запущен")
        currentLang = 'ru';
        const res3 = resolveToast('Сервер успешно запущен');
        if (res3.title !== 'Уведомление' || res3.message !== 'Сервер успешно запущен') {{
            console.error('Test 3 failed:', res3);
            process.exit(3);
        }}

        console.log('SHOW TOAST NODE VERIFICATION PASSED');
        """
        proc = subprocess.run(["node"], input=js_runner, capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(proc.returncode, 0, f"Node script failed: {proc.stderr}\n{proc.stdout}")

    def test_inventory_dark_mode_css_rules(self):
        """Проверка наличия стилей адаптации фона и слотов инвентаря под темную тему."""
        css_content = self.theme_css_file.read_text(encoding="utf-8")
        index_content = self.index_html_file.read_text(encoding="utf-8")

        for src, name in [(css_content, "minecraft-theme.css"), (index_content, "index.html")]:
            self.assertIn(".dark-style .mc-inventory-panel", src, f"{name} must contain .dark-style .mc-inventory-panel")
            self.assertIn("#23242b", src, f"{name} must use dark container background #23242b")
            self.assertIn(".dark-style .mc-slot", src, f"{name} must style slots for dark theme")
            self.assertIn("#17181c", src, f"{name} must style dark slots background #17181c")

    def test_inventory_light_mode_preserved(self):
        """Проверка сохранения классического светло-серого цвета #c6c6c6 в светлой теме."""
        css_content = self.theme_css_file.read_text(encoding="utf-8")
        index_content = self.index_html_file.read_text(encoding="utf-8")

        self.assertIn(".mc-inventory-panel", css_content)
        self.assertIn("#c6c6c6", css_content)
        self.assertIn("#c6c6c6", index_content)


if __name__ == "__main__":
    unittest.main()
