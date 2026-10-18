import math
import tempfile
import unittest
from pathlib import Path
from firemedia.playlists import Track, expand_sources, parse_playlist, write_playlist, load_state, save_state
from firemedia.visualizer import Bar, advance_bar, frequency_levels
from firemedia.order import PlaybackOrder

class PlaylistTests(unittest.TestCase):
    def setUp(self):
        # Windows may return an 8.3 alias for TEMP; production normalizes paths.
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
    def tearDown(self): self.temp.cleanup()
    def test_utf8_bom_relative_and_url(self):
        p=self.root/'mix.m3u8'
        p.write_text('\ufeff#EXTM3U\n#EXTINF:42,夜の音\n音楽.flac\nhttps://example.org/live.m3u8\n',encoding='utf-8')
        tracks=parse_playlist(p)
        self.assertEqual(tracks[0].source,str(self.root/'音楽.flac'))
        self.assertEqual(tracks[0].title,'夜の音');self.assertEqual(tracks[0].duration,42)
        self.assertEqual(tracks[1].source,'https://example.org/live.m3u8')
    def test_hls_is_not_split_into_segments(self):
        p=self.root/'live.m3u8';p.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nsegment.ts\n')
        self.assertEqual(expand_sources([p]),[Track.from_source(str(p))])
    def test_master_hls_is_one_stream(self):
        p=self.root/'master.m3u8';p.write_text('#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100000\nvariant/stream.m3u8\n')
        self.assertEqual(len(expand_sources([p])),1)
        self.assertEqual(expand_sources([p])[0].source,str(p))
    def test_nested_cycle_is_bounded(self):
        a=self.root/'a.m3u';b=self.root/'b.m3u';a.write_text('b.m3u\n');b.write_text('a.m3u\nsong.mp3\n')
        self.assertEqual([t.title for t in expand_sources([a])],['song'])
    def test_export_roundtrip_unicode_spaces_and_urls(self):
        tracks=[Track.from_source(str(self.root/'music'/'a b.flac'),'Žlutá'),Track.from_source('https://example.org/live.m3u8')]
        p=self.root/'saved.m3u8';write_playlist(p,tracks)
        restored=parse_playlist(p)
        self.assertEqual(restored,tracks)
    def test_export_full_paths_by_default_relative_only_when_requested(self):
        media=self.root/'music'/'song.flac'
        tracks=[Track.from_source(str(media))]
        full=self.root/'full.m3u8';relative=self.root/'relative.m3u8'
        write_playlist(full,tracks);write_playlist(relative,tracks,relative=True)
        self.assertEqual(full.read_text().splitlines()[-1],str(media))
        self.assertEqual(relative.read_text().splitlines()[-1],'music/song.flac')
        self.assertEqual(parse_playlist(relative),tracks)

    def test_literal_percent_and_nested_relative_paths(self):
        media=self.root/'music';media.mkdir();song=media/'100%20real.flac';song.touch()
        lists=self.root/'lists';lists.mkdir()
        playlist=lists/'mix.m3u8';playlist.write_text('../music/100%20real.flac\n')
        self.assertEqual(parse_playlist(playlist)[0].source,str(song))

    def test_atomic_state(self):
        p=self.root/'state.json';save_state(p,{'queue':[],'name':'音'});self.assertEqual(load_state(p)['name'],'音')
        p.write_text('{bad');self.assertEqual(load_state(p),{})
    def test_directory_drop(self):
        (self.root/'a.mp3').touch();(self.root/'b.mp4').touch();(self.root/'ignore.txt').touch()
        self.assertEqual(len(expand_sources([self.root])),2)

class PhysicsTests(unittest.TestCase):
    def test_attack_reaches_peak_in_one_frame_even_while_falling(self):
        bar=Bar(height=160,velocity=-500,cap=300)
        advance_bar(bar,20,1/60)
        advance_bar(bar,220,1/60)
        self.assertEqual(bar.height,220)
        advance_bar(bar,260,1/30)
        self.assertEqual(bar.height,260)

    def test_release_is_smooth_monotonic_and_does_not_undershoot(self):
        bar=Bar(height=200,cap=205)
        previous=bar.height
        for _ in range(180):
            advance_bar(bar,40,1/60)
            self.assertGreaterEqual(bar.height,40)
            self.assertLessEqual(bar.height,previous)
            previous=bar.height
        self.assertAlmostEqual(bar.height,40,places=5)

    def test_unsmoothed_bars_follow_both_directions(self):
        bar=Bar(height=100)
        advance_bar(bar,200,1/60,physics=False)
        self.assertEqual(bar.height,200)
        advance_bar(bar,20,1/60,physics=False)
        self.assertEqual(bar.height,20)

    def test_frequency_bands_match_custom_count(self):
        import numpy as np
        spectrum=np.linspace(.001,.1,1025)
        for count in (8,24,64,96,128,256):
            levels=frequency_levels(spectrum,count)
            self.assertEqual(len(levels),count)
            self.assertTrue(all(0<=level<=1 for level in levels))

    def test_caps_have_gravity_and_rebound_independently(self):
        bar=Bar(height=40,cap=120,cap_velocity=0)
        advance_bar(bar,40,1/60)
        self.assertLess(bar.cap_velocity,0);self.assertGreater(bar.cap,bar.height+5)
        hit=False
        for _ in range(240):
            falling=bar.cap_velocity<0
            advance_bar(bar,40,1/120)
            if falling and bar.cap_velocity>0:
                hit=True;break
        self.assertTrue(hit,'The floating cap must rebound after hitting the bar')
        self.assertGreaterEqual(bar.cap,bar.height+5)
    def test_rising_bar_launches_cap(self):
        bar=Bar(height=0,cap=5)
        for _ in range(20): advance_bar(bar,180,1/120)
        self.assertGreater(bar.cap_velocity,0)
        self.assertGreater(bar.cap,bar.height)
    def test_caps_still_bounce_with_bar_springs_disabled(self):
        bar=Bar(height=20,cap=100)
        advance_bar(bar,20,.05,physics=False)
        self.assertEqual(bar.height,20);self.assertLess(bar.cap_velocity,0)
        self.assertGreater(bar.cap,25)
    def test_stable_at_low_detail_rate(self):
        bar=Bar()
        for i in range(3000):
            advance_bar(bar,200*(1+math.sin(i*.1))/2,1/30,tension=280)
            self.assertTrue(math.isfinite(bar.height+bar.cap));self.assertGreaterEqual(bar.cap,bar.height+5-1e-6)
        self.assertLess(bar.cap,1000)

class OrderTests(unittest.TestCase):
    def test_repeat_off_stops_at_end(self):
        o=PlaybackOrder();self.assertIsNone(o.next(2,3,automatic=True))
    def test_repeat_playlist_and_track(self):
        o=PlaybackOrder();self.assertEqual(o.next(2,3,loop='Playlist',automatic=True),0)
        self.assertEqual(o.next(1,3,loop='Track',automatic=True),1)
    def test_shuffle_is_finite_without_repeats(self):
        for mode in ['On','Every loop']:
            o=PlaybackOrder();current=0;seen={0}
            for _ in range(5):
                current=o.next(current,6,mode,automatic=True);self.assertNotIn(current,seen);seen.add(current)
            self.assertIsNone(o.next(current,6,mode,automatic=True))
    def test_manual_next_wraps(self):
        self.assertEqual(PlaybackOrder().next(2,3),0)

if __name__=='__main__': unittest.main()
