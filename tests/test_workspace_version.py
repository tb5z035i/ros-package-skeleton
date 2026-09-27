"""Version identity should follow replacement packages without framework edits."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from workspace_version import development_version


class VersionTests(unittest.TestCase):
    def test_numeric_highest_manifest_version_sets_development_base(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for version in ('1.9.0', '1.10.0'):
                package = root / version
                package.mkdir()
                (package / 'package.xml').write_text(f'<package><version>{version}</version></package>')
                paths.append(str(package))
            with patch('workspace_version.subprocess.check_output', return_value='\n'.join(paths)):
                self.assertEqual(development_version(root, {'CI_PIPELINE_IID': '12', 'CI_COMMIT_SHORT_SHA': 'abc'}),
                                 '1.10.0~ci12+abc-1')

    def test_empty_workspace_cannot_silently_use_example_version(self):
        with patch('workspace_version.subprocess.check_output', return_value=''):
            with self.assertRaisesRegex(ValueError, 'No ROS packages'):
                development_version(Path('/missing'), {})


if __name__ == '__main__':
    unittest.main()
