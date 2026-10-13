import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launcher'))
from game_layout import find_game,resolve_settings
class GameLayoutTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.port=Path(self.temp.name);(self.port/'Game').mkdir()
    def tearDown(self):self.temp.cleanup()
    def dump(self,name):
        p=self.port/'Game'/name;p.mkdir();(p/'eboot.bin').touch();(p/'sce_sys').mkdir();(p/'sce_module').mkdir();return p
    def test_empty_or_iso_is_not_a_game(self):
        (self.port/'Game/own.iso').touch();self.assertIsNone(find_game(self.port))
    def test_detects_single_dump_and_preserves_valid_saved_choice(self):
        p=self.dump('CUSA01623');self.assertEqual(find_game(self.port),p)
        self.assertEqual(resolve_settings({},self.port)['game_dir'],str(p))
        self.assertEqual(resolve_settings({'game_dir':str(p),'language':'1'},self.port),{'game_dir':str(p),'language':'1'})
    def test_ambiguous_nonpreferred_dumps_require_choice(self):
        self.dump('A');self.dump('B');self.assertIsNone(find_game(self.port))
    def test_prefers_validated_title(self):
        self.dump('B');p=self.dump('CUSA01623');self.assertEqual(find_game(self.port),p)
if __name__=='__main__':unittest.main()
