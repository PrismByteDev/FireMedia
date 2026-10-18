import tempfile,unittest,json
from pathlib import Path
from firemedia.formats import (BUILTIN_PRESETS,subtitle_spec,export_subtitle,import_subtitle,
    export_app_playlist,import_app_playlist,matching_srt,unique_name)
from firemedia.playlists import Track

class FormatTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def test_subtitle_preset_roundtrip(self):
        spec=dict(BUILTIN_PRESETS['Glow'],font='Serif',delay=1.25,particles=True,stroke_color='#123456')
        path=self.root/'art.firemsub';export_subtitle(path,'My art',spec)
        self.assertEqual(import_subtitle(path),('My art',spec))
    def test_reject_invalid_preset_fields(self):
        for field,value in [('size',float('nan')),('color','url(evil)'),('particles','yes'),('delay',200),('stroke_width',-1)]:
            with self.assertRaises(ValueError):subtitle_spec({field:value})
    def test_wrong_format_rejected(self):
        path=self.root/'bad.firemsub';path.write_text('{"format":"unknown","version":1}')
        with self.assertRaises(ValueError):import_subtitle(path)
    def test_firempl_roundtrip_and_relative_import(self):
        path=self.root/'mix.firempl';tracks=[Track.from_source(str(self.root/'song.flac'),'Song')]
        export_app_playlist(path,'Mix',tracks);self.assertEqual(import_app_playlist(path),('Mix',tracks))
        data=json.loads(path.read_text());data['tracks'][0]['source']='music/song.flac';path.write_text(json.dumps(data))
        self.assertEqual(import_app_playlist(path)[1][0].source,str(self.root/'music/song.flac'))
    def test_unsafe_track_protocol_rejected(self):
        path=self.root/'bad.firempl';path.write_text(json.dumps({'format':'FireMediaPlaylist','version':1,'name':'Bad','tracks':[{'source':'javascript:alert(1)'}]}))
        with self.assertRaises(ValueError):import_app_playlist(path)
    def test_firempl_omits_duration_and_loads_legacy_duration(self):
        path=self.root/'mix.firempl'
        export_app_playlist(path,'Mix',[Track.from_source(str(self.root/'song.flac'),'Custom title',123)])
        data=json.loads(path.read_text())
        self.assertEqual(data['tracks'],[{'source':str(self.root/'song.flac'),'title':'Custom title'}])
        self.assertEqual(import_app_playlist(path)[1][0].title,'Custom title')
        for duration in (-1,123):
            data['tracks'][0]['duration']=duration;path.write_text(json.dumps(data))
            self.assertEqual(import_app_playlist(path)[1][0].title,'Custom title')
    def test_matching_srt_and_ambiguous_fallback(self):
        movie=self.root/'Movie.mp4';movie.touch();first=self.root/'other.srt';first.touch()
        self.assertEqual(matching_srt(str(movie)),first)
        (self.root/'second.srt').touch();self.assertIsNone(matching_srt(str(movie)))
        exact=self.root/'MOVIE.SRT';exact.touch();self.assertEqual(matching_srt(str(movie)),exact)
        self.assertIsNone(matching_srt('https://example.org/video.mp4'))
    def test_import_name_collision_does_not_overwrite(self):
        self.assertEqual(unique_name('Cinema',{'Cinema','Cinema (2)'}),'Cinema (3)')
