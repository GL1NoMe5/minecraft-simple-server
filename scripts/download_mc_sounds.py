import urllib.request
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "app" / "static" / "assets" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

ASSET_INDEX_URL = "https://piston-meta.mojang.com/v1/packages/16f8e2eca81b5c757d3870c17a58376fc296e2e0/12.json"
BASE_RES_URL = "https://resources.download.minecraft.net"

TARGET_SOUNDS = {
    "click.ogg": "minecraft/sounds/random/click.ogg",
    "wood_click.ogg": "minecraft/sounds/random/wood_click.ogg",
    "cherrywood_click.ogg": "minecraft/sounds/block/cherrywood_button/cherrywood_click.ogg",
    "bamboo_click.ogg": "minecraft/sounds/block/bamboo_wood_button/bamboo_wood_button.ogg",
    "page_flip.ogg": "minecraft/sounds/item/book/open_flip1.ogg",
    "pop.ogg": "minecraft/sounds/random/pop.ogg",
    "bundle_insert.ogg": "minecraft/sounds/item/bundle/insert1.ogg",
    "bundle_drop.ogg": "minecraft/sounds/item/bundle/drop_contents1.ogg",
    "chest_open.ogg": "minecraft/sounds/random/chestopen.ogg",
    "chest_close.ogg": "minecraft/sounds/block/chest/close1.ogg",
    "door_close.ogg": "minecraft/sounds/block/wooden_door/close1.ogg",
    "barrel_close.ogg": "minecraft/sounds/block/barrel/close.ogg",
    "amethyst_chime.ogg": "minecraft/sounds/block/amethyst_cluster/place1.ogg",
    "amethyst_resonate.ogg": "minecraft/sounds/block/amethyst/resonate1.ogg",
    "amethyst_shimmer.ogg": "minecraft/sounds/block/amethyst/shimmer.ogg",
    "amethyst_step.ogg": "minecraft/sounds/block/amethyst/step1.ogg",
    "levelup.ogg": "minecraft/sounds/random/levelup.ogg",
    "note_bass.ogg": "minecraft/sounds/note/bass.ogg",
    "note_pling.ogg": "minecraft/sounds/note/pling.ogg",
    "note_bell.ogg": "minecraft/sounds/note/bell.ogg",
    "note_harp.ogg": "minecraft/sounds/note/harp.ogg",
    "note_flute.ogg": "minecraft/sounds/note/flute.ogg",
    "orb.ogg": "minecraft/sounds/random/orb.ogg",
    "enchant.ogg": "minecraft/sounds/block/enchantment_table/enchant1.ogg",
    "beacon_activate.ogg": "minecraft/sounds/block/beacon/activate.ogg",
    "conduit_activate.ogg": "minecraft/sounds/block/conduit/activate.ogg",
    "liquid_splash.ogg": "minecraft/sounds/liquid/splash.ogg",
    "bottle_fill.ogg": "minecraft/sounds/item/bottle/fill1.ogg",
    "honey_wax.ogg": "minecraft/sounds/item/honeycomb/wax_on1.ogg",
    "villager_no.ogg": "minecraft/sounds/mob/villager/no1.ogg",
    "villager_yes.ogg": "minecraft/sounds/mob/villager/yes1.ogg",
    "toast_challenge.ogg": "minecraft/sounds/ui/toast/challenge_complete.ogg",
    "toast_in.ogg": "minecraft/sounds/ui/toast/in.ogg",
}

def main():
    print("Fetching asset index...")
    req = urllib.request.Request(ASSET_INDEX_URL, headers={"User-Agent": "MinecraftSoundDownloader/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        index_data = json.loads(resp.read().decode("utf-8"))
    
    objects = index_data.get("objects", {})
    print(f"Loaded {len(objects)} assets from index.")
    
    manifest = {}
    downloaded = 0
    
    for filename, sound_key in TARGET_SOUNDS.items():
        if sound_key not in objects:
            print(f"WARNING: Key {sound_key} not found in index!")
            continue
        obj = objects[sound_key]
        sha1_hash = obj["hash"]
        size = obj["size"]
        prefix = sha1_hash[:2]
        url = f"{BASE_RES_URL}/{prefix}/{sha1_hash}"
        out_path = AUDIO_DIR / filename
        
        manifest[filename] = {
            "key": sound_key,
            "hash": sha1_hash,
            "size": size,
            "file": f"/static/assets/audio/{filename}"
        }
        
        if out_path.exists() and out_path.stat().st_size == size:
            print(f"Skipping (already exists): {filename}")
            continue
            
        print(f"Downloading {filename} ({size} bytes) from {url} ...")
        sound_req = urllib.request.Request(url, headers={"User-Agent": "MinecraftSoundDownloader/1.0"})
        with urllib.request.urlopen(sound_req, timeout=15) as sresp:
            sound_data = sresp.read()
        
        with open(out_path, "wb") as f:
            f.write(sound_data)
        downloaded += 1

    manifest_path = AUDIO_DIR / "sounds_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        
    print(f"\nCompleted! Downloaded: {downloaded}, Total verified: {len(manifest)}")
    print(f"Saved manifest to {manifest_path}")

if __name__ == "__main__":
    main()
