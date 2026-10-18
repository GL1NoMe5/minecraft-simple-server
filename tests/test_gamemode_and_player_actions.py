import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.server_manager import server_manager


class TestGamemodeAndPlayerActions(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_player_action_gamemode_with_value_parameter(self):
        """Regression test for the screenshot bug: frontend sends value instead of mode."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()

        with patch.object(server_manager, "process", mock_proc):
            with patch.object(server_manager, "send_command", return_value={"success": True, "message": "Команда отправлена"}) as mock_cmd:
                with server_manager.lock:
                    server_manager.online_players["Alex"] = {"gamemode": "survival", "ping": 10}

                # Send request exactly as frontend previously sent: with 'value'
                res = self.client.post("/api/players/action", json={
                    "action": "gamemode",
                    "player": "Alex",
                    "value": "creative"
                })
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data.get("success"), f"Gamemode switch failed: {data}")
                self.assertIn("Creative", data.get("message", ""))

                mock_cmd.assert_called_once_with("gamemode creative Alex")
                self.assertEqual(server_manager.online_players["Alex"]["gamemode"], "creative")

    def test_player_action_gamemode_with_mode_parameter(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            with patch.object(server_manager, "send_command", return_value={"success": True, "message": "Команда отправлена"}) as mock_cmd:
                with server_manager.lock:
                    server_manager.online_players["Alex"] = {"gamemode": "survival", "ping": 10}

                res = self.client.post("/api/players/action", json={
                    "action": "gamemode",
                    "player": "Alex",
                    "mode": "spectator"
                })
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data.get("success"))
                mock_cmd.assert_called_once_with("gamemode spectator Alex")
                self.assertEqual(server_manager.online_players["Alex"]["gamemode"], "spectator")

    def test_player_action_gamemode_with_both_mode_and_value(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            with patch.object(server_manager, "send_command", return_value={"success": True, "message": "Команда отправлена"}) as mock_cmd:
                with server_manager.lock:
                    server_manager.online_players["Steve"] = {"gamemode": "creative", "ping": 15}

                res = self.client.post("/api/players/action", json={
                    "action": "gamemode",
                    "player": "Steve",
                    "mode": "survival",
                    "value": "survival"
                })
                self.assertEqual(res.status_code, 200)
                data = res.json()
                self.assertTrue(data.get("success"))
                mock_cmd.assert_called_once_with("gamemode survival Steve")
                self.assertEqual(server_manager.online_players["Steve"]["gamemode"], "survival")

    def test_player_action_gamemode_aliases(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        alias_tests = [
            ("0", "survival"),
            ("s", "survival"),
            ("surv", "survival"),
            ("выживание", "survival"),
            ("режим выживания", "survival"),
            ("SURVIVAL", "survival"),
            ("1", "creative"),
            ("c", "creative"),
            ("creat", "creative"),
            ("креатив", "creative"),
            ("режим креатива", "creative"),
            ("творческий", "creative"),
            ("Creative", "creative"),
            ("2", "adventure"),
            ("a", "adventure"),
            ("adv", "adventure"),
            ("приключение", "adventure"),
            ("режим приключения", "adventure"),
            ("3", "spectator"),
            ("sp", "spectator"),
            ("spec", "spectator"),
            ("spectate", "spectator"),
            ("наблюдатель", "spectator"),
            ("режим наблюдателя", "spectator"),
            ("спектейтор", "spectator"),
        ]

        with patch.object(server_manager, "process", mock_proc):
            for raw_input, expected_clean in alias_tests:
                with patch.object(server_manager, "send_command", return_value={"success": True, "message": "OK"}) as mock_cmd:
                    res = self.client.post("/api/players/action", json={
                        "action": "gamemode",
                        "player": "Steve",
                        "value": raw_input
                    })
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.json().get("success"), f"Failed for alias '{raw_input}'")
                    mock_cmd.assert_called_once_with(f"gamemode {expected_clean} Steve")

    def test_player_action_gamemode_integers(self):
        """Verify integers (0, 1, 2, 3) work in both mode and value fields without HTTP 422 or falsy 0 bug."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        int_mapping = [
            (0, "survival"),
            (1, "creative"),
            (2, "adventure"),
            (3, "spectator"),
        ]

        with patch.object(server_manager, "process", mock_proc):
            for int_val, expected_clean in int_mapping:
                # Mode as integer
                with patch.object(server_manager, "send_command", return_value={"success": True, "message": "OK"}) as mock_cmd:
                    res = self.client.post("/api/players/action", json={
                        "action": "gamemode",
                        "player": "Steve",
                        "mode": int_val
                    })
                    self.assertEqual(res.status_code, 200, f"Failed for integer mode={int_val}: {res.text}")
                    self.assertTrue(res.json().get("success"))
                    mock_cmd.assert_called_once_with(f"gamemode {expected_clean} Steve")

                # Value as integer
                with patch.object(server_manager, "send_command", return_value={"success": True, "message": "OK"}) as mock_cmd:
                    res2 = self.client.post("/api/players/action", json={
                        "action": "gamemode",
                        "player": "Steve",
                        "value": int_val
                    })
                    self.assertEqual(res2.status_code, 200, f"Failed for integer value={int_val}: {res2.text}")
                    self.assertTrue(res2.json().get("success"))
                    mock_cmd.assert_called_once_with(f"gamemode {expected_clean} Steve")

    def test_player_action_gamemode_invalid(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            # Missing mode and value
            res = self.client.post("/api/players/action", json={
                "action": "gamemode",
                "player": "Steve"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data.get("success"))
            self.assertIn("Недопустимый режим игры", data.get("message", ""))

            # Unknown string
            res2 = self.client.post("/api/players/action", json={
                "action": "gamemode",
                "player": "Steve",
                "value": "godmode"
            })
            self.assertEqual(res2.status_code, 200)
            data2 = res2.json()
            self.assertFalse(data2.get("success"))
            self.assertIn("godmode", data2.get("message", ""))

    def test_player_action_kick_handling(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            # Kick with reason
            with patch.object(server_manager, "send_command", return_value={"success": True}) as mock_cmd:
                res = self.client.post("/api/players/action", json={
                    "action": "kick",
                    "player": "Troll",
                    "reason": "Griefing"
                })
                self.assertEqual(res.status_code, 200)
                mock_cmd.assert_called_once_with("kick Troll Griefing")

            # Kick with value
            with patch.object(server_manager, "send_command", return_value={"success": True}) as mock_cmd:
                res = self.client.post("/api/players/action", json={
                    "action": "kick",
                    "player": "Troll",
                    "value": "AFK too long"
                })
                self.assertEqual(res.status_code, 200)
                mock_cmd.assert_called_once_with("kick Troll AFK too long")

    def test_player_action_teleport_handling(self):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            # Teleport with target
            with patch.object(server_manager, "send_command", return_value={"success": True}) as mock_cmd:
                res = self.client.post("/api/players/action", json={
                    "action": "teleport",
                    "player": "Alex",
                    "target": "Steve"
                })
                self.assertEqual(res.status_code, 200)
                mock_cmd.assert_called_once_with("tp Alex Steve")

            # Teleport with value
            with patch.object(server_manager, "send_command", return_value={"success": True}) as mock_cmd:
                res = self.client.post("/api/players/action", json={
                    "action": "teleport",
                    "player": "Alex",
                    "value": "Steve"
                })
                self.assertEqual(res.status_code, 200)
                mock_cmd.assert_called_once_with("tp Alex Steve")

    def test_player_action_server_stopped(self):
        with patch.object(server_manager, "process", None):
            res = self.client.post("/api/players/action", json={
                "action": "gamemode",
                "player": "Alex",
                "mode": "creative"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data.get("success"))
            self.assertIn("Сервер должен быть запущен", data.get("message", ""))

    def test_player_action_invalid_username(self):
        res = self.client.post("/api/players/action", json={
            "action": "gamemode",
            "player": "Bad Name with Spaces!",
            "mode": "creative"
        })
        self.assertEqual(res.status_code, 400)

    def test_server_manager_console_gamemode_log_parsing(self):
        with server_manager.lock:
            server_manager.online_players["McDemon"] = {"gamemode": "survival", "ping": 10}

        # 1. Console executed command log
        line1 = "[05окт.2026 03:26:00.000] [Server thread/INFO] [net.minecraft.server.MinecraftServer/]: Set McDemon's game mode to Creative Mode"
        server_manager._handle_console_line_for_players(line1)
        self.assertEqual(server_manager.online_players["McDemon"]["gamemode"], "creative")

        # 2. Player self gamemode command log
        line2 = "[Server thread/INFO]: [McDemon: Set own game mode to Spectator Mode]"
        server_manager._handle_console_line_for_players(line2)
        self.assertEqual(server_manager.online_players["McDemon"]["gamemode"], "spectator")

        # 3. Vanilla bracketed server log
        line3 = "[Server thread/INFO]: [Server: Set McDemon's game mode to Survival Mode]"
        server_manager._handle_console_line_for_players(line3)
        self.assertEqual(server_manager.online_players["McDemon"]["gamemode"], "survival")

        # 4. Russian console log formats
        line4 = "[Server thread/INFO]: Игровой режим игрока McDemon изменен на Креатив"
        server_manager._handle_console_line_for_players(line4)
        self.assertEqual(server_manager.online_players["McDemon"]["gamemode"], "creative")

        line5 = "[Server thread/INFO]: Установлен игровой режим для McDemon: Наблюдатель"
        server_manager._handle_console_line_for_players(line5)
        self.assertEqual(server_manager.online_players["McDemon"]["gamemode"], "spectator")

    def test_offline_player_gamemode_no_fake_online_and_dat_updated(self):
        """Verifies that an offline player does NOT get added to online_players, and their disk .dat is updated."""
        import nbtlib
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(server_manager, "process", mock_proc):
            with patch.object(server_manager, "send_command", return_value={"success": True, "message": "OK"}):
                with server_manager.lock:
                    server_manager.online_players.clear()

                # Call gamemode for McDemon who is NOT in online_players
                res = self.client.post("/api/players/action", json={
                    "action": "gamemode",
                    "player": "McDemon",
                    "mode": "creative"
                })
                self.assertEqual(res.status_code, 200)
                self.assertTrue(res.json().get("success"))

                # Confirm McDemon was NOT added to online_players
                with server_manager.lock:
                    self.assertNotIn("McDemon", server_manager.online_players)

                # Confirm disk .dat file was updated to 1 (creative)
                dat_path = BASE_DIR / "server_data" / "world" / "playerdata" / "5e8052fb-4874-383d-a3f8-53d8c7bc1dac.dat"
                if dat_path.exists():
                    f = nbtlib.load(str(dat_path))
                    self.assertEqual(int(f["playerGameType"]), 1)

                    # Switch back to survival and verify
                    res2 = self.client.post("/api/players/action", json={
                        "action": "gamemode",
                        "player": "McDemon",
                        "mode": "survival"
                    })
                    self.assertTrue(res2.json().get("success"))
                    f2 = nbtlib.load(str(dat_path))
                    self.assertEqual(int(f2["playerGameType"]), 0)

    def test_frontend_js_payloads_and_modal_highlight(self):
        """Runs Node.js script to verify JavaScript functions build the correct payload."""
        js_test = """
        const fs = require('fs');
        const code = fs.readFileSync('app/static/app_logic.js', 'utf8');

        // Mock window / document environment
        let lastPayload = null;
        global.currentLang = 'en';
        global.performPlayerAction = async function(payload) {
          lastPayload = payload;
          return true;
        };
        global.currentInspectPlayer = 'Alex';
        global.refreshInspectPlayer = function() {};
        global.showToast = function() {};

        const mockElements = {
          btnGmSurvival: { className: 'btn active', classList: { add: function(c) { this.cls = c; }, remove: function(c) {} } },
          btnGmCreative: { className: 'btn', classList: { add: function(c) { this.cls = c; }, remove: function(c) {} } },
          btnGmAdventure: { className: 'btn', classList: { add: function(c) { this.cls = c; }, remove: function(c) {} } },
          btnGmSpectator: { className: 'btn', classList: { add: function(c) { this.cls = c; }, remove: function(c) {} } },
          inspectPlayerGmBadge: { className: '', textContent: '' },
          tpSourceSelect: { value: 'Alex' },
          tpTargetSelect: { value: 'Steve' }
        };

        global.document = {
          getElementById: (id) => mockElements[id] || { value: '', classList: { add: ()=>{}, remove: ()=>{} } }
        };
        global.t = (k) => k;
        // Extract getGamemodeBadges
        eval(code.slice(code.indexOf('function getGamemodeBadges'), code.indexOf('async function loadPlayers')));
        // Extract action functions starting from setPlayerGamemode
        eval(code.slice(code.indexOf('async function setPlayerGamemode'), code.indexOf('// ---------------- PLAYER INSPECTION MODAL')));

        // Test setPlayerGamemode
        setPlayerGamemode('Alex', 'creative');
        if (!lastPayload) {
          console.error("setPlayerGamemode failed to call performPlayerAction");
          process.exit(1);
        }
        if (lastPayload.action !== 'gamemode' || lastPayload.player !== 'Alex' || lastPayload.mode !== 'creative' || lastPayload.value !== 'creative') {
          console.error("Invalid setPlayerGamemode payload: " + JSON.stringify(lastPayload));
          process.exit(2);
        }

        // Test kickPlayer
        global.confirm = () => true;
        kickPlayer('Alex');
        if (lastPayload.action !== 'kick' || lastPayload.player !== 'Alex' || !lastPayload.reason || !lastPayload.value) {
          console.error("Invalid kickPlayer payload: " + JSON.stringify(lastPayload));
          process.exit(3);
        }

        // Test teleportSelectedPlayers
        teleportSelectedPlayers();
        if (lastPayload.action !== 'teleport' || lastPayload.player !== 'Alex' || lastPayload.target !== 'Steve' || lastPayload.value !== 'Steve') {
          console.error("Invalid teleport payload: " + JSON.stringify(lastPayload));
          process.exit(4);
        }

        console.log("ALL JS PAYLOAD TESTS PASSED");
        """
        proc = subprocess.run(["node", "-e", js_test], capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(proc.returncode, 0, f"JS contract test failed: {proc.stderr}\n{proc.stdout}")


if __name__ == "__main__":
    unittest.main()
