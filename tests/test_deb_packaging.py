"""Regression tests for packaging boundaries, relocation, and dependency metadata."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ros_platform import Target


SPEC = importlib.util.spec_from_file_location(
    'deb_packaging', Path(__file__).resolve().parents[1] / 'scripts/deb_packaging.py')
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class StagingTests(unittest.TestCase):
    distro = 'jazzy'

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.install = self.root / 'install'
        self.install.mkdir()
        self.prefix = Path('/opt/ros') / self.distro
        self.destination = self.root / 'payload' / self.prefix.relative_to('/')

    def write(self, name, contents):
        path = self.install / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def stage(self):
        packaging.stage_install(self.install, self.destination, [self.root], self.prefix)

    def test_package_hooks_relocate_without_shipping_workspace_setup(self):
        self.write('setup.bash', 'must not replace ROS setup')
        self.write('_local_setup_util_sh.py', 'workspace helper')
        self.write('.colcon_install_layout', 'merged')
        self.write('share/example/local_setup.sh', f'prefix="{self.install}"\n')
        self.write('share/example/package.dsv', 'source;share/example/local_setup.sh\n')
        self.write('share/ament_index/resource_index/parent_prefix_path/example', str(self.install))
        self.stage()
        self.assertFalse((self.destination / 'setup.bash').exists())
        self.assertFalse((self.destination / '_local_setup_util_sh.py').exists())
        self.assertFalse((self.destination / '.colcon_install_layout').exists())
        self.assertEqual((self.destination / 'share/example/local_setup.sh').read_text(),
                         f'prefix="{self.prefix}"\n')
        self.assertEqual((self.destination / 'share/example/package.dsv').read_text(),
                         'source;share/example/local_setup.sh\n')

    def test_source_bound_symlink_is_rejected(self):
        source = self.root / 'source.py'
        source.write_text('print(1)')
        (self.install / 'program').symlink_to(source)
        with self.assertRaisesRegex(packaging.PackagingError, 'symlink'):
            self.stage()

    def test_absolute_internal_library_symlink_becomes_relative(self):
        library = self.write('lib/libexample.so.1', 'library')
        library.with_name('libexample.so').symlink_to(library)
        self.stage()
        symlink = self.destination / 'lib/libexample.so'
        self.assertEqual(str(symlink.readlink()), 'libexample.so.1')
        self.assertEqual(symlink.read_text(), 'library')

    def test_absolute_library_symlink_chain_is_relocated(self):
        library = self.write('lib/libexample.so.1.0', 'library')
        library.with_name('libexample.so.1').symlink_to(library)
        library.with_name('libexample.so').symlink_to(library.with_name('libexample.so.1'))
        self.stage()
        self.assertEqual((self.destination / 'lib/libexample.so').read_text(), 'library')

    def test_unrecognized_runtime_path_is_rejected(self):
        self.write('share/example/config.yaml', f'data_path: {self.root}/src/data\n')
        with self.assertRaisesRegex(packaging.PackagingError, 'Unrelocated'):
            self.stage()

    def test_python_bytecode_is_not_shipped(self):
        path = self.write('lib/python3.12/site-packages/example/__pycache__/main.pyc', '')
        path.write_bytes(b'\0compiled')
        self.stage()
        self.assertEqual(list(self.destination.rglob('*.pyc')), [])

    def test_python_sdist_manifest_is_omitted_but_entry_points_are_kept(self):
        self.write('lib/example.egg-info/SOURCES.txt', str(self.root / 'build/example.egg-info'))
        self.write('lib/example.egg-info/entry_points.txt', '[console_scripts]\nhello = example:main\n')
        self.stage()
        self.assertFalse((self.destination / 'lib/example.egg-info/SOURCES.txt').exists())
        self.assertTrue((self.destination / 'lib/example.egg-info/entry_points.txt').exists())

    @unittest.skipUnless(shutil.which('cc') and shutil.which('readelf'), 'requires native build tools')
    def test_elf_with_build_directory_rpath_is_rejected(self):
        executable = self.install / 'example'
        subprocess.run(['cc', '-x', 'c', '-', '-o', str(executable),
                        '-Wl,-rpath,' + str(self.root / 'build')],
                       input='int main(void) { return 0; }\n', text=True, check=True)
        with self.assertRaisesRegex(packaging.PackagingError, 'ELF dynamic metadata'):
            self.stage()

    def test_installed_underlay_file_collision_is_rejected(self):
        self.write('lib/example.txt', 'new content')
        self.stage()
        underlay = self.root / 'underlay'
        (underlay / 'lib').mkdir(parents=True)
        (underlay / 'lib/example.txt').write_text('existing ROS content')
        with self.assertRaisesRegex(packaging.PackagingError, 'collides'):
            packaging.verify_payload(self.destination, [], underlay)


class HumbleStagingTests(StagingTests):
    distro = 'humble'


class DependencyTests(unittest.TestCase):
    @staticmethod
    def dependency(name, enabled=True, **versions):
        return SimpleNamespace(name=name, evaluated_condition=enabled,
                               **{f'version_{key}': versions.get(key)
                                  for key in ('lt', 'lte', 'eq', 'gte', 'gt')})

    def test_internal_and_disabled_dependencies_are_excluded(self):
        resolver = packaging.Resolver({}, Target('jazzy', 'noble', 'amd64'))
        resolver.cache = {'external': ('apt', ['libexternal1'])}
        package = SimpleNamespace(name='example', exec_depends=[
            self.dependency('internal'), self.dependency('disabled', False),
            self.dependency('external', gte='1.2')])
        internal = SimpleNamespace(name='internal', exec_depends=[])
        self.assertEqual(resolver.dependencies([package, internal], ['exec']),
                         {'libexternal1 (>= 1.2)'})

    def test_unresolved_key_fails(self):
        resolver = packaging.Resolver({}, Target('jazzy', 'noble', 'amd64'))
        with patch.object(packaging, 'run', return_value='#gem\nunavailable\n'):
            with self.assertRaisesRegex(packaging.PackagingError, 'only APT and pip'):
                resolver.resolve('unavailable')

    def test_rosdep_resolves_for_selected_ubuntu_and_ros_distro(self):
        for distro, codename in [('jazzy', 'noble'), ('humble', 'jammy')]:
            with self.subTest(distro=distro):
                resolver = packaging.Resolver({}, Target(distro, codename, 'arm64'))
                with patch.object(packaging, 'run', return_value=f'#apt\nros-{distro}-rclpy\n') as run:
                    self.assertEqual(resolver.resolve('rclpy'), ('apt', [f'ros-{distro}-rclpy']))
                    run.assert_called_once_with(
                        ['rosdep', 'resolve', '--rosdistro', distro, '--os=ubuntu:' + codename, 'rclpy'],
                        env={}, capture=True)

    def test_control_includes_target_conflicts_and_runtime_dependencies(self):
        for distro, codename in [('jazzy', 'noble'), ('humble', 'jammy')]:
            for architecture in ('amd64', 'arm64'):
                with self.subTest(distro=distro, architecture=architecture):
                    self.check_metadata(Target(distro, codename, architecture))

    def check_metadata(self, target):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'LICENSE').write_text('Example license')
            stage = root / 'payload'
            stage.mkdir()
            config = {'package': {'name': 'test-bundle',
                                  'maintainer': 'Test <test@example.invalid>',
                                  'description': 'Test bundle', 'license_files': ['LICENSE']}}
            packaging.write_metadata(stage, config, [SimpleNamespace(name='example_node', version='1.0')],
                                     {target.package_name('ros-core'), 'libexample1 (>= 1.2)'},
                                     '1.0-1', target, root)
            control = (stage / 'DEBIAN/control').read_text()
            self.assertIn(f'Package: ros-{target.distro}-test-bundle\n', control)
            self.assertIn(f'Architecture: {target.architecture}\n', control)
            self.assertIn(f'Conflicts: ros-{target.distro}-example-node\n', control)
            self.assertIn('libexample1 (>= 1.2)', control)
            self.assertIn('example_node 1.0',
                          (stage / f'usr/share/doc/ros-{target.distro}-test-bundle/workspace-packages').read_text())
            self.assertTrue((stage / 'DEBIAN/md5sums').read_text())


if __name__ == '__main__':
    unittest.main()
