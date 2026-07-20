import tempfile
import unittest
from pathlib import Path

from pdf2word.storage import WorkspaceStore


class WorkspaceStoreTests(unittest.TestCase):
    def test_create_job_makes_expected_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = WorkspaceStore(Path(tmp)).create_job()
            self.assertTrue(workspace.input_dir.is_dir())
            self.assertTrue(workspace.parser_outputs_dir.is_dir())
            self.assertTrue(workspace.ir_dir.is_dir())
            self.assertTrue(workspace.output_dir.is_dir())
            self.assertTrue(workspace.validation_dir.is_dir())
            self.assertTrue(workspace.traces_dir.is_dir())


if __name__ == "__main__":
    unittest.main()

