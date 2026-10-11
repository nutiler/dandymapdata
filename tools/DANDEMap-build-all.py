"""Build cleaned terrain and native WMO maps into DandyMapData. Close WoW first.
Python dependencies: Pillow numpy scipy. Source exports are never changed.
"""
import argparse,json,re,shutil,tempfile,uuid,math
from pathlib import Path
from functools import lru_cache
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
OCEAN=(1,29,41,255)
# User-confirmed offshore dev artifacts; review this list if Forever adds land here.
KALIMDOR_EXCLUDED_TILES={(45,20),(46,20),(47,20)}
REPORT={"maps":[],"wmo":[],"warnings":[]}

def quote(value):
    return json.dumps(value, ensure_ascii=False)

def discover(folder):
    found = {}
    for p in sorted(Path(folder).rglob('*.png')):
        match = re.fullmatch(r'map(\d+)_(\d+)\.png', p.name, re.I)
        if not match:
            continue
        xy = tuple(map(int, match.groups()))
        if not all(0 <= n < 64 for n in xy):
            raise ValueError(f'Unexpected ADT coordinate: {p}')
        if xy in found:
            raise ValueError(f'Duplicate coordinate {xy}: select ONE map folder, not all exports. {p}')
        with Image.open(p) as im:
            if im.size != (512, 512):
                raise ValueError(f'Expected native 512x512 tile, got {im.size}: {p}')
            im.verify()
        found[xy] = p
    if not found:
        raise ValueError(f'No mapX_Y.png tiles found in {folder}')
    return found

def scan_root(root):
    root=Path(root)
    if not root.is_dir():
        raise ValueError(f'Export folder not found: {root}')
    plans=[]
    names={'azeroth':'Eastern Kingdoms','kalimdor':'Kalimdor','blackfathom':'Blackfathom Deeps','collin':'Ruins of Lordaeron','deadminesinstance':'The Deadmines','gnomereganinstance':'Gnomeregan','monastery':'Scarlet Monastery','razorfendowns':'Razorfen Downs','razorfenkraulinstance':'Razorfen Kraul','shadowfang':'Shadowfang Keep','stormwindjail':'The Stockade','stormwindprison':'Stormwind Prison','sunkentemple':'Sunken Temple','uldaman':'Uldaman','wailingcaverns':'Wailing Caverns'}
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        slug=re.sub(r'[^a-z0-9-]','-',directory.name.lower())
        native=[p for p in directory.rglob('*.png') if re.fullmatch(r'map(\d+)_(\d+)\.png',p.name,re.I)]
        if native:
            tiles=discover(directory);xs,ys=zip(*tiles)
            plans.append(('local-'+slug,names.get(slug,directory.name)+' (native)',tiles,(min(xs),min(ys),max(xs)+1,max(ys)+1),None))
        for meta_path in sorted(directory.rglob('*_wmo_minimap.json')):
            meta=json.loads(meta_path.read_text(encoding='utf-8-sig'))
            image_path=meta_path.with_suffix('.png')
            with Image.open(image_path) as im:
                width,height=im.size;im.verify()
            declared=meta.get('image',{})
            if declared.get('width')!=width or declared.get('height')!=height:
                raise ValueError(f'WMO image dimensions disagree with metadata: {meta_path}')
            # A WMO export is already a composed image. Tile it without rotating,
            # stretching or guessing relationships between floors.
            tiles={}
            for y in range((height+511)//512):
                for x in range((width+511)//512):
                    tiles[x,y]=(image_path,(x*512,y*512,min(width,(x+1)*512),min(height,(y+1)*512)))
            stem=re.sub(r'[^a-z0-9-]','-',meta_path.stem.lower())
            plans.append(('local-wmo-'+slug+'-'+stem,str(meta.get('map_name',directory.name))+' (interior)',tiles,(0,0,width/512,height/512),meta_path))
    if not plans:
        raise ValueError('No mapX_Y.png tiles or paired *_wmo_minimap.json/PNG exports found under the map folders.')
    if len({p[0] for p in plans})!=len(plans):
        raise ValueError('Duplicate map identifiers: keep one export per map folder.')
    return plans

def lua(v):
    if v is None:return 'nil'
    if isinstance(v,bool):return 'true' if v else 'false'
    if isinstance(v,(int,float)):
        if not math.isfinite(v):raise ValueError('Non-finite metadata')
        return repr(v)
    if isinstance(v,str):return json.dumps(v,ensure_ascii=False)
    if isinstance(v,list):return '{'+','.join(lua(x) for x in v)+'}'
    if isinstance(v,dict):return '{'+','.join('['+lua(k)+']='+lua(x) for k,x in v.items())+'}'
    raise ValueError('Unsupported metadata type')

def water(a):
    r,g,b=a.astype(np.float32).transpose(2,0,1)
    return (g>r*1.25)&(b>r*.8)&(r<65)&(g<100)&(b<125)

def make_cleaner(tiles,mid):
    @lru_cache(maxsize=128)
    def read(x,y):
        if mid=='local-kalimdor' and (x,y) in KALIMDOR_EXCLUDED_TILES:
            return np.full((512,512,3),OCEAN[:3],dtype=np.uint8)
        with Image.open(tiles[x,y]) as im:return np.array(im.convert('RGB'))
    w=(max(x for x,y in tiles)+1)*64;h=(max(y for x,y in tiles)+1)*64
    valid=np.zeros((h,w),bool);small=np.zeros((h,w,3),np.uint8)
    for x,y in tiles:
        small[y*64:(y+1)*64,x*64:(x+1)*64]=np.array(Image.fromarray(read(x,y)).resize((64,64),Image.Resampling.BOX));valid[y*64:(y+1)*64,x*64:(x+1)*64]=True
    candidate=water(small)&valid;labels,_=ndi.label(candidate)
    edge=ndi.binary_dilation(~valid);edge[[0,-1],:]=True;edge[:,[0,-1]]=True
    ids=np.unique(labels[candidate&edge]);ids=ids[ids>0]
    coarse=ndi.binary_dilation(np.isin(labels,ids)&candidate,iterations=2)
    artifacts={(47,20),(46,20),(45,20),(0,0),(0,1),(0,2),(1,0),(2,0)}
    def clean(x,y):
        a=read(x,y);patch=np.empty((640,640,3),np.uint8);patch[:]=OCEAN[:3]
        for dx in [-1,0,1]:
            for dy in [-1,0,1]:
                if (x+dx,y+dy) not in tiles:continue
                src=read(x+dx,y+dy);lx=64+dx*512;ly=64+dy*512;l=max(0,lx);t=max(0,ly);r=min(640,lx+512);b=min(640,ly+512)
                patch[t:b,l:r]=src[t-ly:b-ly,l-lx:r-lx]
        dist=ndi.distance_transform_edt(water(patch))[64:576,64:576]
        region=np.array(Image.fromarray(coarse[y*64:(y+1)*64,x*64:(x+1)*64]).resize((512,512),Image.Resampling.NEAREST))
        t=np.clip((dist-3)/28,0,1);alpha=t*t*(3-2*t)*region
        result=np.rint(a*(1-alpha[:,:,None])+np.array(OCEAN[:3])*alpha[:,:,None]).astype('uint8')
        if mid=='local-kalimdor' and (x,y) in artifacts:
            r,g,b=a.astype(float).transpose(2,0,1)
            band=(abs(r-g)<12)&(r>45)&(b<r+8)
            # Never wipe future terrain simply because it shares an old artifact coordinate.
            dark=(np.max(a,axis=2)<=32)&((np.max(a,axis=2).astype(int)-np.min(a,axis=2))<=10)
            if band.any() and np.all(water(a)|band|dark):result[:]=OCEAN[:3]
            elif band.any():REPORT['warnings'].append(f'{mid} {x},{y}: changed artifact tile; kept terrain, manual review needed')
        return Image.fromarray(result).convert('RGBA')
    return clean

def zephra_cleaner(tiles):
    x0=min(x for x,y in tiles);y0=min(y for x,y in tiles)
    w=(max(x for x,y in tiles)-x0+1)*512;h=(max(y for x,y in tiles)-y0+1)*512
    if w*h>64000000:raise ValueError('Unexpected Zephra dimensions; needs review')
    candidate=np.ones((h,w),bool)
    for (x,y),p in tiles.items():
        with Image.open(p) as im:a=np.array(im.convert('RGBA'))
        candidate[(y-y0)*512:(y-y0+1)*512,(x-x0)*512:(x-x0+1)*512]=(np.max(a[:,:,:3],axis=2)<=2)|(a[:,:,3]==0)
    seed=np.zeros(candidate.shape,bool);seed[[0,-1],:]=True;seed[:,[0,-1]]=True
    mask=ndi.binary_propagation(seed&candidate,mask=candidate)
    def clean(x,y):
        with Image.open(tiles[x,y]) as im:a=np.array(im.convert('RGBA'))
        a[mask[(y-y0)*512:(y-y0+1)*512,(x-x0)*512:(x-x0+1)*512]]=OCEAN
        return Image.fromarray(a)
    return clean

def write(im,path,hover=False):
    import io
    path.parent.mkdir(parents=True,exist_ok=True)
    buf=io.BytesIO();im.save(buf,format='TGA',compression=None);path.write_bytes(buf.getvalue())
    with Image.open(path) as test:
        test.load()
        if test.size!=(512,512) or not np.array_equal(np.asarray(test),np.asarray(im)):raise ValueError('Output verification failed: '+str(path))
    if hover:
        a=np.array(im);d=np.max(np.abs(a[:,:,:3].astype(float)-np.array(OCEAN[:3])),axis=2)
        a[:,:,3]=np.rint(np.clip((d-8)/35,0,1)*255).astype('uint8')
        Image.fromarray(a).save(path.with_name(path.stem+'_hover.tga'),format='TGA',compression=None)

def build(dest,tiles,mid):
    pretty=mid in ['local-kalimdor','local-azeroth','local-2991']
    if mid=='local-kalimdor':
        REPORT['explicit_kalimdor_exclusions']=[list(xy) for xy in sorted(set(tiles)&KALIMDOR_EXCLUDED_TILES)]
    cleaner=make_cleaner(tiles,mid) if mid in ['local-kalimdor','local-azeroth'] else zephra_cleaner(tiles) if mid=='local-2991' else None
    dest.mkdir(parents=True,exist_ok=True)
    keys={}
    def emit(im,key):
        ocean=pretty and np.all(np.asarray(im)==np.array(OCEAN,dtype=np.uint8))
        keys[key]=not bool(ocean)
        if not ocean:write(im,dest/(key+'.tga'),pretty)
    for i,((x,y),source) in enumerate(sorted(tiles.items()),1):
        if cleaner:im=cleaner(x,y)
        elif isinstance(source,tuple):
            p,box=source
            with Image.open(p) as full:im=Image.new('RGBA',(512,512));im.paste(full.convert('RGBA').crop(box),(0,0))
        else:
            with Image.open(source) as full:im=full.convert('RGBA')
        if pretty:
            canvas=Image.new('RGBA',(512,512),OCEAN);canvas.alpha_composite(im);im=canvas
        emit(im,f'7/{x}/{y}')
        if i%100==0:print(f'  native {i}/{len(tiles)}',flush=True)
    previous=set(tiles)
    for level in range(6,-1,-1):
        parents={(x//2,y//2) for x,y in previous}
        for px,py in sorted(parents):
            canvas=Image.new('RGBA',(512,512),OCEAN if pretty else (0,0,0,0))
            for dx in range(2):
                for dy in range(2):
                    x,y=2*px+dx,2*py+dy
                    if (x,y) in previous and keys[f'{level+1}/{x}/{y}']:
                        with Image.open(dest/f'{level+1}/{x}/{y}.tga') as im:canvas.paste(im.resize((256,256),Image.Resampling.LANCZOS),(dx*256,dy*256))
            emit(canvas,f'{level}/{px}/{py}')
        previous=parents
    omitted=sum(not value for value in keys.values())
    REPORT.setdefault('ocean_optimization',{})[mid]={'tiles_omitted':omitted,'tiles_written':len(keys)-omitted,'texture_files_avoided':omitted*2 if pretty else 0}
    print(f'  {omitted} ocean tiles omitted; {len(keys)-omitted} terrain tiles kept',flush=True)
    return keys

def wmo_meta(path):
    m=json.loads(path.read_text(encoding='utf-8-sig'))
    # Known wow.export schema: source image X points south, image Y points west.
    # Current addon supports origin-placed global WMOs. Unknown placement is not guessed.
    for k in ['map_id','ppu','image','corners']:
        if k not in m:raise ValueError(f'{path}: missing {k}')
    if not isinstance(m['map_id'],int) or m['map_id']<0:raise ValueError(f'{path}: missing engine map_id (not wmo_id)')
    modf=m.get('modf')
    if modf:
        def vector(v):
            if isinstance(v,dict):return [v.get(k) for k in ['x','y','z']]
            return v
        for field in ['position','rotation']:
            vec=vector(modf.get(field))
            if not isinstance(vec,list) or len(vec)!=3 or any(not isinstance(v,(int,float)) or abs(v)>1e-6 for v in vec):
                raise ValueError(f'{path}: non-origin/unknown MODF {field}; export report needed to add its transform safely')
        if modf.get('scale')!=1024:raise ValueError(f'{path}: unsupported MODF scale; metadata review needed')
    tl=m['corners']['top_left'];br=m['corners']['bottom_right'];ppu=m['ppu'];w=m['image']['width'];h=m['image']['height']
    vals=[ppu,w,h,tl['world_x'],tl['world_y'],br['world_x'],br['world_y']]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in vals) or ppu<=0:raise ValueError('Invalid WMO numeric metadata: '+str(path))
    if abs((tl['world_x']-br['world_x'])*ppu-w)>2 or abs((br['world_y']-tl['world_y'])*ppu-h)>2:
        raise ValueError('WMO corners disagree with image dimensions: '+str(path))
    return dict(stem=re.sub(r'[^a-z0-9-]','-',path.stem.lower()),instance=m['map_id'],width=w,height=h,ppu=ppu,north=tl['world_x'],west=tl['world_y'])

def parse_existing(text):
    if not text:return {},{}
    pieces=re.split(r'\},\s*tiles\s*=\s*\{',text,maxsplit=1)
    if len(pieces)!=2:raise ValueError('Unrecognized existing Data.lua; refusing to discard maps')
    rows={}
    for row in re.findall(r'\{id="[^"\n]+"[^\n]*?\},?',pieces[0]):
        mid=re.search(r'id="([^"]+)"',row)[1];rows[mid]=row.rstrip(',')+','
    catalogs={mid:{key:value=='true' for key,value in re.findall(r'\["(\d+/\d+/\d+)"\]\s*=\s*(true|false)',body)} for mid,body in re.findall(r'\["([^"]+)"\]\s*=\s*\{([^}]*)\}',pieces[1],re.S)}
    if not rows or set(rows)!=set(catalogs):raise ValueError('Existing catalog parse failed; no files changed')
    return rows,catalogs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--maps-root',type=Path,default=Path.home()/'wow.export'/'maps')
    p.add_argument('--output',type=Path,default=Path(r'C:\Program Files (x86)\World of Warcraft\_classic_beta_\Interface\AddOns\DandyMapData'))
    p.add_argument('--scan-only',action='store_true',help='Validate exports and write report without building/installing')
    p.add_argument('--report',type=Path,default=Path('DANDEMap-build-report.json'))
    args=p.parse_args()
    if not args.maps_root.is_dir():
        print('Export folder not found:',args.maps_root,flush=True)
        selected=None
        try:
            import tkinter as tk
            from tkinter import filedialog
            window=tk.Tk();window.withdraw()
            try:
                window.attributes('-topmost',True)
                selected=filedialog.askdirectory(parent=window,title='Select wow.export maps folder (contains azeroth, kalimdor, 2991, dungeons)',mustexist=True)
            finally:window.destroy()
        except Exception:
            print('Folder picker unavailable. Paste the full maps folder path, or press Enter to cancel.',flush=True)
            try:selected=input('Maps folder: ').strip().strip('"')
            except EOFError:selected=None
        if not selected:raise ValueError('No folder selected. Run again with --maps-root "YOUR ACTUAL MAPS FOLDER"')
        args.maps_root=Path(selected)
        if not args.maps_root.is_dir():raise ValueError('Selected folder does not exist: '+str(args.maps_root))
    source=args.maps_root.resolve();root=args.output.resolve()
    REPORT['maps_root']=str(source);REPORT['output']=str(root)
    print('Using exports: '+str(source),flush=True)
    if source==root or source in root.parents or root in source.parents:raise ValueError('Source and installed addon must be separate')
    plans=scan_root(source)
    # Every WMO-like export must have its matching PNG and JSON. No silent omissions.
    for f in source.rglob('*'):
        if f.is_file() and '_wmo_minimap' in f.stem.lower() and f.suffix.lower() in ['.png','.json']:
            partner=f.with_suffix('.json' if f.suffix.lower()=='.png' else '.png')
            if not partner.is_file():raise ValueError('Missing WMO partner: '+str(partner))
    meta={};metadata_errors=[]
    for mid,name,tiles,bounds,path in plans:
        REPORT['maps'].append(dict(id=mid,name=name,native_tiles=len(tiles),bounds=bounds,metadata=str(path) if path else None))
        if path:
            m=json.loads(path.read_text(encoding='utf-8-sig'));REPORT['wmo'].append(dict(path=str(path),metadata=m))
            try:meta[mid]=wmo_meta(path)
            except (ValueError,KeyError,TypeError) as e:metadata_errors.append(str(e))
    if metadata_errors:
        REPORT['metadata_errors']=metadata_errors
        raise ValueError('WMO metadata needs review: '+'; '.join(metadata_errors))
    if args.scan_only:
        print(f'Scan complete: {len(plans)} map datasets. Report: {args.report}');return
    root.parent.mkdir(parents=True,exist_ok=True)
    existing=(root/'Data.lua').read_text(encoding='utf-8-sig') if (root/'Data.lua').exists() else ''
    rows,catalogs=parse_existing(existing)
    stage=Path(tempfile.mkdtemp(prefix='DandyMapData-build-',dir=root.parent));backup=root.parent/('DandyMapData-backup-'+uuid.uuid4().hex[:12]);moved=[];installed=[]
    try:
        # Retain exported metadata for maps not included in this export.
        allmeta={}
        if (root/'WMORecords.json').exists():
            allmeta=json.loads((root/'WMORecords.json').read_text(encoding='utf-8'))
            if not isinstance(allmeta,dict):raise ValueError('Invalid saved WMO records')
        allmeta.update(meta)
        for mid,name,tiles,bounds,path in plans:
            print(f'{name}: {len(tiles)} native tiles',flush=True)
            catalogs[mid]=build(stage/'Tiles'/mid,tiles,mid)
            left,top,right,bottom=bounds
            if mid=='local-2991':name='Zephras Isle'
            texture='Interface\\AddOns\\DandyMapData\\Tiles\\'+mid+'\\'
            rows[mid]='{id=%s,name=%s,left=%s,top=%s,right=%s,bottom=%s,textureRoot=%s,extension=".tga"},'%(quote(mid),quote(name),left,top,right,bottom,quote(texture))
            if path:
                target=stage/'Metadata'/(mid+'.json');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        lines=['DANDEMapData = {version=1, maps={']+[rows[k] for k in sorted(rows)]+['},tiles={']
        for mid in sorted(catalogs):lines+=['['+quote(mid)+']={']+['['+quote(k)+']='+('true' if value else 'false')+',' for k,value in catalogs[mid].items()]+['},']
        lines+=['}}'];(stage/'Data.lua').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        Image.new('RGBA',(8,8),OCEAN).save(stage/'Ocean.tga',format='TGA',compression=None)
        (stage/'WMORecords.json').write_text(json.dumps(allmeta,indent=2),encoding='utf-8')
        (stage/'WMOExports.lua').write_text('DANDEMapWMOExports='+lua(list(allmeta.values()))+'\n',encoding='utf-8')
        # Use maintained release metadata, not stale installed TOC entries.
        templates=Path(__file__).resolve().parent
        toc=(templates/'DandyMapData.toc').read_text(encoding='utf-8-sig')
        (stage/'DandyMapData.toc').write_text(toc,encoding='utf-8')
        shutil.copy2(templates/'LocalTextures-README.md',stage/'README.md')
        # Install only after all maps validate. Preserve absent maps and unrelated data.
        backup.mkdir()
        paths=[Path('Tiles')/m[0] for m in plans]+[Path('Metadata')/(mid+'.json') for mid in meta]+[Path(n) for n in ['Data.lua','WMOExports.lua','WMORecords.json','DandyMapData.toc','Ocean.tga','README.md']]
        for rel in paths:
            live=root/rel;old=backup/rel;new=stage/rel
            live.parent.mkdir(parents=True,exist_ok=True)
            if live.exists():old.parent.mkdir(parents=True,exist_ok=True);live.rename(old);moved.append((live,old))
            new.rename(live);installed.append(live)
        REPORT['backup']=str(backup);REPORT['installed']=True
        print('DONE. Restart WoW. Backup: '+str(backup))
    except BaseException:
        for live in reversed(installed):
            if live.is_dir():shutil.rmtree(live)
            elif live.exists():live.unlink()
        for live,old in reversed(moved):old.rename(live)
        raise
    finally:shutil.rmtree(stage,ignore_errors=True)


if __name__=='__main__':
    try:main()
    except Exception as e:
        REPORT['error']=str(e);print('STOPPED:',e);raise SystemExit(1)
    finally:
        # Report survives validation failures and includes discovered WMO sidecars.
        import sys
        report=Path(sys.argv[sys.argv.index('--report')+1]) if '--report' in sys.argv else Path('DANDEMap-build-report.json')
        report.write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
