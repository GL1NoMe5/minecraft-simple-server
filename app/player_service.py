import hashlib
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import nbtlib
from PIL import Image, ImageDraw

from app.config import BASE_DIR, SERVER_DIR

AVATAR_CACHE_DIR = BASE_DIR / "cache" / "avatars"
AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
AVATAR_CACHE_TTL = 86400  # 24 hours

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_.\-]{1,32}$")

GAMEMODE_MAP = {
    0: "survival",
    1: "creative",
    2: "adventure",
    3: "spectator",
}


def is_valid_username(username: str) -> bool:
    if not username or not isinstance(username, str):
        return False
    return bool(USERNAME_REGEX.match(username.strip()))


def get_offline_uuid(username: str) -> str:
    """Computes Minecraft's offline-mode UUIDv3 for a username."""
    md5_bytes = bytearray(hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest())
    md5_bytes[6] = (md5_bytes[6] & 0x0F) | 0x30  # version 3
    md5_bytes[8] = (md5_bytes[8] & 0x3F) | 0x80  # IETF variant
    return str(uuid.UUID(bytes=bytes(md5_bytes)))


def load_usercache() -> List[Dict[str, str]]:
    cache_file = SERVER_DIR / "usercache.json"
    if not cache_file.exists():
        return []
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def resolve_player_uuid(username: str) -> str:
    uname_lower = username.lower()
    for entry in load_usercache():
        if str(entry.get("name", "")).lower() == uname_lower and entry.get("uuid"):
            return str(entry["uuid"])
    return get_offline_uuid(username)


def _generate_default_steve_png() -> bytes:
    """Generates a 64x64 pixel-art Steve avatar PNG as local fallback."""
    default_path = AVATAR_CACHE_DIR / "_default_steve.png"
    if default_path.exists():
        try:
            return default_path.read_bytes()
        except Exception:
            pass

    img = Image.new("RGBA", (8, 8), (189, 142, 114, 255))
    draw = ImageDraw.Draw(img)
    # Hair (top and sides)
    hair_color = (74, 52, 35, 255)
    for x in range(8):
        draw.point((x, 0), fill=hair_color)
        draw.point((x, 1), fill=hair_color)
    draw.point((0, 2), fill=hair_color)
    draw.point((7, 2), fill=hair_color)

    # Eyes
    draw.point((1, 4), fill=(255, 255, 255, 255))
    draw.point((2, 4), fill=(73, 59, 127, 255))
    draw.point((5, 4), fill=(73, 59, 127, 255))
    draw.point((6, 4), fill=(255, 255, 255, 255))

    # Nose & Mouth
    draw.point((3, 5), fill=(156, 105, 76, 255))
    draw.point((4, 5), fill=(156, 105, 76, 255))
    for x in range(2, 6):
        draw.point((x, 6), fill=(115, 69, 48, 255))

    scaled = img.resize((64, 64), Image.Resampling.NEAREST)
    buf = io.BytesIO()
    scaled.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    try:
        default_path.write_bytes(png_bytes)
    except Exception:
        pass
    return png_bytes


def _crop_skin_to_avatar(skin_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(skin_bytes)) as raw_img:
        img = raw_img.convert("RGBA")
        # Support standard 64px skins as well as HD skins (128x, 256x, etc.)
        scale = max(1, img.width // 64)
        base_box = (8 * scale, 8 * scale, 16 * scale, 16 * scale)
        overlay_box = (40 * scale, 8 * scale, 48 * scale, 16 * scale)

        head = img.crop(base_box)
        if img.width >= 48 * scale and img.height >= 16 * scale:
            overlay = img.crop(overlay_box)
            head = Image.alpha_composite(head, overlay)

        avatar = head.resize((64, 64), Image.Resampling.NEAREST)
        buf = io.BytesIO()
        avatar.save(buf, format="PNG")
        return buf.getvalue()


def get_player_avatar(username: str, force_refresh: bool = False) -> bytes:
    """
    Cascading avatar resolver:
    1. Disk cache in cache/avatars/{username}.png
    2. Ely.by skin system: http://skinsystem.ely.by/textures/{username}
       -> crops (8,8,16,16) + (40,8,48,16) and scales 64x64 NEAREST
    3. Fallback: https://mc-heads.net/avatar/{username}/64
    4. Local fallback: default Steve 64x64 PNG
    """
    safe_name = re.sub(r"[^a-zA-Z0-9_.\-]", "_", username.strip()).lower() or "steve"
    cache_path = AVATAR_CACHE_DIR / f"{safe_name}.png"

    if not force_refresh and cache_path.exists():
        try:
            age = time.time() - cache_path.stat().st_mtime
            if age < AVATAR_CACHE_TTL and cache_path.stat().st_size > 0:
                return cache_path.read_bytes()
        except Exception:
            pass

    quoted_user = urllib.parse.quote(username.strip())

    # 1. Try Ely.by textures API
    try:
        ely_url = f"http://skinsystem.ely.by/textures/{quoted_user}"
        req = urllib.request.Request(ely_url, headers={"User-Agent": "LocalMCManager/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                ctype = (resp.headers.get("content-type") or "").lower()
                body = resp.read()
                if "image/" in ctype:
                    png_bytes = _crop_skin_to_avatar(body)
                    cache_path.write_bytes(png_bytes)
                    return png_bytes
                elif body:
                    tex_data = json.loads(body.decode("utf-8"))
                    skin_url = tex_data.get("SKIN", {}).get("url")
                    if skin_url:
                        req_skin = urllib.request.Request(skin_url, headers={"User-Agent": "LocalMCManager/1.0"})
                        with urllib.request.urlopen(req_skin, timeout=5) as skin_resp:
                            if skin_resp.status == 200:
                                png_bytes = _crop_skin_to_avatar(skin_resp.read())
                                cache_path.write_bytes(png_bytes)
                                return png_bytes
    except Exception:
        pass

    # 2. Fallback to mc-heads.net
    try:
        mcheads_url = f"https://mc-heads.net/avatar/{quoted_user}/64"
        req = urllib.request.Request(mcheads_url, headers={"User-Agent": "LocalMCManager/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                raw_bytes = resp.read()
                with Image.open(io.BytesIO(raw_bytes)) as im:
                    im_rgba = im.convert("RGBA").resize((64, 64), Image.Resampling.NEAREST)
                    buf = io.BytesIO()
                    im_rgba.save(buf, format="PNG")
                    png_bytes = buf.getvalue()
                    cache_path.write_bytes(png_bytes)
                    return png_bytes
    except Exception:
        pass

    # 3. Local default Steve fallback
    return _generate_default_steve_png()


STATIC_ICONS_DIR = Path(__file__).parent / "static" / "icons"
STATIC_ICONS_DIR.mkdir(parents=True, exist_ok=True)


def get_item_icon(item_id: str) -> Optional[bytes]:
    """
    Retrieves the PNG icon for a vanilla Minecraft item or block, caching it in static/icons/.
    Falls back across item textures, block textures, and PrismarineJS assets.
    """
    clean_id = (item_id or "").strip().lower()
    if clean_id.startswith("minecraft:"):
        clean_id = clean_id[len("minecraft:"):]

    safe_name = re.sub(r"[^a-z0-9_.\-]", "_", clean_id)
    if not safe_name:
        return None

    # 1. Check local disk cache
    cached_file = STATIC_ICONS_DIR / f"{safe_name}.png"
    if cached_file.exists() and cached_file.stat().st_size > 0:
        try:
            return cached_file.read_bytes()
        except Exception:
            pass

    # 2. Try online sources (mcasset.cloud item -> block -> PrismarineJS item -> block)
    urls = [
        f"https://assets.mcasset.cloud/1.20.2/assets/minecraft/textures/item/{safe_name}.png",
        f"https://assets.mcasset.cloud/1.20.2/assets/minecraft/textures/block/{safe_name}.png",
        f"https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.20.2/items/{safe_name}.png",
        f"https://raw.githubusercontent.com/PrismarineJS/minecraft-assets/master/data/1.20.2/blocks/{safe_name}.png",
    ]

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "LocalMCManager/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if data and len(data) > 30:
                        try:
                            cached_file.write_bytes(data)
                        except Exception:
                            pass
                        return data
        except Exception:
            continue

    return None


VANILLA_MAX_DURABILITY: Dict[str, int] = {
    # Swords
    "wooden_sword": 59, "stone_sword": 131, "iron_sword": 250, "golden_sword": 32, "diamond_sword": 1561, "netherite_sword": 2031,
    # Shovels
    "wooden_shovel": 59, "stone_shovel": 131, "iron_shovel": 250, "golden_shovel": 32, "diamond_shovel": 1561, "netherite_shovel": 2031,
    # Pickaxes
    "wooden_pickaxe": 59, "stone_pickaxe": 131, "iron_pickaxe": 250, "golden_pickaxe": 32, "diamond_pickaxe": 1561, "netherite_pickaxe": 2031,
    # Axes
    "wooden_axe": 59, "stone_axe": 131, "iron_axe": 250, "golden_axe": 32, "diamond_axe": 1561, "netherite_axe": 2031,
    # Hoes
    "wooden_hoe": 59, "stone_hoe": 131, "iron_hoe": 250, "golden_hoe": 32, "diamond_hoe": 1561, "netherite_hoe": 2031,
    # Armor
    "leather_helmet": 55, "leather_chestplate": 80, "leather_leggings": 75, "leather_boots": 65,
    "chainmail_helmet": 165, "chainmail_chestplate": 240, "chainmail_leggings": 225, "chainmail_boots": 195,
    "iron_helmet": 165, "iron_chestplate": 240, "iron_leggings": 225, "iron_boots": 195,
    "golden_helmet": 77, "golden_chestplate": 112, "golden_leggings": 105, "golden_boots": 91,
    "diamond_helmet": 363, "diamond_chestplate": 528, "diamond_leggings": 495, "diamond_boots": 429,
    "netherite_helmet": 407, "netherite_chestplate": 592, "netherite_leggings": 555, "netherite_boots": 481,
    "turtle_helmet": 275,
    # Tools & equipment
    "bow": 384, "crossbow": 465, "fishing_rod": 64, "shears": 238, "flint_and_steel": 64, "shield": 336,
    "trident": 250, "elytra": 432, "brush": 64, "mace": 500, "carrot_on_a_stick": 25, "warped_fungus_on_a_stick": 100,
    "wolf_armor": 64,
}


def format_item_display_name(item_id: str) -> str:
    if not item_id:
        return "Пусто"
    short_id = item_id.split(":", 1)[-1]
    return short_id.replace("_", " ").title()


def _extract_item_dict(item_compound: Any) -> Optional[Dict[str, Any]]:
    try:
        raw_id = str(item_compound.get("id", ""))
        if not raw_id or raw_id == "minecraft:air":
            return None
        count_val = item_compound.get("Count")
        if count_val is None:
            count_val = item_compound.get("count", 1)
        count = int(count_val)
        slot_val = item_compound.get("Slot")
        slot = int(slot_val) if slot_val is not None else None

        # Check for custom name or damage if present
        tag = item_compound.get("tag") or item_compound.get("components")
        custom_name = None
        damage = 0
        max_damage = None
        if tag and isinstance(tag, dict):
            if "Damage" in tag:
                try:
                    damage = max(0, int(tag["Damage"]))
                except Exception:
                    pass
            elif "minecraft:damage" in tag:
                try:
                    damage = max(0, int(tag["minecraft:damage"]))
                except Exception:
                    pass

            if "minecraft:max_damage" in tag:
                try:
                    max_damage = int(tag["minecraft:max_damage"])
                except Exception:
                    pass
            elif "max_damage" in tag:
                try:
                    max_damage = int(tag["max_damage"])
                except Exception:
                    pass
            elif "MaxDamage" in tag:
                try:
                    max_damage = int(tag["MaxDamage"])
                except Exception:
                    pass

            # Custom name extraction
            disp = tag.get("display") or tag.get("minecraft:custom_name")
            if isinstance(disp, dict) and "Name" in disp:
                try:
                    raw_n = str(disp["Name"])
                    if raw_n.startswith("{") and "text" in raw_n:
                        custom_name = json.loads(raw_n).get("text")
                    else:
                        custom_name = raw_n
                except Exception:
                    pass
            elif isinstance(disp, str):
                try:
                    if disp.startswith("{") and "text" in disp:
                        custom_name = json.loads(disp).get("text")
                    else:
                        custom_name = disp
                except Exception:
                    pass

        is_vanilla = raw_id.startswith("minecraft:") or ":" not in raw_id
        parts = raw_id.split(":", 1)
        namespace = parts[0] if len(parts) == 2 else "minecraft"
        item_name = parts[1] if len(parts) == 2 else parts[0]

        if max_damage is None and is_vanilla:
            max_damage = VANILLA_MAX_DURABILITY.get(item_name)
        elif max_damage is None and damage > 0:
            max_damage = max(damage + 20, 100)

        durability_pct = None
        if damage > 0 and max_damage and max_damage > 0:
            durability_pct = max(0, min(100, round((1.0 - damage / max_damage) * 100)))

        return {
            "slot": slot,
            "id": raw_id,
            "name": custom_name or format_item_display_name(raw_id),
            "count": count,
            "damage": damage,
            "max_damage": max_damage,
            "durability_pct": durability_pct,
            "is_vanilla": is_vanilla,
            "namespace": namespace,
            "item_name": item_name,
            "icon_url": f"/api/items/{raw_id}/icon" if is_vanilla else None,
        }
    except Exception:
        return None


def parse_nbt_to_player_data(username: str, uuid_str: str, nbt_root: Any, source: str = "file") -> Dict[str, Any]:
    """Converts an nbtlib Compound (from .dat file or parsed SNBT) into clean JSON for the frontend."""
    def _float(key: str, default: float = 0.0) -> float:
        val = nbt_root.get(key)
        try:
            return round(float(val), 1) if val is not None else default
        except Exception:
            return default

    def _int(key: str, default: int = 0) -> int:
        val = nbt_root.get(key)
        try:
            return int(val) if val is not None else default
        except Exception:
            return default

    health = _float("Health", 20.0)
    food = _int("foodLevel", 20)
    saturation = _float("foodSaturationLevel", 5.0)
    xp_level = _int("XpLevel", 0)
    xp_p = _float("XpP", 0.0)
    game_type_num = _int("playerGameType", 0)
    gamemode = GAMEMODE_MAP.get(game_type_num, "survival")

    dimension_raw = nbt_root.get("Dimension", "minecraft:overworld")
    dimension = str(dimension_raw).replace('"', "")

    pos_list = nbt_root.get("Pos", [])
    try:
        pos = [round(float(x), 1) for x in list(pos_list)[:3]]
        if len(pos) < 3:
            pos = [0.0, 64.0, 0.0]
    except Exception:
        pos = [0.0, 64.0, 0.0]

    hotbar: List[Optional[Dict[str, Any]]] = [None] * 9
    main_inv: List[Optional[Dict[str, Any]]] = [None] * 27
    armor: Dict[str, Optional[Dict[str, Any]]] = {
        "helmet": None,
        "chestplate": None,
        "leggings": None,
        "boots": None,
    }
    offhand: Optional[Dict[str, Any]] = None
    raw_items: List[Dict[str, Any]] = []

    inv_list = nbt_root.get("Inventory", [])
    if inv_list:
        for raw_item in inv_list:
            parsed = _extract_item_dict(raw_item)
            if not parsed:
                continue
            raw_items.append(parsed)
            slot = parsed["slot"]
            if slot is None:
                continue
            # Handle signed/unsigned byte for -106 (150 unsigned)
            if slot < 0:
                slot_signed = slot
            elif slot > 127:
                slot_signed = slot - 256
            else:
                slot_signed = slot

            if 0 <= slot_signed <= 8:
                hotbar[slot_signed] = parsed
            elif 9 <= slot_signed <= 35:
                main_inv[slot_signed - 9] = parsed
            elif slot_signed == 100:
                armor["boots"] = parsed
            elif slot_signed == 101:
                armor["leggings"] = parsed
            elif slot_signed == 102:
                armor["chestplate"] = parsed
            elif slot_signed == 103:
                armor["helmet"] = parsed
            elif slot_signed in (-106, 40):
                offhand = parsed

    # Support 1.20.5+ / 1.21+ 'equipment' compound if present
    equip = nbt_root.get("equipment")
    if equip and isinstance(equip, dict):
        for eq_key, target_key in (
            ("head", "helmet"),
            ("chest", "chestplate"),
            ("legs", "leggings"),
            ("feet", "boots"),
        ):
            if eq_key in equip and armor[target_key] is None:
                parsed_eq = _extract_item_dict(equip[eq_key])
                if parsed_eq:
                    armor[target_key] = parsed_eq
                    raw_items.append(parsed_eq)
        if "offhand" in equip and offhand is None:
            parsed_off = _extract_item_dict(equip["offhand"])
            if parsed_off:
                offhand = parsed_off
                raw_items.append(parsed_off)

    # Parse Ender Chest items (EnderItems)
    ender_inv: List[Optional[Dict[str, Any]]] = [None] * 27
    ender_list = nbt_root.get("EnderItems", [])
    if ender_list:
        for raw_item in ender_list:
            parsed_ender = _extract_item_dict(raw_item)
            if not parsed_ender:
                continue
            e_slot = parsed_ender["slot"]
            if e_slot is not None and 0 <= e_slot < 27:
                ender_inv[e_slot] = parsed_ender

    return {
        "name": username,
        "uuid": uuid_str,
        "source": source,
        "has_nbt": True,
        "health": max(0.0, min(health, 40.0)),
        "max_health": 20.0,
        "food": max(0, min(food, 20)),
        "max_food": 20,
        "saturation": saturation,
        "xp_level": xp_level,
        "xp_progress": round(xp_p * 100, 1),
        "gamemode": gamemode,
        "dimension": dimension,
        "position": {"x": pos[0], "y": pos[1], "z": pos[2]},
        "inventory": {
            "hotbar": hotbar,
            "main": main_inv,
            "armor": armor,
            "offhand": offhand,
            "ender_chest": ender_inv,
            "total_items": len(raw_items),
        },
    }


def read_player_data_from_disk(username: str) -> Optional[Dict[str, Any]]:
    uuid_str = resolve_player_uuid(username)
    playerdata_dir = SERVER_DIR / "world" / "playerdata"
    dat_file = playerdata_dir / f"{uuid_str}.dat"

    if dat_file.exists():
        try:
            nbt_file = nbtlib.load(dat_file)
            root = nbt_file.root if hasattr(nbt_file, "root") else nbt_file
            return parse_nbt_to_player_data(username, uuid_str, root, source="playerdata_file")
        except Exception:
            pass

    return None


def default_player_data(username: str, uuid_str: str) -> Dict[str, Any]:
    """Fallback empty structure used only when inspecting an online player who has not saved to disk yet."""
    return {
        "name": username,
        "uuid": uuid_str,
        "source": "pending",
        "has_nbt": False,
        "health": 20.0,
        "max_health": 20.0,
        "food": 20,
        "max_food": 20,
        "saturation": 5.0,
        "xp_level": 0,
        "xp_progress": 0.0,
        "gamemode": "survival",
        "dimension": "minecraft:overworld",
        "position": None,
        "inventory": {
            "hotbar": [None] * 9,
            "main": [None] * 27,
            "armor": {
                "helmet": None,
                "chestplate": None,
                "leggings": None,
                "boots": None,
            },
            "offhand": None,
            "ender_chest": [None] * 27,
            "total_items": 0,
        },
    }
