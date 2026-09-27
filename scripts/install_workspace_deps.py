#!/usr/bin/python3
"""Install package.xml APT dependencies and package-local pip inputs consistently."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

from deb_packaging import BUILD_TYPES, Resolver, discover, load_config
from python_dependencies import collect_python_dependencies
from ros_platform import detect_target


def main():
    root = Path(__file__).resolve().parents[1]
    target = detect_target()
    env = dict(os.environ, ROS_DISTRO=target.distro)
    as_root = [] if os.geteuid() == 0 else ['sudo']
    with tempfile.TemporaryDirectory(prefix='ros-dependencies-') as temporary:
        work = Path(temporary)
        packages = discover(root, work, env)
        resolver = Resolver(env, target)
        pip = resolver.dependencies(packages, (*BUILD_TYPES, 'test'), 'pip')
        dependencies = collect_python_dependencies(packages, pip)
        skip = [key for key, (installer, _) in resolver.cache.items() if installer == 'pip']
        command = ['rosdep', 'install', '--from-paths', str(root / 'src'), '--ignore-src',
                   '--rosdistro', target.distro, '-y']
        if skip:
            command += ['--skip-keys', ' '.join(skip)]
        subprocess.run(command, check=True, env=env)
        extra = load_config(root / 'packaging.toml').get('dependencies', {})
        apt = sorted(set(extra.get('build', []) + extra.get('runtime', [])))
        if apt:
            subprocess.run([*as_root, 'apt-get', 'install', '-y', '--no-install-recommends', *apt], check=True)
        manifest = work / 'python-dependencies.json'
        manifest.write_text(json.dumps(dependencies))
        subprocess.run([*as_root, '/usr/bin/python3',
                        str(root / 'scripts/install_python_dependencies.py'), str(manifest)], check=True)


if __name__ == '__main__':
    main()
