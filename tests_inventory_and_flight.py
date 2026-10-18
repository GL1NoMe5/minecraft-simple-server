import json
import os
import sys
from pathlib import Path
import unittest

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app.config import load_config, save_config, ServerConfig, SERVER_DIR, CONFIG_FILE
from app.server_manager import server_manager
from app.player_service import parse_nbt_to_player_data, default_player_data, VANILLA_MAX_DURABILITY
from fastapi.testclient import TestClient
from app.main import app

class TestServerFlightAndInventory(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_allow_flight_in_config(self):
        cfg = load_config()
        self.assertTrue(hasattr(cfg, "allow_flight"), "ServerConfig must have allow_flight")
        self.assertTrue(cfg.allow_flight, "allow_flight should default to True")

    def test_allow_flight_in_server_properties_file(self):
        prop_file = SERVER_DIR / "server.properties"
        self.assertTrue(prop_file.exists(), "server.properties must exist")
        props = server_manager.read_server_properties()
        self.assertEqual(props.get("allow-flight"), "true", "allow-flight must be 'true' in server.properties")

    def test_server_manager_update_server_properties_preserves_flight(self):
        cfg = load_config()
        cfg.allow_flight = True
        server_manager.update_server_properties(cfg)
        props = server_manager.read_server_properties()
        self.assertEqual(props.get("allow-flight"), "true")

        # Test toggling to false and back to true
        cfg.allow_flight = False
        server_manager.update_server_properties(cfg)
        props = server_manager.read_server_properties()
        self.assertEqual(props.get("allow-flight"), "false")

        cfg.allow_flight = True
        server_manager.update_server_properties(cfg)
        props = server_manager.read_server_properties()
        self.assertEqual(props.get("allow-flight"), "true")

    def test_properties_api_get_and_post(self):
        # GET /api/server/properties
        res = self.client.get("/api/server/properties")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("allow-flight", data)
        self.assertEqual(data["allow-flight"], "true")

        # POST /api/server/properties with allow-flight
        data["allow-flight"] = "true"
        res_post = self.client.post("/api/server/properties", json=data)
        self.assertEqual(res_post.status_code, 200)
        self.assertTrue(res_post.json().get("success"))

        cfg = load_config()
        self.assertTrue(cfg.allow_flight)

    def test_static_inventory_assets_exist(self):
        icons_dir = BASE_DIR / "app" / "static" / "icons"
        required_icons = [
            "empty_armor_slot_helmet.png",
            "empty_armor_slot_chestplate.png",
            "empty_armor_slot_leggings.png",
            "empty_armor_slot_boots.png",
            "empty_armor_slot_shield.png",
            "ender_chest.png"
        ]
        for icon in required_icons:
            icon_path = icons_dir / icon
            self.assertTrue(icon_path.exists(), f"Icon {icon} must exist in {icons_dir}")
            self.assertGreater(icon_path.stat().st_size, 0, f"Icon {icon} cannot be empty")

        font_path = BASE_DIR / "app" / "static" / "assets" / "vendor" / "fonts" / "MinecraftTen.woff"
        self.assertTrue(font_path.exists(), "MinecraftTen.woff font must exist")
        self.assertGreater(font_path.stat().st_size, 1000, "MinecraftTen.woff font size valid")

    def test_player_service_default_player_data(self):
        data = default_player_data("Player1", "uuid-1234")
        inv = data["inventory"]
        self.assertIn("ender_chest", inv)
        self.assertEqual(len(inv["ender_chest"]), 27)
        self.assertEqual(len(inv["hotbar"]), 9)
        self.assertEqual(len(inv["main"]), 27)
        self.assertIn("helmet", inv["armor"])
        self.assertIn("chestplate", inv["armor"])
        self.assertIn("leggings", inv["armor"])
        self.assertIn("boots", inv["armor"])
        self.assertIsNone(inv["offhand"])

    def test_player_service_nbt_parsing_with_durability(self):
        mock_nbt = {
            "Health": 20.0,
            "foodLevel": 20,
            "Inventory": [
                {"id": "minecraft:netherite_pickaxe", "Count": 1, "Slot": 0, "tag": {"Damage": 200}},
                {"id": "minecraft:diamond_chestplate", "Count": 1, "Slot": 102, "tag": {"Damage": 50}},
                {"id": "ironfurnaces:upgrade", "Count": 4, "Slot": 10},
                {"id": "mekanism:mekasuit_helmet", "Count": 1, "Slot": 103, "tag": {"Damage": 10, "max_damage": 500}},
                {"id": "minecraft:shield", "Count": 1, "Slot": -106, "tag": {"Damage": 30}}
            ],
            "EnderItems": [
                {"id": "minecraft:diamond", "Count": 64, "Slot": 0},
                {"id": "create:wrench", "Count": 1, "Slot": 4}
            ]
        }
        data = parse_nbt_to_player_data("Crafter", "uuid-5678", mock_nbt)
        inv = data["inventory"]

        # Netherite pickaxe in hotbar slot 0
        pick = inv["hotbar"][0]
        self.assertIsNotNone(pick)
        self.assertEqual(pick["id"], "minecraft:netherite_pickaxe")
        self.assertEqual(pick["max_damage"], 2031)
        self.assertEqual(pick["damage"], 200)
        self.assertEqual(pick["durability_pct"], 90)
        self.assertTrue(pick["is_vanilla"])

        # Diamond chestplate in armor
        chest = inv["armor"]["chestplate"]
        self.assertIsNotNone(chest)
        self.assertEqual(chest["max_damage"], 528)
        self.assertEqual(chest["damage"], 50)
        self.assertEqual(chest["durability_pct"], 91)

        # Modded item in main inv slot 1 (slotNum = 10, index = 1)
        mod_item = inv["main"][1]
        self.assertIsNotNone(mod_item)
        self.assertEqual(mod_item["id"], "ironfurnaces:upgrade")
        self.assertFalse(mod_item["is_vanilla"])
        self.assertEqual(mod_item["namespace"], "ironfurnaces")
        self.assertEqual(mod_item["count"], 4)

        # Modded armor in helmet with custom max_damage
        mod_helm = inv["armor"]["helmet"]
        self.assertIsNotNone(mod_helm)
        self.assertEqual(mod_helm["id"], "mekanism:mekasuit_helmet")
        self.assertFalse(mod_helm["is_vanilla"])
        self.assertEqual(mod_helm["max_damage"], 500)
        self.assertEqual(mod_helm["durability_pct"], 98)

        # Shield in offhand
        shield = inv["offhand"]
        self.assertIsNotNone(shield)
        self.assertEqual(shield["id"], "minecraft:shield")
        self.assertEqual(shield["max_damage"], 336)
        self.assertEqual(shield["durability_pct"], 91)

        # EnderItems in ender_chest
        self.assertEqual(len(inv["ender_chest"]), 27)
        self.assertIsNotNone(inv["ender_chest"][0])
        self.assertEqual(inv["ender_chest"][0]["id"], "minecraft:diamond")
        self.assertEqual(inv["ender_chest"][0]["count"], 64)
        self.assertIsNotNone(inv["ender_chest"][4])
        self.assertEqual(inv["ender_chest"][4]["id"], "create:wrench")
        self.assertFalse(inv["ender_chest"][4]["is_vanilla"])

    def test_html_contains_authentic_mc_elements(self):
        index_html = (BASE_DIR / "app" / "static" / "index.html").read_text(encoding="utf-8")
        
        # Check required DOM elements
        self.assertIn('id="inspectArmorGrid"', index_html)
        self.assertIn('id="inspectEnderChestSlot"', index_html)
        self.assertIn('id="inspectOffhandSlot"', index_html)
        self.assertIn('id="inspectMainInvGrid"', index_html)
        self.assertIn('id="inspectHotbarGrid"', index_html)
        self.assertIn('id="inspectEnderGrid"', index_html)
        self.assertIn('id="inspectSelectedSlotInfo"', index_html)
        self.assertIn('id="propAllowFlight"', index_html)
        self.assertIn('modal-xl', index_html)
        
        # Check CSS classes
        self.assertIn('.mc-inventory-panel', index_html)
        self.assertIn('.mc-armor-column', index_html)
        self.assertIn('.mc-middle-column', index_html)
        self.assertIn('.mc-inv-column', index_html)
        self.assertIn('.mc-grid-main', index_html)
        self.assertIn('.mc-grid-hotbar', index_html)
        self.assertIn('.mc-durability-bar', index_html)
        self.assertIn('.mc-slot-count', index_html)
        self.assertIn("font-family: 'Minecraft'", index_html)

    def test_app_logic_js_functions(self):
        app_js = (BASE_DIR / "app" / "static" / "app_logic.js").read_text(encoding="utf-8")
        self.assertIn("renderInventoryGrids", app_js)
        self.assertIn("buildSlotHtml", app_js)
        self.assertIn("toggleEnderChestView", app_js)
        self.assertIn("showSlotDetails", app_js)
        self.assertIn("empty_armor_slot_helmet.png", app_js)
        self.assertIn("empty_armor_slot_shield.png", app_js)
        self.assertIn("ender_chest.png", app_js)
        self.assertIn("mc-durability-bar", app_js)
        self.assertIn("mc-slot-count", app_js)
        self.assertIn("propAllowFlight", app_js)

if __name__ == "__main__":
    unittest.main()
