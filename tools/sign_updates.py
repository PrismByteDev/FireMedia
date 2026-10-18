"""Sign the exact release packages using the dedicated Ed25519 publishing key."""
import base64
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from firemedia.update_core import canonical, REPOSITORY


def sign_release(directory, private_key, now=None):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    directory=Path(directory);inventory=json.loads((directory/'release-info.json').read_text())
    if inventory['prerelease']:return None
    if inventory['repository']!=REPOSITORY:raise ValueError('Signing is restricted to the FireMedia repository')
    assets={}
    for asset in inventory['assets']:
        platform={'windows-portable':'windows-x64','linux-appimage':'appimage-x64'}.get(asset['package'])
        if platform:assets[platform]={field:asset[field] for field in ('size','sha256','url')}
    if set(assets)!={'windows-x64','appimage-x64'}:raise ValueError('Both automatic update packages are required')
    now=int(time.time() if now is None else now)
    payload={'format':'FireMediaUpdate','schema':1,'repository':REPOSITORY,'channel':'stable',
             'version':inventory['version'],'tag':inventory.get('tag', 'v' + inventory['version']),
             'issued':now,'expires':now+365*86400,
             'sequence':now,'min_updater':1,'assets':assets}
    key=serialization.load_pem_private_key(private_key,password=None)
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('An Ed25519 signing key is required')
    from firemedia.update_core import read_json,verify_manifest
    envelope={'payload':payload,'key_id':'primary-2026','signature':base64.b64encode(key.sign(canonical(payload))).decode('ascii')}
    verify_manifest(envelope,now=now)
    path=directory/'update.json';path.write_text(json.dumps(envelope,indent=2)+'\n',encoding='utf-8')
    # Include the signed manifest in the normal release checksum inventory.
    from tools.prepare_release import checksum
    files=sorted(p for p in directory.iterdir() if p.name!='SHA256SUMS')
    (directory/'SHA256SUMS').write_text(''.join(f'{checksum(p)}  {p.name}\n' for p in files),encoding='utf-8')
    return path


if __name__=='__main__':
    secret=os.environ.get('FIREMEDIA_UPDATE_SIGNING_KEY','')
    if not secret:raise SystemExit('Configure the FIREMEDIA_UPDATE_SIGNING_KEY repository secret before releasing.')
    sign_release(sys.argv[1] if len(sys.argv)>1 else 'release-output',secret.encode('ascii'))
