import shutil
import subprocess
import unittest
from pathlib import Path


class WalkCollisionTests(unittest.TestCase):
    def test_synthetic_wall_front_back_and_slide(self):
        node=shutil.which('node')
        if not node:
            self.skipTest('Node.js is not installed; run walk_collision_probe.mjs on a development machine')
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([node,str(root/'tests/walk_collision_probe.mjs')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS synthetic walk collision',result.stdout)
