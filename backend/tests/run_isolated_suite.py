import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(Path('backend/tests').resolve()))
import test_core

fixture = Path('/tmp/phase3-info-suite-fresh.sqlite3')
assert not fixture.exists()
test_core.DB = fixture

def retain_fixture(self, *args, **kwargs):
    if self != fixture and not (self.parent == test_core.ROOT and self.name in ('test-info-flow.db', 'test-info-flow.db-wal', 'test-info-flow.db-shm')):
        raise RuntimeError('unexpected_unlink_blocked')
    return None

Path.unlink = retain_fixture
suite = unittest.defaultTestLoader.discover('backend/tests', pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(not result.wasSuccessful())
