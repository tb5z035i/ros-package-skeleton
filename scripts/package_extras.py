"""Stage optional delivery files without application-specific packaging code."""

import json
from pathlib import Path
import re
import shlex
import shutil


def stage_extras(stage, root, config, packages, target, python_dependencies):
    name = target.package_name(config['package']['name'])
    prefix = target.prefix
    control = stage / 'DEBIAN'
    control.mkdir(parents=True, exist_ok=True)
    resources = prefix / 'share' / name
    destination = stage / resources.relative_to('/')
    dependencies = set()
    postinst = ['#!/bin/sh', 'set -e', 'if [ "$1" = configure ]; then']
    has_python = python_dependencies['requirements'] or python_dependencies['wheels']
    if has_python:
        python_dir = destination / 'python'
        if python_dir.exists():
            raise ValueError(f'Reserved packaging resource path already installed: {python_dir}')
        python_dir.mkdir(parents=True)
        manifest = dict(python_dependencies, wheels=[])
        for wheel in python_dependencies['wheels']:
            source = Path(wheel['path'])
            relative = Path('wheels') / wheel['package'] / source.name
            output = python_dir / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
            manifest['wheels'].append(dict(wheel, path=str(relative)))
        (python_dir / 'dependencies.json').write_text(json.dumps(manifest, indent=2) + '\n')
        shutil.copy2(Path(__file__).with_name('install_python_dependencies.py'),
                     python_dir / 'install.py')
        postinst.append('    /usr/bin/python3 ' + shlex.quote(str(resources / 'python/install.py'))
                        + ' ' + shlex.quote(str(resources / 'python/dependencies.json')))
        dependencies.update({'python3-pip', 'ca-certificates'})

    substitutions = {'@PREFIX@': str(prefix), '@ROS_DISTRO@': target.distro,
                     '@DEB_PACKAGE@': name}

    def render(text):
        for old, new in substitutions.items():
            text = text.replace(old, new)
        if re.search(r'@[A-Z_]+@', text):
            raise ValueError(f'Unknown packaging substitution: {text}')
        return text

    services = sorted((root / 'packaging/systemd').glob('*.service*'))
    for service in services:
        if not (service.name.endswith('.service') or service.name.endswith('.service.in')):
            raise ValueError(f'Expected .service or .service.in: {service}')
        filename = render(service.name.removesuffix('.in'))
        output = stage / 'usr/lib/systemd/system' / filename
        if output.exists():
            raise ValueError(f'Duplicate systemd unit: {filename}')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render(service.read_text()))
    if services:
        reload = ('    if [ -d /run/systemd/system ] && command -v systemctl >/dev/null 2>&1; then\n'
                  '        systemctl --system daemon-reload\n    fi')
        postinst.append(reload)
        (control / 'postrm').write_text('#!/bin/sh\nset -e\ncase "$1" in\n'
                                      'remove|purge)\n' + reload + '\n;;\nesac\n')
        (control / 'postrm').chmod(0o755)
    if has_python or services:
        (control / 'postinst').write_text('\n'.join(postinst + ['fi', '']))
        (control / 'postinst').chmod(0o755)
    # pip dependencies may be shared by other bundles. Never uninstall them in
    # prerm/postrm, and never enable/start/restart hardware services implicitly.
    conffiles = root / 'packaging/conffiles'
    if conffiles.is_file():
        paths = set()
        for line in conffiles.read_text().splitlines():
            pattern = render(line.strip())
            if not pattern or pattern.startswith('#'):
                continue
            if not pattern.startswith('/') or '..' in Path(pattern).parts:
                raise ValueError(f'Conffile pattern must be an absolute installed path: {line}')
            matches = sorted(stage.glob(pattern.lstrip('/')))
            if not matches:
                raise ValueError(f'Conffile pattern has no installed files: {line}')
            for path in matches:
                if not path.is_file() or path.is_symlink() or path.is_relative_to(control):
                    raise ValueError(f'Invalid conffile: {path}')
                paths.add('/' + str(path.relative_to(stage)))
        if paths:
            (control / 'conffiles').write_text('\n'.join(sorted(paths)) + '\n')
    # Installed tests are shipped independently of setup.py/CMake install rules.
    for package in packages:
        tests = Path(package.filename).parent / 'test/installed'
        if tests.is_dir():
            shutil.copytree(tests, destination / 'tests' / package.name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
    return dependencies
