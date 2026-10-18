"""Update trust boundaries, platform policy, atomic replacement and wake locks."""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from zipfile import ZipFile, ZipInfo
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from firemedia.update_core import (canonical, verify_manifest, version, atomic_json, read_json,
    install_windows, install_appimage, extract_windows, update_lock, download_package, REPOSITORY)
from firemedia.update_worker import check, main
from firemedia.update_platform import systemd_quote


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config=self.root/'updates.json'
        self.key=Ed25519PrivateKey.generate();self.keys={'test':self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex()}
        now=int(time.time())
        self.payload={'format':'FireMediaUpdate','schema':1,'repository':REPOSITORY,'channel':'stable','version':'1.2.3',
                      'issued':now-10,'expires':now+86400,'sequence':10,'min_updater':1,'assets':{}}
        for platform,filename in [('windows-x64','FireMedia-1.2.3-windows-x64.zip'),('appimage-x64','FireMedia-1.2.3-x86_64.AppImage')]:
            self.payload['assets'][platform]={'url':f'https://github.com/{REPOSITORY}/releases/download/v1.2.3/{filename}',
                                             'size':100,'sha256':'a'*64}
    def tearDown(self):self.temp.cleanup()
    def sign(self,payload=None):
        payload=deepcopy(self.payload if payload is None else payload)
        return {'payload':payload,'key_id':'test','signature':base64.b64encode(self.key.sign(canonical(payload))).decode()}
    def test_signature_and_tampering(self):
        signed=self.sign();self.assertEqual(verify_manifest(signed,keys=self.keys),self.payload)
        signed['payload']['assets']['windows-x64']['sha256']='b'*64
        with self.assertRaises(ValueError):verify_manifest(signed,keys=self.keys)
        with self.assertRaises(ValueError):verify_manifest(self.sign(),keys={})
    def test_expiry_replay_future_repository_and_platform_rejected(self):
        for change in ({'expires':0},{'issued':int(time.time())+900},{'repository':'other/repo'},
                       {'channel':'preview'},{'min_updater':999}):
            payload=dict(self.payload,**change)
            with self.subTest(change=change),self.assertRaises(ValueError):verify_manifest(self.sign(payload),keys=self.keys)
        with self.assertRaises(ValueError):verify_manifest(self.sign(),keys=self.keys,minimum_sequence=11)
        for key,value in [('url','https://evil.example/app.exe'),('size',-1),('sha256','bad')]:
            p=deepcopy(self.payload);p['assets']['windows-x64'][key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):verify_manifest(self.sign(p),keys=self.keys)
    def test_version_order_handles_numeric_and_preview_versions(self):
        self.assertGreater(version('0.10.0'),version('0.9.99'))
        self.assertLess(version('1.0.0rc2'),version('1.0.0'));self.assertLess(version('1.0.0a1'),version('1.0.0b1'))
        for bad in ('../app','v1.0.0','1.0.0;echo','1.0'):
            with self.assertRaises(ValueError):version(bad)
    def test_disabled_makes_no_discovery_or_download_requests(self):
        atomic_json(self.config,{'mode':'disabled'})
        with patch('firemedia.update_worker.discover') as discover:
            self.assertEqual(check(self.config,'appimage',self.root/'x')['status'],'disabled');discover.assert_not_called()
    def test_notify_portable_manual_do_not_install_and_toasts_coalesce(self):
        for kind in ('windows','portable','manual','appimage'):
            atomic_json(self.config,{'mode':'notify'})
            with patch('firemedia.update_worker.discover',return_value=(self.payload,{'mode':'notify'})),patch('firemedia.update_worker.current_version',return_value='0.1.0'),patch('firemedia.update_worker.install_windows') as windows,patch('firemedia.update_worker.install_appimage') as appimage,patch('firemedia.update_worker.native_notification',return_value=True):
                self.assertEqual(check(self.config,kind,self.root)['status'],'available');windows.assert_not_called();appimage.assert_not_called()
        state={'mode':'notify','notified':'1.2.3:available'}
        with patch('firemedia.update_worker.discover',return_value=(self.payload,state)),patch('firemedia.update_worker.native_notification') as notify:
            check(self.config,'portable',None);notify.assert_not_called()
    def test_automatic_and_explicit_installer_modes(self):
        for mode,manual in [('launch',False),('background',False),('notify',True)]:
            atomic_json(self.config,{'mode':mode})
            with patch('firemedia.update_worker.discover',return_value=(self.payload,{'mode':mode})),patch('firemedia.update_worker.current_version',return_value='0.1.0'),patch('firemedia.update_worker.install_windows') as install,patch('firemedia.update_worker.native_notification',return_value=True):
                self.assertEqual(check(self.config,'windows',self.root,install=manual)['status'],'installed');install.assert_called_once()
    def test_unsigned_or_broken_download_never_switches_installed_version(self):
        atomic_json(self.root/'current.json',{'version':'0.1.0'})
        def bad_download(asset,path):raise ValueError('hash mismatch')
        with patch('firemedia.update_core.download_package',side_effect=bad_download),self.assertRaises(ValueError):install_windows(self.root,self.payload)
        self.assertEqual(read_json(self.root/'current.json')['version'],'0.1.0');self.assertFalse((self.root/'versions/1.2.3').exists())
    def test_valid_windows_staging_keeps_old_files_and_switches_atomically(self):
        old=self.root/'versions/0.1.0';old.mkdir(parents=True);(old/'FireMedia.exe').write_bytes(b'old')
        atomic_json(self.root/'current.json',{'version':'0.1.0'})
        archive=self.root/'release.zip'
        with ZipFile(archive,'w') as package:
            package.writestr('FireMedia/FireMedia.exe',b'new');package.writestr('FireMedia/_internal/runtime.dll',b'runtime')
        with patch('firemedia.update_core.download_package',side_effect=lambda a,p:shutil.copyfile(archive,p)):
            self.assertTrue(install_windows(self.root,self.payload));self.assertFalse(install_windows(self.root,self.payload))
        self.assertEqual((old/'FireMedia.exe').read_bytes(),b'old');self.assertEqual(read_json(self.root/'current.json'),{'version':'1.2.3','previous':'0.1.0'})
    def test_archive_traversal_links_windows_aliases_and_duplicates_rejected(self):
        for name in ('FireMedia/../escape','/FireMedia/escape','FireMedia/C:/file','FireMedia/CON.txt','FireMedia/dir./file'):
            archive=self.root/'bad.zip'
            with ZipFile(archive,'w') as package:package.writestr(name,b'bad')
            destination=self.root/'stage'
            with self.subTest(name=name),self.assertRaises(ValueError):extract_windows(archive,destination)
            shutil.rmtree(destination)
        archive=self.root/'bad.zip';info=ZipInfo('FireMedia/link');info.external_attr=0o120777<<16
        with ZipFile(archive,'w') as package:package.writestr(info,'../../etc/passwd')
        with self.assertRaises(ValueError):extract_windows(archive,self.root/'stage')
    def test_appimage_replacement_keeps_previous_inode_and_rejects_invalid_format(self):
        image=self.root/'FireMedia.AppImage';image.write_bytes(b'old');image.chmod(0o755)
        content=b'\x7fELF'+b'\0'*4+b'AI\x02'+b'new image'
        with patch('firemedia.update_core.download_package',side_effect=lambda a,p:Path(p).write_bytes(content)):
            install_appimage(image,self.payload)
        self.assertEqual(image.read_bytes(),content);self.assertEqual(image.with_name(image.name+'.previous').read_bytes(),b'old')
        with patch('firemedia.update_core.download_package',side_effect=lambda a,p:Path(p).write_bytes(b'not ELF')),self.assertRaises(ValueError):install_appimage(image,self.payload)
        self.assertEqual(image.read_bytes(),content)
    def test_package_hash_is_verified(self):
        path=self.root/'download'
        def fetch(*args,**kwargs):path.write_bytes(b'tampered')
        with patch('firemedia.update_core.fetch',side_effect=fetch),self.assertRaises(ValueError):download_package(self.payload['assets']['windows-x64'],path)
    def test_lock_excludes_a_second_updater(self):
        with update_lock(self.config):
            with self.assertRaises(OSError):
                with update_lock(self.config):pass
    def test_notification_protocol_cannot_inject_arguments(self):
        for argv in (['firemedia-update:install','--config','anything'],['firemedia-update:restart --config x'],['firemedia-update:other']):
            with patch('firemedia.update_worker.helper_root') as root:
                self.assertEqual(main(argv),1);root.assert_not_called()
    def test_systemd_exec_escaping(self):
        text=systemd_quote('/tmp/100% "media"/FireMedia.AppImage')
        self.assertIn('100%%',text);self.assertIn('\\"media\\"',text);self.assertTrue(text.startswith('"'))


class WakeLockTests(unittest.TestCase):
    def test_windows_pause_video_and_release(self):
        from firemedia.wakelock import WakeLock
        call=Mock(return_value=1)
        with patch('firemedia.wakelock.sys.platform','win32'),patch('firemedia.wakelock.ctypes.windll',SimpleNamespace(kernel32=SimpleNamespace(SetThreadExecutionState=call)),create=True):
            wake=WakeLock();wake.update(True,False);self.assertEqual(call.call_args.args[0],0x80000001)
            count=call.call_count;wake.update(True,False);self.assertEqual(call.call_count,count)
            wake.update(True,True);self.assertEqual(call.call_args.args[0],0x80000003)
            wake.update(False);self.assertEqual(call.call_args.args[0],0x80000000);self.assertEqual(wake.flags,0)
    def test_linux_portal_suspend_and_idle_flags(self):
        from firemedia.wakelock import WakeLock
        with patch('firemedia.wakelock.sys.platform','linux'):
            wake=WakeLock()
            with patch.object(wake,'_request') as request:
                wake.update(True,False);self.assertEqual(wake.flags,4);request.assert_called_once()
                wake.update(True,True);self.assertEqual(wake.flags,12)
                wake.update(False);self.assertEqual(wake.flags,0)
