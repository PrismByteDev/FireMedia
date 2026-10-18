"""Release metadata integrity, version checks, and clean source exports."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from firemedia import __version__
from tools.build_source import build_source,source_paths
from tools.prepare_release import validate_tag,prepare_release


class ReleaseTests(unittest.TestCase):
    def test_clean_source_export_is_reproducible_and_excludes_local_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files={'README.md':'public','LICENSE':'license','firemedia/main.py':'print(1)',
                   'packaging/README.md':'build','docs/UPDATES.md':'plan','.github/workflows/ci.yml':'workflow','legacy/web-prototype/LICENSE':'MIT',
                   'dist/app.exe':'binary','vendor/windows/tool.dll':'binary','.aws/credentials':'private',
                   'firemedia/state.json':'private','firemedia/.env.txt':'private','tests/private.key':'private',
                   'firemedia/__pycache__/old.py':'cached','state.json':'private','.env':'private'}
            for name,value in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
            a=build_source(root/'a.zip',root);b=build_source(root/'b.zip',root)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with ZipFile(a) as archive:
                names=archive.namelist();self.assertEqual(len(names),7)
                self.assertTrue(any(name.endswith('/legacy/web-prototype/LICENSE') for name in names))
                self.assertTrue(any(name.endswith('/.github/workflows/ci.yml') for name in names))
                self.assertFalse(any('private' in archive.read(name).decode() for name in names))
    def test_release_tag_must_match_current_version(self):
        self.assertFalse(validate_tag('v'+__version__))
        self.assertTrue(validate_tag('v0.3.0rc1','0.3.0rc1'))
        self.assertFalse(validate_tag('vBETA.0.0','0.3.0'))
        with self.assertRaises(ValueError):validate_tag('vBETA.0.0','0.3.1')
        for tag in ('main','v999.0.0','../bad','v'+__version__+'; echo bad'):
            with self.assertRaises(ValueError):validate_tag(tag)
    def test_release_inventory_hashes_match_every_packaged_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);inputs=root/'inputs';inputs.mkdir();output=root/'out'
            for name in (f'firemedia_{__version__}_all.deb','FireMedia-windows-x64.zip',f'FireMedia-{__version__}-windows-x64-setup.exe',f'FireMedia-{__version__}-x86_64.AppImage'):
                (inputs/name).write_bytes(('fixture for '+name).encode())
            inventory=prepare_release(inputs,output,'v'+__version__)
            self.assertEqual(inventory,json.loads((output/'release-info.json').read_text()))
            for asset in inventory['assets']:
                data=(output/asset['name']).read_bytes()
                self.assertEqual(len(data),asset['size']);self.assertEqual(hashlib.sha256(data).hexdigest(),asset['sha256'])
                self.assertTrue(asset['url'].startswith('https://github.com/PrismByteDev/FireMedia/releases/download/v'+__version__+'/'))
            for line in (output/'SHA256SUMS').read_text().splitlines():
                digest,name=line.split('  ',1);self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),digest)
            with ZipFile(output/f'FireMedia-{__version__}-source.zip') as archive:
                self.assertTrue(any(name.endswith('/LICENSE') for name in archive.namelist()))
                self.assertTrue(any(name.endswith('/docs/UPDATES.md') for name in archive.namelist()))
            with self.assertRaises(ValueError):prepare_release(inputs,output,'v'+__version__)
    def test_missing_package_and_invalid_repository_fail_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'out'
            with self.assertRaises(ValueError):prepare_release(root,output,'v'+__version__)
            self.assertFalse(output.exists())
            with self.assertRaises(ValueError):prepare_release(root,output,'v'+__version__,repository='../../bad')
