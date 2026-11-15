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
        """Проверка эндпоинта DELETE /api/world в изолированной временной папке (не трогает реальный мир)."""
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_world = Path(tmp_dir) / "world"
            dummy_world.mkdir(parents=True, exist_ok=True)
            (dummy_world / "level.dat").write_bytes(b"test")
            with patch("app.server_manager.SERVER_DIR", Path(tmp_dir)):
                res = self.client.delete("/api/world")
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertIn("success", data)
                self.assertTrue(data.get("success"))
                self.assertFalse(dummy_world.exists())

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

    def test_quiet_polling_filter(self):
        """Проверка фильтрации спама GET /api/status в логах uvicorn.access с сохранением важных запросов и ошибок."""
        import logging
        from app.main import QuietPollingFilter, install_quiet_access_log_filter

        flt = QuietPollingFilter()

        def make_record(method: str, path: str, status: int) -> logging.LogRecord:
            return logging.LogRecord(
                name="uvicorn.access",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg='%s - "%s %s HTTP/%s" %d',
                args=("127.0.0.1:50896", method, path, "1.1", status),
                exc_info=None,
            )

        # Должны подавляться (частый опрос и статика без ошибок)
        self.assertFalse(flt.filter(make_record("GET", "/api/status", 200)))
        self.assertFalse(flt.filter(make_record("GET", "/api/players?refresh=false", 200)))
        self.assertFalse(flt.filter(make_record("GET", "/static/app_logic.js?v=1", 200)))
        self.assertFalse(flt.filter(make_record("GET", "/assets/js/main.js", 304)))
        self.assertFalse(flt.filter(make_record("GET", "/api/items/eternal:sword/icon", 404)))

        # Должны оставаться в консоли (действия, страница /, ошибки сервера)
        self.assertTrue(flt.filter(make_record("GET", "/", 200)))
        self.assertTrue(flt.filter(make_record("POST", "/api/server/start", 200)))
        self.assertTrue(flt.filter(make_record("POST", "/api/server/command", 200)))
        self.assertTrue(flt.filter(make_record("GET", "/api/status", 500)))
        self.assertTrue(flt.filter(make_record("GET", "/api/items/eternal:sword/icon", 500)))

        # Проверка идемпотентности установки фильтра
        install_quiet_access_log_filter()
        install_quiet_access_log_filter()
        access_logger = logging.getLogger("uvicorn.access")
        matching = [f for f in access_logger.filters if isinstance(f, QuietPollingFilter)]
        self.assertEqual(len(matching), 1)

    def test_windows_console_configuration_safe(self):
        """Проверка безопасного выполнения configure_windows_console() из run.py."""
        from run import configure_windows_console
        configure_windows_console()

    def test_config_mtime_cache(self):
        """Проверка mtime-кэширования load_config() без лишнего чтения диска на каждый /api/status."""
        from unittest.mock import patch
        import app.config as cfg_mod

        first = cfg_mod.load_config()
        with patch("builtins.open", side_effect=AssertionError("Disk open should not be called on cache hit")):
            second = cfg_mod.load_config()
        self.assertEqual(first.model_dump(), second.model_dump())

    def test_forge_args_cache_and_invalidation(self):
        """Проверка кэширования find_forge_args_file() и сброса invalidate_core_cache()."""
        sm = ServerManager()
        try:
            sm.invalidate_core_cache()
            self.assertFalse(sm._forge_args_cached_valid)
            _ = sm.find_forge_args_file()
            self.assertTrue(sm._forge_args_cached_valid)
            sm.invalidate_core_cache()
            self.assertFalse(sm._forge_args_cached_valid)
        finally:
            sm._stop_metrics_worker()

    def test_perform_autosave_write_thread_safe(self):
        """Проверка потокобезопасной записи save-all через _perform_autosave_write."""
        from unittest.mock import MagicMock, patch

        sm = ServerManager()
        try:
            self.assertIsNone(sm._perform_autosave_write())

            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            mock_proc.pid = 12345
            mock_proc.stdin = MagicMock()
            sm.process = mock_proc
            sm.status = "RUNNING"

            mock_ps = MagicMock()
            mock_ps.is_running.return_value = True
            with patch("psutil.Process", return_value=mock_ps):
                ts = sm._perform_autosave_write()
            self.assertIsNotNone(ts)
            writes = [c.args[0] for c in mock_proc.stdin.write.call_args_list]
            self.assertIn("save-all\n", writes)
            self.assertTrue(any("say §a[Server] World saved!" in w for w in writes))
        finally:
            sm.process = None
            sm.status = "STOPPED"
            sm._stop_metrics_worker()

    def test_broadcast_log_evicts_broken_socket(self):
        """Проверка удаления зависшего/ошибочного WebSocket из connected_websockets."""
        import asyncio

        class BrokenWS:
            async def send_text(self, payload: str):
                raise RuntimeError("socket closed")

        sm = ServerManager()
        try:
            bad = BrokenWS()
            sm.connected_websockets.add(bad)
            asyncio.run(sm.broadcast_log("[Test] broadcast"))
            self.assertNotIn(bad, sm.connected_websockets)
        finally:
            sm._stop_metrics_worker()

    def test_app_logic_syntax_and_non_overlapping_poll(self):
        """Проверка синтаксиса app_logic.js через Node.js и защиты от наложения /api/status."""
        import shutil
        import subprocess

        js_path = BASE_DIR / "app" / "static" / "app_logic.js"
        content = js_path.read_text(encoding="utf-8")
        self.assertIn("isPollingStatus", content)
        self.assertIn("AbortController", content)
        self.assertIn("oldWs.onclose = null", content)

        if shutil.which("node"):
            res = subprocess.run(["node", "-c", str(js_path)], capture_output=True, text=True, cwd=str(BASE_DIR))
            self.assertEqual(res.returncode, 0, f"JavaScript syntax error: {res.stderr}")

if __name__ == "__main__":
    unittest.main()
