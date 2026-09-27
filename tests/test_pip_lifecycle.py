"""Real dpkg/pip coexistence check; opt in only inside a disposable root container."""

import base64
import hashlib
import io
import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from deb_packaging import write_metadata
from package_extras import stage_extras
from python_dependencies import collect_python_dependencies
from ros_platform import detect_target


@unittest.skipUnless(os.environ.get('ROS_DEB_TEST_DISPOSABLE') == '1' and os.geteuid() == 0,
                     'requires an explicitly disposable root container')
class PipLifecycleTests(unittest.TestCase):
    def test_two_debs_share_pip_distribution_without_dpkg_file_collisions(self):
        target = detect_target()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'src/vendor_consumer'
            source.mkdir(parents=True)
            (source / 'LICENSE').write_text('Test fixture license\n')
            wheels = source / 'wheels'
            wheels.mkdir()
            wheel = wheels / 'ros_skeleton_fixture-1.0-py3-none-any.whl'
            metadata = 'ros_skeleton_fixture-1.0.dist-info'
            files = {
                'ros_skeleton_fixture/__init__.py': b'VALUE = 42\n',
                f'{metadata}/METADATA': b'Metadata-Version: 2.1\nName: ros-skeleton-fixture\nVersion: 1.0\n',
                f'{metadata}/WHEEL': b'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
            }
            record = io.StringIO()
            writer = csv.writer(record)
            for name, contents in files.items():
                digest = base64.urlsafe_b64encode(hashlib.sha256(contents).digest()).rstrip(b'=').decode()
                writer.writerow([name, 'sha256=' + digest, len(contents)])
            writer.writerow([f'{metadata}/RECORD', '', ''])
            files[f'{metadata}/RECORD'] = record.getvalue().encode()
            with zipfile.ZipFile(wheel, 'w') as archive:
                for name, contents in files.items():
                    archive.writestr(name, contents)
            # Exercise a real public requirement fetched through TUNA as well.
            (source / 'requirements.txt').write_text('typing-extensions==4.12.2\n')
            package = SimpleNamespace(name='vendor_consumer', version='1.0.0',
                                      filename=str(source / 'package.xml'), licenses=[])
            python = collect_python_dependencies([package])
            artifacts = []
            names = []
            configs = []
            (root / 'packaging').mkdir()
            try:
                for suffix in ('one', 'two'):
                    config = {'package': {'name': 'skeleton-fixture-' + suffix,
                                          'maintainer': 'Test <test@example.invalid>',
                                          'description': 'Disposable pip lifecycle fixture'}}
                    name = target.package_name(config['package']['name'])
                    names.append(name)
                    stage = root / suffix
                    installed_config = target.prefix / 'share' / name / 'settings.yaml'
                    staged_config = stage / installed_config.relative_to('/')
                    staged_config.parent.mkdir(parents=True)
                    staged_config.write_text('setting: default\n')
                    (root / 'packaging/conffiles').write_text(str(installed_config) + '\n')
                    configs.append(installed_config)
                    apt = stage_extras(stage, root, config, [package], target, python)
                    write_metadata(stage, config, [], apt, '1.0-1', target, root)
                    deb = root / (name + '.deb')
                    subprocess.run(['dpkg-deb', '--build', '--root-owner-group', str(stage), str(deb)], check=True)
                    artifacts.append(deb)
                    subprocess.run(['dpkg', '-i', str(deb)], check=True)
                    installed_config.write_text('setting: operator\n')
                    payload = subprocess.check_output(['dpkg-query', '-L', name], text=True)
                    self.assertIn('.whl', payload)
                    self.assertNotIn('site-packages', payload)
                    self.assertNotIn('dist-packages', payload)
                subprocess.run(['/usr/bin/python3', '-c',
                                'import ros_skeleton_fixture, typing_extensions; assert ros_skeleton_fixture.VALUE == 42'], check=True)
                subprocess.run(['dpkg', '--force-confold', '-i', str(artifacts[1])], check=True)
                self.assertEqual(configs[1].read_text(), 'setting: operator\n')
                subprocess.run(['dpkg', '--remove', names[0]], check=True)
                self.assertEqual(configs[0].read_text(), 'setting: operator\n')
                subprocess.run(['dpkg', '--purge', names[0]], check=True)
                self.assertFalse(configs[0].exists())
                # Removing one bundle must leave the other bundle's pip dependency.
                subprocess.run(['/usr/bin/python3', '-c', 'import ros_skeleton_fixture'], check=True)
                subprocess.run(['dpkg', '--purge', names[1]], check=True)
                self.assertFalse(configs[1].exists())
                subprocess.run(['/usr/bin/python3', '-c', 'import ros_skeleton_fixture'], check=True)
            finally:
                subprocess.run(['dpkg', '--purge', *names], check=False)


if __name__ == '__main__':
    unittest.main()
