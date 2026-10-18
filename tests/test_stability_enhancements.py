import unittest
import time
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.server_manager import server_manager, ServerManager

class TestStabilityEnhancements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_status_instant_response(self):
        """Проверка того, что get_status возвращает кэшированные метрики без блокировок."""
        start = time.perf_counter()
        res = self.client.get("/api/status")
        elapsed = time.perf_counter() - start
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertIn("stats", data)
        self.assertIn("cpu_percent", data["stats"])
        self.assertIn("memory_mb", data["stats"])
        self.assertIn("memory_str", data["stats"])
        self.assertLess(elapsed, 0.5, "get_status должен возвращаться быстро без блокирующего сканирования")

    def test_metrics_worker_lifecycle(self):
        """Проверка работы фонового потока метрик ServerManager."""
        sm = ServerManager()
        self.assertIsNotNone(sm._metrics_thread)
        self.assertTrue(sm._metrics_thread.is_alive())
        # Проверяем остановку
        sm._stop_metrics_worker()
        self.assertIsNone(sm._metrics_thread)

    def test_graceful_shutdown_when_stopped(self):
        """Проверка graceful_shutdown при незапущенном сервере."""
        sm = ServerManager()
        res = sm.graceful_shutdown(timeout=1)
        self.assertTrue(res.get("success"))
        self.assertEqual(sm.status, "STOPPED")
        sm._stop_metrics_worker()

    def test_websocket_history_batch(self):
        """Проверка отдачи истории через WebSocket единым пакетом history."""
        # Заполняем историю тестовыми строками
        server_manager.log_history.clear()
        server_manager.log_history.append("[Test] Line 1")
        server_manager.log_history.append("[Test] Line 2")

        with self.client.websocket_connect("/ws/console") as ws:
            first_msg = ws.receive_json()
            self.assertEqual(first_msg.get("type"), "history")
            self.assertIsInstance(first_msg.get("data"), list)
            self.assertIn("[Test] Line 1", first_msg["data"])
            self.assertIn("[Test] Line 2", first_msg["data"])

    def test_delete_world_endpoint(self):
        """Проверка эндпоинта DELETE /api/world."""
        res = self.client.delete("/api/world")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("success", data)

    def test_index_html_contains_audio_and_modal(self):
        """Проверка наличия кнопки звука и модального окна в index.html."""
        index_path = BASE_DIR / "app" / "static" / "index.html"
        self.assertTrue(index_path.exists())
        content = index_path.read_text(encoding="utf-8")
        self.assertIn('id="btnAudioToggle"', content)
        self.assertIn('id="confirmDeleteWorldModal"', content)
        self.assertIn('static/app_logic.js?v=', content)

    def test_app_logic_contains_audio_engine_and_dom_limit(self):
        """Проверка наличия MinecraftAudio и MAX_CONSOLE_LINES в app_logic.js."""
        js_path = BASE_DIR / "app" / "static" / "app_logic.js"
        self.assertTrue(js_path.exists())
        content = js_path.read_text(encoding="utf-8")
        self.assertIn('const MinecraftAudio', content)
        self.assertIn('MAX_CONSOLE_LINES', content)
        self.assertIn('appendConsoleLogsBatch', content)
        self.assertIn('executeDeleteWorld', content)

if __name__ == "__main__":
    unittest.main()
