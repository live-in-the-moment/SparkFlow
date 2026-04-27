from __future__ import annotations

import unittest

from backend.core import _dataset_file_out_dir


class DatasetPathIsolationTests(unittest.TestCase):
    def test_same_stem_in_different_dirs_gets_distinct_output_dirs(self) -> None:
        base = _dataset_file_out_dir(__import__('pathlib').Path('out'), 'a/foo.dwg')
        other = _dataset_file_out_dir(__import__('pathlib').Path('out'), 'b/foo.dwg')
        self.assertNotEqual(str(base), str(other))


if __name__ == '__main__':
    unittest.main()
