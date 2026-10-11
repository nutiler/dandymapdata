# DandyMap - Enhanced Textures

Optional terrain and dungeon artwork for **DandyMap**, built for WoW Forever beta 1.60.1 (Interface 16001).

[Download the latest texture pack](https://github.com/nutiler/dandymapdata/releases/latest)

## Installation

1. Install DandyMap from [CurseForge](https://www.curseforge.com/wow/addons/dandymap).
2. Download **DandyMapData-1.2.zip** from this repository's Releases page. The automatically generated **Source code** archives are build files and catalogs, not the texture pack.
3. Close WoW and extract the ZIP into your game's `Interface/AddOns` folder.
4. Check that `Interface/AddOns/DandyMapData/DandyMapData.toc` exists. Avoid an extra nested `DandyMapData` folder.
5. Start WoW and enable both **DandyMap** and **DandyMap - Local Textures**.

DandyMap detects the enabled pack automatically. Keep the folder named `DandyMapData`; its texture paths depend on that name. DandyMap 1.4.8 or newer is recommended. The main addon works without this download. Disable the data addon to return to the built-in client terrain.

## What's included

Version **1.2** includes 67 exported map datasets, terrain zoom levels 0–7, cleaned ocean backgrounds, outdoor hover textures, and exported interior artwork and placement metadata. The installed pack occupies approximately **6.31 GiB**. ZIP compression reduces the download size without changing the installed textures.

Some datasets are client test or unused maps. Their presence does not mean they are accessible in-game, and not every interior floor or transform is supported. This pack supplies artwork and map placement data; it has no standalone map window or NPC pin database.

## Repository contents

The repository keeps the addon catalog, placement metadata, build scripts, credits, and release manifest. Large TGA textures are distributed in the downloadable release ZIP. `manifest.json` lists each packaged file's SHA-256; `SHA256SUMS.txt` checks the release ZIP.

To rebuild from your own exports, see [the build instructions](tools/DANDEMap-build-README.txt). To package an existing generated pack, install the dependencies in `tools/requirements.txt` and run:

```powershell
python tools/package_release.py --pack "C:\YOUR GAME\Interface\AddOns\DandyMapData" --output "C:\YOUR OUTPUT\DandyMapData"
```

## Credits and support

Blizzard Entertainment: original client terrain and artwork. **wow.export**: terrain and interior export tools. **DandyMap**: texture preparation and catalog generation. Original artwork remains owned by its respective rights holders.

[Support Discord](https://discord.gg/pugs). Include your client build, DandyMap and texture-pack versions, map name, coordinates, and any Lua error when reporting a problem.
