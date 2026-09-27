"""Derive a development Debian version from the workspace's ROS manifests."""

import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET


def development_version(root, env):
    paths = subprocess.check_output(
        ['colcon', 'list', '--base-paths', str(root / 'src'), '--paths-only'], text=True).splitlines()
    versions = []
    for path in paths:
        version = ET.parse(Path(path) / 'package.xml').getroot().findtext('version', '').strip()
        parts = version.split('.')
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError(f'{path}: expected a ROS major.minor.patch version')
        versions.append(tuple(map(int, parts)))
    if not versions:
        raise ValueError('No ROS packages under src/')
    base = '.'.join(map(str, max(versions)))
    return f'{base}~ci{env.get("CI_PIPELINE_IID", "0")}+{env.get("CI_COMMIT_SHORT_SHA", "local")}-1'


if __name__ == '__main__':
    print(development_version(Path(__file__).resolve().parents[1], os.environ))
