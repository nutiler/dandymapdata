DANDEMap — one-command MapData builder

FIRST RUN
1. Install Python 3 if needed. Open PowerShell in the folder containing
   DANDEMap-build-all.py.
2. Install dependencies once:
   py -m pip install Pillow numpy scipy
3. Close WoW.
4. Run:
   py .\DANDEMap-build-all.py

If the default export path is missing, a folder picker opens. Select the MAPS
folder containing azeroth, kalimdor, 2991, and dungeon folders. Do not select
one individual minimap folder. Canceling stops without installing anything.
If the picker is unavailable, the script asks for the path in the terminal.

You can always specify the exact export folder yourself:
   py .\DANDEMap-build-all.py --maps-root "C:\YOUR ACTUAL EXPORT PATH\maps"

The default is the wow.export\maps folder under your Windows user profile.
A single folder named wow.export differs from a folder named .export inside
a folder named wow. Use File Explorer's address bar to copy the real path; don't guess.
The selected path is recorded in DANDEMap-build-report.json. It is not saved
as the default for later runs: use --maps-root to avoid choosing it again.

INSTALL DESTINATION
Default:
C:\Program Files (x86)\World of Warcraft\_classic_beta_\Interface\AddOns\DandyMapData
The builder does not read or modify the sibling DandyMap addon. Install the
current DandyMap addon separately to use ocean markers and WMO metadata.
To override the destination, add:
   --output "D:\YOUR GAME\Interface\AddOns\DandyMapData"

NORMAL UPDATE WORKFLOW
1. Export current maps through wow.export into your maps folder.
2. Keep native mapXX_YY.png filenames. Keep each WMO PNG together with its
   matching *_wmo_minimap.json. Avoid duplicate or stale alternate exports.
3. Close WoW and run the builder.
4. Wait for DONE, then restart WoW.
5. Check continent seams, hover behavior, player/quest pins, and dungeon
   position/orientation. Keep the backup until these checks pass.

WHAT IT DOES
- Scans native terrain plus paired WMO images/metadata recursively within
  each map subfolder, including monastery_wmo_minimap files.
- Cleans Kalimdor/Eastern Kingdoms ocean; handles known Kalimdor artifact
  tiles conservatively; replaces Zephra's edge-connected black background.
- Preserves dungeon artwork; creates TGA zoom levels 0 through 7.
- Builds terrain-only hover textures for the three outdoor overview maps.
- Generates Data.lua and supported WMO runtime metadata inside DandyMapData.
- Never installs addon UI code or modifies DANDEMap or saved settings.
- Preserves installed maps absent from this export; no automatic pruning.
- Stages and validates output before installation, keeps backups beside
  DandyMapData, and rolls back ordinary installation errors.
- Does not modify source exports and does not make a ZIP.

WMO POSITIONING LIMIT
Current support covers origin-placed global WMO exports with the known
wow.export corners/ppu/image/map_id metadata. Unknown schema, non-origin
placement, rotation or scale stops installation rather than guessing.
If stopped, send DANDEMap-build-report.json. It contains exported WMO metadata
and local paths; it is not uploaded automatically.
A PNG alone cannot establish a dungeon's true world transform.

OPTIONAL SCAN ONLY
   py .\DANDEMap-build-all.py --scan-only
This validates export structure/metadata and writes the report without
building textures or installing files. It still rejects unsupported metadata.

ERRORS
- Export folder not found: use the picker or --maps-root with the exact path.
- Missing WMO partner: export/copy both the PNG and corresponding JSON.
- Unsupported WMO transform: send the report; do not delete metadata to bypass.
- No module named PIL/numpy/scipy: run the dependency command above.
- Access denied: check the destination and its Windows write permissions.
- Interrupted build: don't launch WoW until installation status is clear.
  Forced termination or power loss during installation cannot be auto-rolled back.

BACKUPS AND SPACE
A full rebuild needs room for the existing textures, staged new textures,
and any older backups. TGA files are much larger than PNG exports. Backups
are not deleted automatically. Do not remove them until the new build passes
in-game checks.

OCEAN TILE OPTIMIZATION
The builder now omits tiles that are exactly uniform opaque ocean after
cleanup, at every zoom level, for Kalimdor, Eastern Kingdoms, and Zephras Isle.
Any remaining non-ocean pixel keeps its tile. Dungeons and WMO maps are not
subject to this optimization. Original wow.export PNG files are unchanged.

Data.lua records omitted ocean tiles explicitly so the renderer does not
substitute larger terrain tiles. Missing/unknown tiles retain normal fallback.
The background uses one shared 8x8 Ocean.tga with the same pixels and texture
rendering path as exported water. Background regions do not overlap terrain,
preserving the movement-fade fix. In-game color/fade validation is still needed.

Close WoW, replace your old build script with this version, and run:
  py .\DANDEMap-build-all.py
The existing Pillow, numpy, and scipy dependencies are unchanged.
The script installs map data only, backs up replaced data files, and removes
obsolete ocean textures from rebuilt map directories. UI updates are separate.
Restart WoW afterward. Do not restore old renderer Lua alone while using the
optimized data; restore the matching data and Lua backup together if needed.

The report's ocean_optimization section lists tiles_omitted, tiles_written,
and texture_files_avoided for each rebuilt dataset. Absent export datasets
are preserved. Old backups continue to take disk space until removed manually.
Check continent and zone views, coastal zoom transitions, and movement fade.
If a seam remains, send a screenshot and the new DANDEMap-build-report.json,
and say whether you were standing still or moving.

AZSHARA OFFSHORE ARTIFACT EXCLUSIONS
Kalimdor tiles map45_20, map46_20, and map47_20 are explicitly replaced with
uniform ocean before cleanup and downsampling, then omitted by the ocean
optimization. This removes their dev boundary lines at every zoom level,
including neighboring cleanup samples. Source PNG files remain untouched.
The report records explicit_kalimdor_exclusions. These coordinates are listed
in KALIMDOR_EXCLUDED_TILES near the top of the script; review/remove entries
if a future Forever update adds real terrain there. No other new exclusions
are applied. Rerun the full builder with WoW closed to apply this change.
