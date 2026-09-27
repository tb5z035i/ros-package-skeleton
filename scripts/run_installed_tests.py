#!/usr/bin/python3
"""Run each ROS package's test/installed tests without sharing import namespaces."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def run_tests(directories, reports=None):
    failed = False
    for name, directory in directories:
        if not directory.is_dir():
            continue
        with tempfile.TemporaryDirectory(prefix='ros-installed-test-') as temporary:
            command = ['/usr/bin/python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', str(directory)]
            if reports:
                command += ['--junitxml', str(reports / f'{name}.xml')]
            result = subprocess.run(command, cwd=temporary, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
            failed |= result.returncode != 0
    return int(failed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source', type=Path)
    group.add_argument('--installed', type=Path)
    parser.add_argument('--reports', type=Path)
    args = parser.parse_args()
    if args.reports:
        args.reports = args.reports.resolve()
        args.reports.mkdir(parents=True, exist_ok=True)
    if args.source:
        # Match colcon discovery, including nested packages and COLCON_IGNORE.
        output = subprocess.check_output(['colcon', 'list', '--base-paths', str(args.source.resolve()),
                                          '--paths-only'], text=True)
        directories = [(Path(path).name, Path(path) / 'test/installed') for path in output.splitlines()]
    else:
        directories = [(path.name, path) for path in sorted(args.installed.resolve().glob('*'))]
    raise SystemExit(run_tests(directories, args.reports))
