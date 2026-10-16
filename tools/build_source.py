"""Create a source archive without build outputs, local state, or credentials."""
import argparse
from pathlib import Path
import sys
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from firemedia import __version__

DIRECTORIES=('firemedia','packaging','tools','tests','examples','docs','.github','legacy')
FILES=('pyproject.toml','MANIFEST.in','README.md','LICENSE','CONTRIBUTING.md','SECURITY.md',
       'CHANGELOG.md','.gitignore','.gitattributes','firemedia.desktop','run.sh','BUILD-WINDOWS.cmd',
       'LOGO DESIGN.svg','logo128.png','logo2k.png','Emblem.svg','Emblem.png')
SUFFIXES={'.py','.ps1','.spec','.iss','.md','.txt','.json','.toml','.yaml','.yml','.xml',
          '.svg','.png','.js','.html','.css','.sh','.cmd'}
EXCLUDED={'__pycache__','.git','.venv','.venv-build','build','dist','vendor','.aws','.codex','.agents','state.json'}


def source_paths(root=ROOT):
    root=Path(root)
    paths=[root/name for name in FILES if (root/name).is_file()]
    for name in DIRECTORIES:
        for path in (root/name).rglob('*'):
            relative=path.relative_to(root)
            source_file=path.suffix.lower() in SUFFIXES or path.name in ('LICENSE','COPYING','COPYRIGHT')
            if path.is_file() and not path.name.startswith('.env') and source_file and not EXCLUDED.intersection(relative.parts):paths.append(path)
    return sorted((p for p in paths if not p.is_symlink()),key=lambda p:p.relative_to(root).as_posix())


def build_source(output,root=ROOT,version=__version__):
    root=Path(root);output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(output,'w',ZIP_DEFLATED,compresslevel=9) as archive:
        for path in source_paths(root):
            relative=path.relative_to(root).as_posix()
            info=ZipInfo(f'FireMedia-{version}/{relative}',date_time=(1980,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED;info.create_system=3
            mode=0o755 if relative in ('run.sh',) else 0o644
            info.external_attr=(0o100000|mode)<<16
            archive.writestr(info,path.read_bytes())
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist'/f'FireMedia-{__version__}-source.zip')
    args=parser.parse_args();print(build_source(args.output))


if __name__=='__main__':main()
