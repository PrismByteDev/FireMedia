"""Build example .firemp ZIP packages from their editable source folders."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
output=root/'dist/plugins';output.mkdir(parents=True,exist_ok=True)
for folder in sorted((root/'examples/plugins').iterdir()):
    if not folder.is_dir():continue
    target=output/(folder.name+'.firemp')
    with ZipFile(target,'w',ZIP_DEFLATED) as package:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:package.write(path,path.relative_to(folder).as_posix())
    print(target)
