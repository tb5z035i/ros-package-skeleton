#!/usr/bin/python3
"""Install a bundle's declared Python dependencies through pip, never into its deb."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

TUNA_INDEX = 'https://pypi.tuna.tsinghua.edu.cn/simple'


def install(dependencies, base):
    wheels = [str((base / wheel['path']).resolve()) for wheel in dependencies['wheels']]
    requirements = dependencies['requirements']
    if not requirements and not wheels:
        return
    # Use the distro's /usr/local scheme, visible to system ROS Python. Keep pip
    # files outside dpkg ownership. This env option also works with Jammy's pip.
    env = {key: value for key, value in os.environ.items() if not key.startswith('PIP_')
           and key not in {'PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'}}
    env.update(PIP_CONFIG_FILE='/dev/null', PIP_BREAK_SYSTEM_PACKAGES='1',
               PYTHONNOUSERSITE='1')
    command = ['/usr/bin/python3', '-m', 'pip', 'install', '--disable-pip-version-check',
               '--no-input', '--index-url', TUNA_INDEX]
    with tempfile.TemporaryDirectory(prefix='ros-pip-') as temporary:
        if dependencies['constraints']:
            constraints = Path(temporary) / 'constraints.txt'
            constraints.write_text('\n'.join(dependencies['constraints']) + '\n')
            command += ['--constraint', str(constraints)]
        subprocess.run([*command, *requirements, *wheels], env=env, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    install(json.loads(args.manifest.read_text()), args.manifest.resolve().parent)
