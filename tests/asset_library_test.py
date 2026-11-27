"""Library casting must preserve identity, enforce coverage and never create missing images."""
import json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from storytoon import asset_library as lib
from storytoon.schema import Storyboard,CharacterDef,LocationDef,Shot,CharacterInShot,Line

def story(gender='female',age='young',action='talk',style='cutout'):
    return Storyboard(title='Một chuyện khác',style=style,
      characters=[CharacterDef(id='mai',name='Mai',gender=gender,age=age,description='tóc dài áo xanh')],
      locations=[LocationDef(id='nha',name='Nhà',description='phòng có cửa gỗ',time_of_day='indoor')],
      shots=[Shot(id='s001',location='nha',framing='wide',characters=[CharacterInShot(id='mai',action=action)],
                  lines=[Line(speaker='mai',text='Lời thoại được giữ nguyên.')])])

class LibraryTests(unittest.TestCase):
    def test_gender_age_style_and_portrait_coverage(self):
        sb=story()
        lib.assign(sb)
        lib.validate(sb)
        entry=next(e for e in lib.catalog()['characters'] if e['id']==sb.characters[0].asset_id)
        self.assertEqual(entry['gender'],'female')
        self.assertEqual(sb.characters[0].id,'mai')
        self.assertEqual(sb.characters[0].name,'Mai')
        if entry['coverage']=='portrait': self.assertEqual(sb.shots[0].framing,'medium')
        fixture=lib.catalog()
        next(e for e in fixture['characters'] if e['id']==sb.characters[0].asset_id)['coverage']='portrait'
        with patch.object(lib,'catalog',return_value=fixture):
            sb.shots[0].framing='wide'
            lib.assign(sb)
            self.assertEqual(sb.shots[0].framing,'medium')
            lib.validate(sb)
        sb.characters[0].asset_id='chu_tu'
        with self.assertRaises(lib.MissingAssets):lib.validate(sb)
        child=story(age='child',action='walk')
        adults_only=lib.catalog()
        adults_only['characters']=[e for e in adults_only['characters'] if e.get('age')!='child']
        with patch.object(lib,'catalog',return_value=adults_only):
            lib.assign(child)
            self.assertIsNone(child.characters[0].asset_id)
            with self.assertRaises(lib.MissingAssets):lib.validate(child)
        stick=story(gender='male',age='child',style='stick')
        lib.assign(stick)
        with self.assertRaises(lib.MissingAssets):lib.validate(stick)

    def test_empty_library_is_read_only_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            sb=story()
            lib.assign(sb,root=root)
            with self.assertRaises(lib.MissingAssets):lib.validate(sb,root=root)
            self.assertEqual(list(root.rglob('*')),[])

    def test_ai_only_copies_casting_decisions(self):
        sb=story()
        response=sb.model_dump()
        response['title']='AI rewrite'
        response['characters'][0].update(name='Wrong name',id='mai',asset_id='co_lan')
        response['locations'][0]['asset_id']='cho_dem'
        response['shots']=[]
        with patch('storytoon.chatgpt.generate',return_value=json.dumps(response)):
            lib.ai_assign(sb)
        self.assertEqual(sb.title,'Một chuyện khác')
        self.assertEqual(sb.characters[0].name,'Mai')
        self.assertEqual(len(sb.shots),1)
        self.assertEqual(sb.shots[0].lines[0].text,'Lời thoại được giữ nguyên.')
        self.assertEqual(sb.characters[0].asset_id,'co_lan')

    def test_existing_prop_insert_preserves_dialogue(self):
        sb=story(gender='male')
        sb.shots[0].characters[0].prop='banh_bao'
        fixture=lib.catalog()
        fixture['inserts'].append({'id':'existing_bun_fixture','props':['banh_bao'],'style':'cutout',
                                  'ready':True,'label':'Existing test insert'})
        with patch.object(lib,'catalog',return_value=fixture):
            lib.assign(sb)
            lib.validate(sb)
        self.assertEqual(sb.shots[0].location,'insert:existing_bun_fixture')
        self.assertEqual(sb.shots[0].lines[0].speaker,'mai')
        self.assertEqual(sb.shots[0].characters,[])

    def test_render_never_substitutes_a_placeholder(self):
        from storytoon.render.location import load_location
        with self.assertRaises(FileNotFoundError):load_location('__missing_library_location__')
        with self.assertRaises(FileNotFoundError):load_location('insert:__missing_library_insert__')

    def test_render_loads_physical_asset_for_story_identity(self):
        from storytoon.render.compositor import ShotRenderer
        sb=story()
        sb.characters[0].asset_id='co_lan'
        sb.locations[0].asset_id='cho_dem'
        sb.shots[0].framing='close'
        renderer=ShotRenderer(sb.shots[0],sb,None,width=320,height=180,fps=12)
        self.assertEqual(renderer.actors[0].cis.id,'mai')
        self.assertEqual(renderer.actors[0].rig.id,'co_lan')
        self.assertEqual(renderer.frame(0).shape,(180,320,4))

if __name__=='__main__':unittest.main()
