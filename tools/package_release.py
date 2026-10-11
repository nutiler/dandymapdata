"""Verify and ZIP an existing DandyMapData pack; never modify the installed pack."""
import argparse
import hashlib
import json
import re
import struct
import time
import zipfile
from pathlib import Path

from lupa import LuaRuntime

REPO = Path(__file__).resolve().parents[1]
LIMIT = 2 * 1024**3
BLOCK = 1024**2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    pack = args.pack.resolve(strict=True)
    output = args.output.resolve()
    if output == pack or pack in output.parents:
        raise ValueError('Release output must be outside the installed texture pack.')
    output.mkdir(parents=True, exist_ok=True)
    toc = (pack / 'DandyMapData.toc').read_text(encoding='utf-8-sig')
    version = re.search(r'^## Version:\s*(\S+)', toc, re.M).group(1)
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
        raise ValueError('Unexpected texture-pack version.')
    if '## Interface: 16001' not in toc:
        raise ValueError('Unexpected client Interface version.')
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute((pack / 'Data.lua').read_text(encoding='utf-8-sig'))
    lua.execute((pack / 'WMOExports.lua').read_text(encoding='utf-8-sig'))
    data = lua.globals().DANDEMapData
    assert data.version == 1 and data.maps is not None and data.tiles is not None
    required = {'DandyMapData.toc', 'Data.lua', 'WMOExports.lua', 'WMORecords.json', 'Ocean.tga'}
    maps = []
    for _, m in data.maps.items():
        assert m.right > m.left and m.bottom > m.top
        assert m.textureRoot == 'Interface\\AddOns\\DandyMapData\\Tiles\\' + m.id + '\\'
        assert m.extension == '.tga'
        tile_count = ocean_count = 0
        for key, exists in data.tiles[m.id].items():
            assert re.fullmatch(r'[0-7]/[0-9]+/[0-9]+', key)
            if exists:
                required.add('Tiles/' + m.id + '/' + key + '.tga')
                tile_count += 1
            else:
                ocean_count += 1
        maps.append({'id': m.id, 'name': m.name, 'tiles': tile_count, 'omitted_ocean_tiles': ocean_count})
    actual = {p.relative_to(pack).as_posix(): p for p in pack.rglob('*') if p.is_file()}
    missing = sorted(required - actual.keys())
    if missing:
        raise ValueError('Missing catalog files: ' + repr(missing[:10]))
    # Only addon data, artwork, and public placement metadata belong in the ZIP.
    allowed_root = required & {'DandyMapData.toc', 'Data.lua', 'WMOExports.lua', 'WMORecords.json', 'Ocean.tga'}
    allowed_root.add('README.md')
    unexpected = [name for name in actual if name not in allowed_root and not name.startswith(('Tiles/', 'Metadata/'))]
    if unexpected:
        raise ValueError('Unexpected installed files: ' + repr(unexpected))
    for name, path in actual.items():
        if path.is_symlink():
            raise ValueError('Symlink is not release data: ' + name)
        if name.endswith('.json'):
            text = path.read_text(encoding='utf-8-sig')
            json.loads(text)
            if re.search(r'(?i)(?:[a-z]:[\\/]|token|password|api[_-]?key)', text):
                raise ValueError('Private path/credential-like content in metadata: ' + name)
        if name.endswith('.tga'):
            with path.open('rb') as stream:
                header = stream.read(18)
            ident, cmap, kind = header[:3]
            width, height, bits = struct.unpack_from('<HHB', header, 12)
            assert cmap == 0 and kind == 2 and bits in (24, 32) and width > 0 and height > 0, name
            assert path.stat().st_size >= 18 + ident + width * height * (bits // 8), name
    zip_path = output / ('DandyMapData-' + version + '.zip')
    if zip_path.exists():
        raise FileExistsError('Preserve the previous release ZIP; choose a new output folder.')
    # README is a release-specific override; the installed pack remains untouched.
    readme = (REPO / 'README.md').read_bytes()
    entries = []
    started = time.monotonic()
    print(json.dumps({'phase': 'validated_source', 'version': version, 'maps': len(maps), 'files': len(actual)}), flush=True)
    with zipfile.ZipFile(zip_path, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for index, (name, path) in enumerate(sorted(actual.items()), 1):
            before = path.stat()
            info = zipfile.ZipInfo('DandyMapData/' + name, (2026, 10, 11, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info._compresslevel = 6
            digest = hashlib.sha256()
            size = 0
            with archive.open(info, 'w', force_zip64=True) as destination:
                if name == 'README.md':
                    destination.write(readme)
                    digest.update(readme)
                    size = len(readme)
                else:
                    with path.open('rb') as source:
                        while chunk := source.read(BLOCK):
                            destination.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Source changed during packaging: ' + name)
            entries.append({'path': name, 'bytes': size, 'sha256': digest.hexdigest()})
            if index % 500 == 0:
                print(json.dumps({'phase': 'packaging', 'files_done': index, 'files_total': len(actual), 'seconds': round(time.monotonic() - started)}), flush=True)
        manifest = {'name': 'DandyMapData', 'version': version, 'interface': 16001, 'data_schema': 1, 'release_date': '2026-10-11', 'map_count': len(maps), 'maps': maps, 'files': entries}
        manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        archive.writestr('DandyMapData/MANIFEST.json', manifest_bytes)
    # Read every archived byte and compare the packaged hashes, including CRC checks.
    print(json.dumps({'phase': 'verifying_zip', 'bytes': zip_path.stat().st_size}), flush=True)
    with zipfile.ZipFile(zip_path) as archive:
        assert len(set(archive.namelist())) == len(entries) + 1
        for entry in entries:
            digest = hashlib.sha256()
            size = 0
            with archive.open('DandyMapData/' + entry['path']) as source:
                while chunk := source.read(BLOCK):
                    digest.update(chunk)
                    size += len(chunk)
            assert digest.hexdigest() == entry['sha256'] and size == entry['bytes'], entry['path']
        assert archive.read('DandyMapData/MANIFEST.json') == manifest_bytes
    if zip_path.stat().st_size >= LIMIT:
        raise ValueError('Verified ZIP exceeds GitHub asset limit; split packaging is required.')
    with zip_path.open('rb') as source:
        checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    (output / 'manifest.json').write_bytes(manifest_bytes)
    (output / 'SHA256SUMS.txt').write_text(checksum + '  ' + zip_path.name + '\n', encoding='utf-8')
    receipt = {'validation': 'passed', 'version': version, 'zip': str(zip_path), 'zip_bytes': zip_path.stat().st_size, 'sha256': checksum, 'map_count': len(maps), 'file_count': len(entries) + 1, 'installed_bytes': sum(e['bytes'] for e in entries) + len(manifest_bytes)}
    (output / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
