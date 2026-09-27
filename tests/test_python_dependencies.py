"""Exercise pip metadata, native wheel selection and generated package lifecycle."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from deb_packaging import Resolver
from install_python_dependencies import install
from package_extras import stage_extras
from python_dependencies import collect_python_dependencies, read_requirements
from ros_platform import Target


class PythonDependenciesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'src/driver'
        self.source.mkdir(parents=True)
        self.package = SimpleNamespace(name='driver', filename=str(self.source / 'package.xml'))
        self.target = Target('jazzy', 'noble', 'amd64')
        self.config = {'package': {'name': 'sample-app'}}

    def wheel(self, name='vendor_driver-1.0-py3-none-any.whl'):
        path = self.source / 'wheels' / name
        path.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('vendor_driver/__init__.py', 'VALUE = 42\n')
        return path

    def test_rosdep_pip_separates_installer_and_keeps_version_conditions(self):
        dependency = SimpleNamespace(name='vendor-pip', evaluated_condition=True,
                                     version_lt='2.0', version_lte=None, version_eq=None,
                                     version_gte='1.0', version_gt=None)
        self.package.exec_depends = [dependency]
        resolver = Resolver({}, self.target)
        with patch('deb_packaging.run', return_value='#pip\nvendor-driver\n'):
            self.assertEqual(resolver.dependencies([self.package], ['exec']), set())
            self.assertEqual(resolver.dependencies([self.package], ['exec'], 'pip'),
                             {'vendor-driver<2.0,>=1.0'})

    def test_collects_requirements_constraints_and_compatible_wheels(self):
        (self.source / 'requirements.txt').write_text('pymodbus>=3 # driver\n')
        (self.source / 'pip-constraints.txt').write_text('pymodbus==3.15.0\n')
        universal = self.wheel()
        self.wheel('vendor_driver-1.0-cp39-cp39-win_amd64.whl')
        result = collect_python_dependencies([self.package], ['other>=1'])
        self.assertEqual(result['requirements'], ['other>=1', 'pymodbus>=3'])
        self.assertEqual(result['constraints'], ['pymodbus==3.15.0'])
        self.assertEqual(result['wheels'], [{'package': 'driver', 'path': str(universal)}])

    def test_incompatible_and_pointer_wheels_fail_before_packaging(self):
        wheel = self.wheel('vendor_driver-1.0-cp39-cp39-win_amd64.whl')
        with self.assertRaisesRegex(ValueError, 'no compatible wheel'):
            collect_python_dependencies([self.package])
        wheel.unlink()
        self.wheel().write_text('version https://git-lfs.github.com/spec/v1\n')
        with self.assertRaisesRegex(ValueError, 'LFS pointer'):
            collect_python_dependencies([self.package])

    def test_ambiguous_vendor_versions_fail(self):
        self.wheel()
        self.wheel('vendor_driver-2.0-py3-none-any.whl')
        with self.assertRaisesRegex(ValueError, 'one version'):
            collect_python_dependencies([self.package])

    def test_requirements_reject_options_urls_and_local_paths(self):
        for line in ['--index-url https://other.invalid', '../vendor', 'vendor @ https://other.invalid/v.whl']:
            with self.subTest(line=line), self.assertRaises(ValueError):
                read_requirements(line, 'requirements.txt')

    def test_pip_uses_tuna_system_python_and_no_target_or_forced_upgrade(self):
        dependencies = {'requirements': ['shared>=1'], 'constraints': ['shared<2'],
                        'wheels': [{'path': 'wheels/vendor.whl'}]}
        with patch('install_python_dependencies.subprocess.run') as run:
            with patch.dict(os.environ, {'PIP_EXTRA_INDEX_URL': 'https://unwanted.invalid'}):
                install(dependencies, self.root)
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ['/usr/bin/python3', '-m', 'pip', 'install'])
        self.assertIn('https://pypi.tuna.tsinghua.edu.cn/simple', command)
        self.assertIn(str(self.root / 'wheels/vendor.whl'), command)
        self.assertNotIn('--target', command)
        self.assertNotIn('--upgrade', command)
        self.assertEqual(run.call_args.kwargs['env']['PIP_BREAK_SYSTEM_PACKAGES'], '1')
        self.assertNotIn('PIP_EXTRA_INDEX_URL', run.call_args.kwargs['env'])
        self.assertTrue(run.call_args.kwargs['check'])

    def test_empty_dependencies_do_not_invoke_pip(self):
        with patch('install_python_dependencies.subprocess.run') as run:
            install({'requirements': [], 'constraints': [], 'wheels': []}, self.root)
        run.assert_not_called()

    def test_deb_contains_wheel_archive_and_pip_postinst_but_no_uninstall(self):
        wheel = self.wheel()
        dependencies = collect_python_dependencies([self.package], ['shared>=1'])
        stage = self.root / 'payload'
        runtime = stage_extras(stage, self.root, self.config, [self.package], self.target, dependencies)
        resources = stage / 'opt/ros/jazzy/share/ros-jazzy-sample-app/python'
        self.assertEqual((resources / 'wheels/driver' / wheel.name).read_bytes(), wheel.read_bytes())
        manifest = json.loads((resources / 'dependencies.json').read_text())
        self.assertEqual(manifest['requirements'], ['shared>=1'])
        self.assertFalse(Path(manifest['wheels'][0]['path']).is_absolute())
        self.assertFalse(any(stage.rglob('site-packages')))
        self.assertEqual(runtime, {'python3-pip', 'ca-certificates'})
        self.assertFalse((stage / 'DEBIAN/prerm').exists())
        self.assertFalse((stage / 'DEBIAN/postrm').exists())
        postinst = stage / 'DEBIAN/postinst'
        subprocess.run(['sh', '-n', str(postinst)], check=True)
        self.assertIn('if [ "$1" = configure ]', postinst.read_text())
        self.assertTrue(postinst.stat().st_mode & 0o111)

    def test_service_templates_conffiles_and_installed_tests_are_staged(self):
        services = self.root / 'packaging/systemd'
        services.mkdir(parents=True)
        (services / 'sample-@ROS_DISTRO@@.service.in').write_text(
            '[Service]\nExecStart=/bin/bash -c "source @PREFIX@/setup.bash; ros2 launch driver run.launch.py"\n')
        (self.root / 'packaging/conffiles').write_text('@PREFIX@/share/driver/config/*.yaml\n')
        stage = self.root / 'payload'
        config = stage / 'opt/ros/jazzy/share/driver/config/settings.yaml'
        config.parent.mkdir(parents=True)
        config.write_text('setting: 1\n')
        tests = self.source / 'test/installed'
        tests.mkdir(parents=True)
        (tests / 'test_driver.py').write_text('def test_driver(): pass\n')
        stage_extras(stage, self.root, self.config, [self.package], self.target,
                     {'requirements': [], 'constraints': [], 'wheels': []})
        service = stage / 'usr/lib/systemd/system/sample-jazzy@.service'
        self.assertIn('/opt/ros/jazzy/setup.bash', service.read_text())
        self.assertEqual((stage / 'DEBIAN/conffiles').read_text(),
                         '/opt/ros/jazzy/share/driver/config/settings.yaml\n')
        self.assertTrue((stage / 'opt/ros/jazzy/share/ros-jazzy-sample-app/tests/driver/test_driver.py').is_file())
        for name in ('postinst', 'postrm'):
            hook = stage / 'DEBIAN' / name
            subprocess.run(['sh', '-n', str(hook)], check=True)
            text = hook.read_text()
            self.assertIn('daemon-reload', text)
            for verb in ('enable', 'start', 'restart', 'stop'):
                self.assertNotRegex(text, rf'systemctl.*\b{verb}\b')

    def test_unmatched_conffile_fails(self):
        (self.root / 'packaging').mkdir()
        (self.root / 'packaging/conffiles').write_text('@PREFIX@/share/missing.yaml\n')
        with self.assertRaisesRegex(ValueError, 'no installed files'):
            stage_extras(self.root / 'stage', self.root, self.config, [self.package], self.target,
                         {'requirements': [], 'constraints': [], 'wheels': []})


class CredentialTests(unittest.TestCase):
    def test_ci_credentials_only_go_to_https_on_the_gitlab_host(self):
        helper = Path(__file__).resolve().parents[1] / 'scripts/ci-git-credential'
        env = dict(os.environ, CI_JOB_TOKEN='test-token', CI_SERVER_HOST='gitlab.example', CI_SERVER_PORT='8443')
        for protocol, host, expected in [('https', 'gitlab.example', True),
                                         ('https', 'gitlab.example:8443', True),
                                         ('https', 'untrusted.example', False),
                                         ('http', 'gitlab.example', False)]:
            result = subprocess.run(['bash', str(helper), 'get'], env=env,
                                    input=f'protocol={protocol}\nhost={host}\n\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual('password=test-token' in result.stdout, expected)
            self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
