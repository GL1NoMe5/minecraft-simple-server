import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.player_service import parse_nbt_to_player_data, default_player_data, _extract_item_dict

class TestInventoryEdgeCases(unittest.TestCase):
    def test_empty_nbt_root(self):
        res = parse_nbt_to_player_data("GhostPlayer", "uuid-000", {})
        self.assertEqual(res["health"], 20.0)
        self.assertEqual(res["food"], 20)
        self.assertEqual(len(res["inventory"]["main"]), 27)
        self.assertEqual(len(res["inventory"]["hotbar"]), 9)
        self.assertEqual(len(res["inventory"]["ender_chest"]), 27)
        self.assertEqual(res["inventory"]["total_items"], 0)

    def test_damaged_item_exceeding_max_durability(self):
        raw = {"id": "minecraft:diamond_sword", "Count": 1, "Slot": 0, "tag": {"Damage": 99999}}
        item = _extract_item_dict(raw)
        self.assertIsNotNone(item)
        self.assertEqual(item["durability_pct"], 0) # bounded at 0

    def test_damage_zero_durability_pct_none(self):
        raw = {"id": "minecraft:diamond_sword", "Count": 1, "Slot": 0, "tag": {"Damage": 0}}
        item = _extract_item_dict(raw)
        self.assertIsNotNone(item)
        self.assertIsNone(item["durability_pct"])

    def test_modded_item_with_special_characters(self):
        raw = {"id": "ae2:item.appliedenergistics2.BiometricCard", "Count": 1, "Slot": 5}
        item = _extract_item_dict(raw)
        self.assertIsNotNone(item)
        self.assertEqual(item["namespace"], "ae2")
        self.assertFalse(item["is_vanilla"])

    def test_offhand_unsigned_byte_slot(self):
        # In Minecraft NBT, offhand slot -106 is sometimes stored as unsigned byte 150
        nbt = {
            "Inventory": [
                {"id": "minecraft:totem_of_undying", "Count": 1, "Slot": 150}
            ]
        }
        res = parse_nbt_to_player_data("TotemUser", "uuid-111", nbt)
        self.assertIsNotNone(res["inventory"]["offhand"])
        self.assertEqual(res["inventory"]["offhand"]["id"], "minecraft:totem_of_undying")

    def test_equipment_compound_modern_versions(self):
        # Minecraft 1.20.5+ / 1.21 equipment compound
        nbt = {
            "equipment": {
                "head": {"id": "minecraft:turtle_helmet", "count": 1},
                "offhand": {"id": "minecraft:shield", "count": 1, "components": {"minecraft:damage": 10}}
            }
        }
        res = parse_nbt_to_player_data("ModernPlayer", "uuid-222", nbt)
        self.assertIsNotNone(res["inventory"]["armor"]["helmet"])
        self.assertEqual(res["inventory"]["armor"]["helmet"]["id"], "minecraft:turtle_helmet")
        self.assertIsNotNone(res["inventory"]["offhand"])
        self.assertEqual(res["inventory"]["offhand"]["id"], "minecraft:shield")
        self.assertEqual(res["inventory"]["offhand"]["damage"], 10)

    def test_ender_items_out_of_bounds_slots(self):
        nbt = {
            "EnderItems": [
                {"id": "minecraft:apple", "Count": 5, "Slot": -1}, # negative slot
                {"id": "minecraft:golden_apple", "Count": 2, "Slot": 26}, # valid slot
                {"id": "minecraft:bread", "Count": 10, "Slot": 99} # beyond 27 slots
            ]
        }
        res = parse_nbt_to_player_data("EnderUser", "uuid-333", nbt)
        ender = res["inventory"]["ender_chest"]
        self.assertEqual(len(ender), 27)
        self.assertIsNotNone(ender[26])
        self.assertEqual(ender[26]["id"], "minecraft:golden_apple")

    def test_negative_damage_clamped_to_zero(self):
        raw = {"id": "minecraft:iron_sword", "Count": 1, "Slot": 0, "tag": {"Damage": -50}}
        item = _extract_item_dict(raw)
        self.assertIsNotNone(item)
        self.assertEqual(item["damage"], 0)
        self.assertIsNone(item["durability_pct"])

    def test_wolf_armor_durability(self):
        raw = {"id": "minecraft:wolf_armor", "Count": 1, "Slot": 0, "tag": {"Damage": 16}}
        item = _extract_item_dict(raw)
        self.assertIsNotNone(item)
        self.assertEqual(item["max_damage"], 64)
        self.assertEqual(item["damage"], 16)
        self.assertEqual(item["durability_pct"], 75)

    def test_js_build_slot_html_has_count_class(self):
        import shutil
        import subprocess
        if not shutil.which("node"):
            self.skipTest("Node.js is not installed on this system")
        script = """
        const fs = require('fs');
        const code = fs.readFileSync('app/static/app_logic.js', 'utf8');
        eval(code.slice(code.indexOf('function getTextureSlug'), code.indexOf('function onItemIconError')));
        function escapeHtml(s) { return s; }
        const modItemWithCount = { id: 'thermal:drill', name: 'Drill', count: 4, namespace: 'thermal', is_vanilla: false };
        const html = buildSlotHtml('main_0', 9, 'Слот 9', modItemWithCount);
        if (!html.includes('has-count')) process.exit(1);
        const modItemSingle = { id: 'thermal:wrench', name: 'Wrench', count: 1, namespace: 'thermal', is_vanilla: false };
        const htmlSingle = buildSlotHtml('main_1', 10, 'Слот 10', modItemSingle);
        if (htmlSingle.includes('has-count')) process.exit(2);
        """
        res = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=str(BASE_DIR))
        self.assertEqual(res.returncode, 0, f"Node script failed: {res.stderr}")

if __name__ == "__main__":
    unittest.main()

