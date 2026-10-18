"""Validate a release version and assemble checksummed assets; never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from firemedia import __version__
from firemedia.update_core import RELEASE_ALIASES
from tools.build_source import build_source


def validate_tag(tag,version=__version__):
    if RELEASE_ALIASES.get(tag) == version:
        return False
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?',version) or tag!='v'+version:
        raise ValueError(f'Tag must match the app version: v{version}')
    return bool(re.search(r'(?:a|b|rc)\d+$',version))


def checksum(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def prepare_release(input_dir,output_dir,tag,repository='PrismByteDev/FireMedia'):
    preview=validate_tag(tag)
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('Invalid repository name')
    source=Path(input_dir);output=Path(output_dir)
    if source.resolve()==output.resolve():raise ValueError('Input and output folders must differ')
    packages=[
        (f'firemedia_{__version__}_all.deb',f'firemedia_{__version__}_all.deb','linux-deb','all'),
        ('FireMedia-windows-x64.zip',f'FireMedia-{__version__}-windows-x64.zip','windows-portable','x86_64'),
        (f'FireMedia-{__version__}-windows-x64-setup.exe',f'FireMedia-{__version__}-windows-x64-setup.exe','windows-installer','x86_64'),
        (f'FireMedia-{__version__}-x86_64.AppImage',f'FireMedia-{__version__}-x86_64.AppImage','linux-appimage','x86_64')]
    for filename,*_ in packages:
        path=source/filename
        if not path.is_file() or path.is_symlink() or not path.stat().st_size:raise ValueError(f'Missing or empty build asset: {filename}')
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('Release output folder must be empty')
    assets=[]
    for original,filename,kind,arch in packages:
        path=output/filename;shutil.copyfile(source/original,path)
        assets.append({'name':filename,'package':kind,'architecture':arch,'size':path.stat().st_size,
                       'sha256':checksum(path),'url':f'https://github.com/{repository}/releases/download/{tag}/{filename}'})
    build_source(output/f'FireMedia-{__version__}-source.zip')
    # Informational build inventory. This is NOT an authenticated updater manifest.
    inventory={'format':'FireMediaRelease','schema_version':1,'version':__version__,
               'tag':tag,'repository':repository,'prerelease':preview,'assets':assets}
    (output/'release-info.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
    files=sorted(output.iterdir())
    (output/'SHA256SUMS').write_text(''.join(f'{checksum(p)}  {p.name}\n' for p in files),encoding='utf-8')
    return inventory


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True);parser.add_argument('--repository',default='PrismByteDev/FireMedia')
    parser.add_argument('--input-dir',type=Path,default=ROOT/'dist')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'release-output')
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    if args.check_only:validate_tag(args.tag);print('Version matches '+args.tag)
    else:
        prepare_release(args.input_dir,args.output_dir,args.tag,args.repository)
        print('Release files prepared in '+str(args.output_dir))


if __name__=='__main__':main()
