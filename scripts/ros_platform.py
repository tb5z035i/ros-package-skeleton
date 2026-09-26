"""Supported ROS/Ubuntu targets, shared by the shell scripts and packager."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys


UBUNTU_BY_ROS = {'jazzy': 'noble', 'humble': 'jammy'}
ARCHITECTURES = ('amd64', 'arm64')


@dataclass(frozen=True)
class Target:
    distro: str
    codename: str
    architecture: str

    @property
    def prefix(self) -> Path:
        return Path('/opt/ros') / self.distro

    def package_name(self, workspace_name: str) -> str:
        return f'ros-{self.distro}-{workspace_name}'


def detect_target() -> Target:
    release = platform.freedesktop_os_release()
    codename = release.get('VERSION_CODENAME', '')
    distro = os.environ.get('ROS_DISTRO') or next(
        (name for name, ubuntu in UBUNTU_BY_ROS.items() if ubuntu == codename), '')
    if (release.get('ID') != 'ubuntu' or distro not in UBUNTU_BY_ROS
            or UBUNTU_BY_ROS[distro] != codename):
        raise ValueError('Use Ubuntu 24.04 (Noble)/Jazzy or Ubuntu 22.04 (Jammy)/Humble; '
                         'ROS_DISTRO must match the Ubuntu release')
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    if architecture not in ARCHITECTURES:
        raise ValueError(f'Unsupported architecture: {architecture}; use amd64 or arm64')
    expected = os.environ.get('TARGET_ARCH')
    if expected and expected != architecture:
        raise ValueError(f'TARGET_ARCH={expected} does not match container architecture {architecture}')
    return Target(distro, codename, architecture)


if __name__ == '__main__':
    try:
        target = detect_target()
        for key, value in {'ROS_DISTRO': target.distro, 'ROS_PREFIX': str(target.prefix),
                           'UBUNTU_CODENAME': target.codename,
                           'DEB_ARCH': target.architecture}.items():
            print(f'export {key}={shlex.quote(value)}')
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'ROS platform: {error}', file=sys.stderr)
        sys.exit(1)
