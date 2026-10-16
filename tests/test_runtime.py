"""Packaging paths must work independently of the launcher’s working directory."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from firemedia import runtime
from firemedia.sources import source_scheme, file_uri_path
from firemedia.playlists import Track, write_playlist


class RuntimeTests(unittest.TestCase):
    def test_frozen_ffmpeg_found_inside_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            tool = Path(temporary) / 'ffmpeg.exe';tool.touch()
            with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime.sys, 'frozen', True, create=True), patch.object(runtime.sys, '_MEIPASS', temporary, create=True):
                self.assertEqual(runtime.find_tool('ffmpeg'), str(tool))

    def test_drive_and_unc_paths_are_not_url_schemes(self):
        for source in ('C:/Music/song.flac', r'D:\Music\song.flac', r'\\server\share\song.flac'):
            self.assertEqual(source_scheme(source), '')
        self.assertEqual(source_scheme('https://example.org/live.m3u8'), 'https')
        self.assertEqual(source_scheme('file:///C:/Music/song.flac'), 'file')
        self.assertEqual(source_scheme('javascript:alert(1)'), 'javascript')

    def test_windows_file_uri_decode(self):
        with patch('firemedia.sources.os.name', 'nt'):
            self.assertEqual(file_uri_path('file:///C:/My%20Music/song.flac'), 'C:/My Music/song.flac')
            self.assertEqual(file_uri_path('file://server/share/song.flac'), '//server/share/song.flac')
        self.assertEqual(file_uri_path('file:///home/user/My%20Music/song.flac'), '/home/user/My Music/song.flac') if os.name != 'nt' else None

    def test_windows_mpv_dependency_search(self):
        with tempfile.TemporaryDirectory() as temporary:
            dll = Path(temporary) / 'libmpv-2.dll';dll.touch()
            with patch.object(runtime.sys, 'platform', 'win32'), patch.object(runtime, 'runtime_directories', return_value=[Path(temporary)]), patch.object(runtime.os, 'add_dll_directory', create=True) as add_directory, patch.object(runtime.ctypes, 'CDLL') as load:
                self.assertIs(runtime.load_mpv(), load.return_value)
                load.assert_called_once_with(str(dll));add_directory.assert_called_once_with(temporary)

    def test_relative_playlist_cross_drive_falls_back_to_full_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'mix.m3u8'
            track = Track.from_source(str(Path(temporary) / 'song.flac'))
            with patch('firemedia.playlists.os.path.relpath', side_effect=ValueError('different drives')):
                write_playlist(output, [track], relative=True)
            self.assertEqual(output.read_text().splitlines()[-1], track.source)
