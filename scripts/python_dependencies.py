"""Collect declarative pip requirements and native vendor wheels from ROS packages."""

from pathlib import Path
import zipfile

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename


def read_requirements(text, source):
    """Accept portable named requirements; reject pip options and source paths."""
    result = []
    for line in text.splitlines():
        line = line.split(' #', 1)[0].strip()
        if not line or line.startswith('#'):
            continue
        try:
            requirement = Requirement(line)
        except ValueError as error:
            raise ValueError(f'{source}: expected a named PEP 508 requirement: {line}') from error
        if requirement.url:
            raise ValueError(f'{source}: put vendor wheels in wheels/; URLs are unsupported')
        result.append(str(requirement))
    return result


def collect_python_dependencies(packages, requirements=()):
    """Only compatible wheels are selected, with one version per distribution."""
    result = {'requirements': sorted(set(requirements)), 'constraints': [], 'wheels': []}
    tags = {tag: index for index, tag in enumerate(sys_tags())}
    distributions = {}
    for package in packages:
        source = Path(package.filename).parent
        for filename, key in [('requirements.txt', 'requirements'),
                              ('pip-constraints.txt', 'constraints')]:
            path = source / filename
            if path.is_file():
                result[key].extend(read_requirements(path.read_text(), path))
        candidates = {}
        for path in sorted((source / 'wheels').glob('*.whl')):
            name, version, _, wheel_tags = parse_wheel_filename(path.name)
            matches = wheel_tags & tags.keys()
            candidates.setdefault(name, [])
            if matches:
                if not zipfile.is_zipfile(path):
                    raise ValueError(f'Invalid wheel (possibly an LFS pointer): {path}')
                candidates[name].append((version, min(tags[tag] for tag in matches), path))
        for name, wheels in candidates.items():
            if not wheels:
                raise ValueError(f'{source}/wheels: no compatible wheel for {name}')
            if len({version for version, _, _ in wheels}) != 1:
                raise ValueError(f'{source}/wheels: keep one version of {name}')
            _, _, path = min(wheels, key=lambda item: (item[1], item[2].name))
            if canonicalize_name(name) in distributions:
                raise ValueError(f'Declare vendor wheel {name} in one ROS package only')
            distributions[canonicalize_name(name)] = path
            result['wheels'].append({'package': package.name, 'path': str(path)})
    for key in ('requirements', 'constraints'):
        result[key] = sorted(set(result[key]))
    return result
