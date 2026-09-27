"""Build real ROS packages against third-party libraries and inspect the deb."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import deb_packaging as packaging
from ros_platform import detect_target
from workspace_version import development_version


@unittest.skipUnless(all(shutil.which(tool) for tool in ('colcon', 'cmake', 'cc', 'dpkg-deb', 'rosdep')),
                     'requires native ROS packaging tools')
class ThirdPartyBuildTests(unittest.TestCase):
    def test_build_uses_third_party_but_deb_contains_only_src(self):
        try:
            target = detect_target()
        except ValueError as error:
            self.skipTest(str(error))
        if not (target.prefix / 'share/ament_cmake/cmake/ament_cmakeConfig.cmake').is_file():
            self.skipTest('requires ament_cmake')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def write(relative, text):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)

            def package(directory, name, version, dependencies, cmake):
                write(f'{directory}/package.xml',
                      f'<package format="3"><name>{name}</name><version>{version}</version>'
                      '<description>Packaging fixture</description>'
                      '<maintainer email="test@example.com">Test</maintainer><license>MIT</license>'
                      '<buildtool_depend>ament_cmake</buildtool_depend>' + dependencies +
                      '<export><build_type>ament_cmake</build_type></export></package>')
                write(f'{directory}/LICENSE', f'{name} license\n')
                write(f'{directory}/CMakeLists.txt',
                      f'cmake_minimum_required(VERSION 3.16)\nproject({name} C)\n'
                      'find_package(ament_cmake REQUIRED)\n' + cmake + '\nament_package()\n')
                write(f'{directory}/test/installed/test_fixture.py', 'def test_fixture(): pass\n')

            # This build-only package has no rosdep key and must not be resolved
            # as an external dependency or influence the release version.
            package('third_party/vendor_codegen', 'vendor_codegen', '99.0.0', '',
                    'ament_package_xml()\n'
                    'file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/answer.h "#define ANSWER 42\\n")\n'
                    'install(FILES ${CMAKE_CURRENT_BINARY_DIR}/answer.h DESTINATION include)\n'
                    'ament_export_include_directories(include)')
            package('third_party/vendor_helper', 'vendor_helper', '98.0.0', '',
                    'add_library(vendor_unversioned SHARED vendor.c)\n'
                    'add_library(vendor_versioned SHARED vendor.c)\n'
                    'set_target_properties(vendor_versioned PROPERTIES SOVERSION 1)\n'
                    'install(TARGETS vendor_unversioned vendor_versioned EXPORT vendor_targets\n'
                    '        LIBRARY DESTINATION lib)\n'
                    'ament_export_targets(vendor_targets HAS_LIBRARY_TARGET)')
            write('third_party/vendor_helper/vendor.c', 'int vendor_answer(void) { return 42; }\n')
            write('third_party/vendor_helper/requirements.txt', 'vendor-runtime-only>=99\n')
            package('src/nested/shipped_app', 'shipped_app', '1.2.3',
                    '<build_depend>vendor_codegen</build_depend>'
                    '<depend version_gte="1.0">vendor_helper</depend>',
                    'find_package(vendor_codegen REQUIRED)\n'
                    'find_package(vendor_helper REQUIRED)\n'
                    'foreach(kind unversioned versioned)\n'
                    '  add_executable(app_${kind} main.c)\n'
                    '  target_include_directories(app_${kind} PRIVATE ${vendor_codegen_INCLUDE_DIRS})\n'
                    '  target_link_libraries(app_${kind} vendor_helper::vendor_${kind})\n'
                    '  install(TARGETS app_${kind} DESTINATION lib/shipped_app)\n'
                    'endforeach()')
            write('src/nested/shipped_app/main.c',
                  '#include <answer.h>\nint vendor_answer(void);\n'
                  'int main(void) { return vendor_answer() == ANSWER ? 0 : 1; }\n')
            write('packaging.toml', '[package]\nname = "boundary-fixture"\n'
                  'maintainer = "Test <test@example.com>"\ndescription = "Boundary fixture"\n')
            work = root / 'release'
            work.mkdir()
            args = SimpleNamespace(workspace=root, maintainer=None, version='1.2.3-1',
                                   jobs=2, output=root / 'dist', keep_build=True)

            def resolve(resolver, key):
                self.assertIn(key, ('ament_cmake', 'vendor_helper'))
                return 'apt', [target.package_name(key.replace('_', '-'))]

            with patch.object(packaging.Resolver, 'resolve', resolve), \
                    patch.object(packaging.tempfile, 'mkdtemp', return_value=str(work)):
                packaging.build(args)

            self.assertEqual(development_version(root, {}), '1.2.3~ci0+local-1')
            deb, = (root / 'dist').glob('*.deb')
            extracted = root / 'extracted'
            subprocess.run(['dpkg-deb', '-x', str(deb), str(extracted)], check=True)
            prefix = extracted / target.prefix.relative_to('/')
            self.assertEqual({path.name for path in
                              (prefix / 'share/ament_index/resource_index/packages').iterdir()},
                             {'shipped_app'})
            self.assertFalse(any('vendor' in path.name for path in extracted.rglob('*')))
            resources = prefix / 'share' / target.package_name('boundary-fixture')
            self.assertEqual((resources / 'workspace-packages').read_text(), 'shipped_app 1.2.3\n')
            self.assertTrue((resources / 'tests/shipped_app/test_fixture.py').is_file())
            self.assertFalse((resources / 'python').exists())
            control = subprocess.check_output(['dpkg-deb', '-f', str(deb)], text=True)
            self.assertIn(target.package_name('vendor-helper') + ' (>= 1.0)', control)
            self.assertNotIn('vendor-codegen', control)
            self.assertIn('Conflicts: ' + target.package_name('shipped-app'), control)
            copyright_text = (extracted / 'usr/share/doc' /
                              target.package_name('boundary-fixture') / 'copyright').read_text()
            self.assertNotIn('vendor', copyright_text)
            # Simulate separately provided vendor runtime libraries. The deb's
            # executables must link to them without retaining build-tree RPATHs.
            env = dict(os.environ, LD_LIBRARY_PATH=str(work / 'install/vendor_helper/lib'))
            for kind in ('unversioned', 'versioned'):
                subprocess.run([str(prefix / f'lib/shipped_app/app_{kind}')], env=env, check=True)


if __name__ == '__main__':
    unittest.main()
