"""Run the frozen11 complete stage regressions against the private12 parent.

Only test import/author literals differ. Production functions, hashes, browser
producer and dispatcher are not substituted. Mock ports remain explicitly offline.
"""
from scripts.deployment import auto_resume12_parent as parent

path = parent.ROOT / 'tests/unit/test_auto_resume11.py'
source = path.read_text(encoding='utf-8')
source = source.replace('auto_resume11_parent as p', 'auto_resume12_parent as p')
source = source.replace("'source11'", "'source12'").replace("'successor11-author'", "'successor12-author'")
exec(compile(source, str(path) + ':private12-regressions', 'exec'), globals())


class Protocol12Tests(StageTests):
    # This subclass deliberately runs the whole stage corpus a second time with
    # schema/artifact assertions in every setup, not just a synthetic dispatcher.
    def setUp(self):
        super().setUp()
        self.assertEqual(p.load(self.folder / 'manifest.json')['schema'], 12)
        self.assertIs(p.prepare.__globals__, vars(p))
        self.assertIs(p.checked.__globals__, vars(p))
        self.assertIs(p.advance.__globals__, vars(p))
        self.assertIs(p.cleanup.__globals__, vars(p))

    def accepted(self, phase, reference):
        value = super().accepted(phase, reference)
        request = p.load(self.folder / (phase + '-request.json'))
        self.assertEqual(request['schema'], 12)
        tool = (self.folder / (phase + '-tool.js')).read_text(encoding='utf-8')
        self.assertIn('request.schema === 12', tool)
        self.assertNotIn('request.schema === 11', tool)
        return value