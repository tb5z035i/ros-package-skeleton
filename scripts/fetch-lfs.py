#!/usr/bin/python3
"""Fetch root/submodule LFS objects, optionally selecting paths per repository."""

from pathlib import Path
import subprocess
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def fetch(root):
    config_file = root / 'packaging/lfs.toml'
    config = {}
    if config_file.is_file():
        with config_file.open('rb') as stream:
            config = tomllib.load(stream).get('repositories', {})
    output = subprocess.check_output(
        ['git', 'submodule', 'foreach', '--quiet', '--recursive', 'printf "%s\\0" "$displaypath"'],
        cwd=root)
    repositories = ['.', *[path.decode() for path in output.split(b'\0') if path]]
    unknown = set(config) - set(repositories)
    if unknown:
        raise ValueError(f'Unknown LFS repositories in {config_file}: {sorted(unknown)}')
    for path in repositories:
        options = config.get(path, {})
        if set(options) - {'include', 'exclude'}:
            raise ValueError(f'{path}: LFS options must be include/exclude lists')
        command = ['git', '-C', str(root / path), 'lfs', 'pull']
        for option in ('include', 'exclude'):
            if option not in options:
                continue
            patterns = options[option]
            if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
                raise ValueError(f'{path}: LFS {option} must be a list of patterns')
            command.append(f'--{option}=' + ','.join(patterns))
        subprocess.run(command, check=True)


if __name__ == '__main__':
    fetch(Path(__file__).resolve().parents[1])
