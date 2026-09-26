"""Target selection must reject incompatible distro and CPU combinations."""

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ros_platform


class TargetTests(unittest.TestCase):
    def detect(self, codename, architecture, env=None, os_id='ubuntu'):
        with (patch.dict(os.environ, env or {}, clear=True),
              patch.object(ros_platform.platform, 'freedesktop_os_release',
                           return_value={'ID': os_id, 'VERSION_CODENAME': codename}),
              patch.object(ros_platform.subprocess, 'check_output', return_value=architecture + '\n')):
            return ros_platform.detect_target()

    def test_all_supported_targets_with_auto_detection_and_explicit_selection(self):
        for distro, codename in [('jazzy', 'noble'), ('humble', 'jammy')]:
            for architecture in ('amd64', 'arm64'):
                for env in ({}, {'ROS_DISTRO': distro, 'TARGET_ARCH': architecture}):
                    with self.subTest(distro=distro, architecture=architecture, env=env):
                        target = self.detect(codename, architecture, env)
                        self.assertEqual(target, ros_platform.Target(distro, codename, architecture))
                        self.assertEqual(target.prefix, Path('/opt/ros') / distro)
                        self.assertEqual(target.package_name('example-workspace'),
                                         f'ros-{distro}-example-workspace')

    def test_incompatible_os_and_distro_fail(self):
        for os_id, codename, distro in [('ubuntu', 'jammy', 'jazzy'),
                                       ('ubuntu', 'noble', 'humble'),
                                       ('ubuntu', 'focal', 'foxy'),
                                       ('debian', 'noble', 'jazzy')]:
            with self.subTest(os_id=os_id, codename=codename, distro=distro):
                with self.assertRaisesRegex(ValueError, 'ROS_DISTRO must match'):
                    self.detect(codename, 'amd64', {'ROS_DISTRO': distro}, os_id)

    def test_wrong_runner_architecture_fails(self):
        with self.assertRaisesRegex(ValueError, 'does not match'):
            self.detect('noble', 'amd64', {'TARGET_ARCH': 'arm64'})

    def test_unsupported_architecture_fails(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported architecture'):
            self.detect('jammy', 'armhf')


if __name__ == '__main__':
    unittest.main()
