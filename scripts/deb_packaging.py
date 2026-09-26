"""Staged Debian packaging for Jazzy/Noble and Humble/Jammy ROS 2 workspaces."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
try:
    import tomllib
except ModuleNotFoundError:  # Ubuntu 22.04 ships Python 3.10.
    import tomli as tomllib

from ros_platform import detect_target


PACKAGE_NAME = re.compile(r'[a-z0-9][a-z0-9+.-]+\Z')
ROOT_GENERATED = re.compile(
    r'(?:setup\..+|local_setup\..+|_local_setup_util.*\.py|'
    r'COLCON_IGNORE|\.colcon_install_layout)\Z')
RUNTIME_TYPES = ('exec', 'build_export', 'buildtool_export')
BUILD_TYPES = ('build', 'buildtool', *RUNTIME_TYPES)


class PackagingError(RuntimeError):
    pass


def run(args, *, env=None, cwd=None, capture=False):
    print('+ ' + shlex.join(map(str, args)), flush=True)
    return subprocess.run(
        list(map(str, args)), env=env, cwd=cwd, check=True,
        stdout=subprocess.PIPE if capture else None, text=True).stdout


def clean_environment(work, target):
    # Do not inherit overlays, virtualenvs, compiler flags, or colcon defaults.
    env = {key: value for key, value in os.environ.items() if key in {
        'HOME', 'USER', 'LOGNAME', 'TERM', 'http_proxy', 'https_proxy',
        'no_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY',
        'ROSDISTRO_INDEX_URL', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
    }}
    env.update(PATH='/usr/bin:/bin', LANG='C.UTF-8', LC_ALL='C.UTF-8', PYTHONNOUSERSITE='1')
    result = subprocess.run(
        ['/bin/bash', '--noprofile', '--norc', '-c',
         'set -e; source "$1" >&2; env -0', 'release', str(target.prefix / 'setup.bash')],
        env=env, check=True, stdout=subprocess.PIPE)
    env = dict(entry.split('=', 1) for entry in result.stdout.decode().split('\0') if entry)
    env['COLCON_HOME'] = str(work / 'colcon-home')
    defaults = work / 'defaults.yaml'
    defaults.write_text('{}\n')
    env['COLCON_DEFAULTS_FILE'] = str(defaults)
    return env


def load_config(path, maintainer=None):
    with path.open('rb') as stream:
        config = tomllib.load(stream)
    package = config.get('package', {})
    if maintainer:
        package['maintainer'] = maintainer
    for field in ('name', 'maintainer', 'description'):
        value = package.get(field, '')
        if not isinstance(value, str) or not value.strip() or '\n' in value or '\r' in value:
            raise PackagingError(f'Configure a single-line package.{field} in {path}')
    if not PACKAGE_NAME.fullmatch(package['name']):
        raise PackagingError('Invalid Debian package name')
    if not re.fullmatch(r'[^<>]+ <[^<>\s@]+@[^<>\s@]+>', package['maintainer']):
        raise PackagingError('Maintainer must be "Name <email@example.com>"')
    licenses = package.get('license_files', [])
    if not isinstance(licenses, list) or not licenses or not all(isinstance(p, str) for p in licenses):
        raise PackagingError('package.license_files must list the bundled source licenses')
    for kind in ('build', 'runtime'):
        dependencies = config.get('dependencies', {}).get(kind, [])
        if not isinstance(dependencies, list) or not all(
                isinstance(dep, str) and PACKAGE_NAME.fullmatch(dep) for dep in dependencies):
            raise PackagingError(f'dependencies.{kind} must contain Debian package names')
    return config


def discover(root, work, env):
    from catkin_pkg.package import parse_package

    paths = run(['colcon', '--log-base', work / 'log', 'list', '--base-paths',
                 root / 'src', '--topological-order', '--paths-only'],
                env=env, cwd=work, capture=True).splitlines()
    if not paths:
        raise PackagingError('No packages discovered under src/')
    packages = []
    context = {'ROS_VERSION': '2', 'ROS_DISTRO': env['ROS_DISTRO'], 'ROS_PYTHON_VERSION': '3'}
    for path in paths:
        manifest = Path(path) / 'package.xml'
        if not manifest.is_file():
            raise PackagingError(f'Only ROS packages are supported: {path}')
        package = parse_package(str(manifest))
        package.evaluate_conditions(context)
        if package.get_build_type() not in ('ament_cmake', 'ament_python'):
            raise PackagingError(f'Unsupported build type for {package.name}: {package.get_build_type()}')
        if any(dep.evaluated_condition is not False for dep in package.group_depends):
            raise PackagingError(f'{package.name}: group_depend is unsupported; declare explicit dependencies')
        packages.append(package)
    print('Bundling: ' + ', '.join(package.name for package in packages), flush=True)
    return packages


class Resolver:
    def __init__(self, env, target):
        self.env = env
        self.target = target
        self.cache = {}

    def resolve(self, key):
        if key not in self.cache:
            output = run(['rosdep', 'resolve', '--rosdistro', self.target.distro,
                          '--os=ubuntu:' + self.target.codename, key],
                         env=self.env, capture=True)
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if not lines or lines[0] != '#apt':
                raise PackagingError(f'{key}: requires a non-APT installer; add an APT rosdep rule')
            names = ' '.join(lines[1:]).split()
            if not names or not all(PACKAGE_NAME.fullmatch(name) for name in names):
                raise PackagingError(f'{key}: no valid Debian dependency resolution: {output}')
            self.cache[key] = names
        return self.cache[key]

    def dependencies(self, packages, kinds):
        bundled = {package.name for package in packages}
        result = set()
        operators = {'lt': '<<', 'lte': '<=', 'eq': '=', 'gte': '>=', 'gt': '>>'}
        for package in packages:
            for kind in kinds:
                for dependency in getattr(package, kind + '_depends'):
                    if dependency.evaluated_condition is False or dependency.name in bundled:
                        continue
                    for name in self.resolve(dependency.name):
                        constraints = []
                        for attr, operator in operators.items():
                            version = getattr(dependency, 'version_' + attr)
                            if version:
                                if not re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]*', version):
                                    raise PackagingError(f'Invalid dependency version: {version}')
                                constraints.append(f'{name} ({operator} {version})')
                        result.update(constraints or [name])
        return result


def check_dependencies(dependencies, work, env):
    control = work / 'build-dependencies.control'
    control.write_text('Source: workspace-release\nBuild-Depends: ' +
                       ', '.join(sorted(dependencies)) + '\n\n'
                       'Package: workspace-release\nArchitecture: any\nDescription: build check\n')
    try:
        run(['dpkg-checkbuilddeps', control], env=env)
    except subprocess.CalledProcessError as error:
        raise PackagingError(
            'Missing release dependencies. Run rosdep install as documented and install '
            'dependencies.build/runtime from packaging.toml with APT.') from error


def known_metadata(relative):
    return (relative.suffix in {'.sh', '.bash', '.zsh', '.ps1', '.bat', '.dsv', '.cmake', '.pc', '.pth'} or
            relative.parts[:3] == ('share', 'ament_index', 'resource_index'))


def stage_install(install, destination, forbidden, prefix):
    destination.mkdir(parents=True)
    for child in install.iterdir():
        if ROOT_GENERATED.fullmatch(child.name):
            continue
        target = destination / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, target, symlinks=True)
        elif child.is_symlink():
            target.symlink_to(os.readlink(child))
        else:
            shutil.copy2(child, target)

    original = str(install).encode()
    needles = [str(path).encode() for path in forbidden]
    # Normalize the whole link graph before resolving any member of a chain.
    for path in sorted(destination.rglob('*')):
        if not path.is_symlink():
            continue
        link = os.readlink(path)
        for link_prefix in (install, prefix):
            try:
                inside = Path(link).relative_to(link_prefix)
            except ValueError:
                continue
            path.unlink()
            path.symlink_to(os.path.relpath(destination / inside, path.parent))
            break
    for path in sorted(destination.rglob('*')):
        relative = path.relative_to(destination)
        if path.is_symlink():
            link = os.readlink(path)
            resolved = path.resolve()
            if not resolved.is_relative_to(destination):
                raise PackagingError(f'External/source-bound symlink: {relative} -> {link}')
            if not path.exists():
                raise PackagingError(f'Broken installed symlink: {relative}')
            continue
        if not path.is_file():
            continue
        if path.suffix == '.pyc':
            # Compile-time filenames in bytecode point back to the build tree.
            path.unlink()
            continue
        if path.name == 'SOURCES.txt' and path.parent.name.endswith('.egg-info'):
            # setuptools records build-tree egg_info paths here. This is an sdist
            # input manifest, not runtime distribution/entry-point metadata.
            path.unlink()
            continue
        data = path.read_bytes()
        if b'\0' not in data and known_metadata(relative):
            data = data.replace(original, str(prefix).encode())
            path.write_bytes(data)
        if b'\0' not in data and any(needle in data for needle in needles):
            raise PackagingError(f'Unrelocated source/build reference in {relative}; fix its install rules')
        if data.startswith(b'\x7fELF'):
            dynamic = run(['readelf', '-d', path], capture=True)
            for line in dynamic.splitlines():
                if any(tag in line for tag in ('RPATH', 'RUNPATH', 'NEEDED')):
                    if any(needle.decode() in line for needle in needles):
                        raise PackagingError(f'Build path in ELF dynamic metadata: {relative}: {line.strip()}')
            headers = run(['readelf', '-l', path], capture=True)
            if any(needle.decode() in line for line in headers.splitlines()
                   if 'Requesting program interpreter' in line for needle in needles):
                raise PackagingError(f'Build path in ELF interpreter: {relative}')


def verify_payload(destination, packages, prefix):
    for path in destination.iterdir():
        if ROOT_GENERATED.fullmatch(path.name):
            raise PackagingError(f'Workspace setup file included in payload: {path.name}')
    for package in packages:
        for relative in (f'share/ament_index/resource_index/packages/{package.name}',
                         f'share/{package.name}/package.xml',
                         f'share/{package.name}/package.dsv'):
            if not (destination / relative).is_file():
                raise PackagingError(f'Missing ROS installation file: {relative}')
    # Sharing directories is expected; sharing files with installed packages is not.
    for path in destination.rglob('*'):
        if path.is_dir() and not path.is_symlink():
            continue
        installed = prefix / path.relative_to(destination)
        if installed.exists() or installed.is_symlink():
            raise PackagingError(f'Payload collides with an installed file: {installed}')


def elf_dependencies(stage, package_name, work, env, prefix):
    destination = stage / prefix.relative_to('/')
    binaries = []
    shlibs = set()
    bundled_sonames = set()
    unversioned_needed = {}
    library_dirs = {str(prefix / 'lib')}
    for path in sorted(destination.rglob('*')):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                continue
        dynamic = run(['readelf', '-d', path], capture=True)
        if '(NEEDED)' not in dynamic and '(SONAME)' not in dynamic:
            continue
        binaries.append(path)
        unversioned_needed[path] = set(re.findall(r'\(NEEDED\).*\[([^\]]+\.so)\]', dynamic))
        library_dirs.add(str(path.parent))
        match = re.search(r'\(SONAME\).*\[([^\]]+)\]', dynamic)
        if match:
            soname = match.group(1)
            bundled_sonames.add(soname)
            if '.so.' in soname:
                name, version = soname.split('.so.', 1)
            else:
                # Unversioned ROS libraries are private to the bundle. dpkg recognizes
                # their common package root via the DEBIAN directory below.
                continue
            shlibs.add(f'{name} {version} {package_name}')
    if not binaries:
        return set()
    # These local mappings identify bundled libraries, allowing -x to remove self-dependencies.
    local_shlibs = work / 'shlibs.local'
    local_shlibs.write_text('\n'.join(sorted(shlibs)) + '\n')
    (stage / 'DEBIAN').mkdir(exist_ok=True)
    output = run(['dpkg-shlibdeps', '-O', '-x' + package_name,
                  *(['-L' + str(local_shlibs)] if shlibs else []), '-S' + str(stage),
                  *['-l' + directory for directory in sorted(library_dirs)],
                  *['-e' + str(binary) for binary in binaries]],
                 env=env, cwd=work, capture=True)
    dependencies = set()
    for line in output.splitlines():
        if line.startswith('shlibs:Depends='):
            dependencies.update(entry.strip() for entry in line.split('=', 1)[1].split(',') if entry.strip())
    # Many ROS libraries have unversioned SONAMEs and no Debian shlibs/symbols
    # metadata. dpkg-shlibdeps deliberately skips those. Resolve their APT
    # owners as well, so missing upstream manifest entries cannot silently
    # produce a bundle that only runs in its build environment.
    resolved_sonames = set(bundled_sonames)
    loader_env = dict(env)
    loader_env['LD_LIBRARY_PATH'] = ':'.join(sorted(library_dirs)) + ':' + env.get('LD_LIBRARY_PATH', '')
    for binary, needed in unversioned_needed.items():
        missing = needed - resolved_sonames
        if not missing:
            continue
        linkage = run(['ldd', binary], env=loader_env, capture=True)
        libraries = dict(re.findall(r'^\s*(\S+) => (/\S+) \(', linkage, re.MULTILINE))
        for soname in sorted(missing):
            if soname not in libraries:
                raise PackagingError(f'Cannot resolve external library {soname} needed by {binary.name}')
            library = libraries[soname]
            ownership = run(['dpkg-query', '-S', library], env=env, capture=True).strip().splitlines()
            if len(ownership) != 1 or ': ' not in ownership[0]:
                raise PackagingError(f'Cannot determine a unique APT owner for {library}')
            owner = ownership[0].split(': ', 1)[0]
            version = run(['dpkg-query', '-W', '-f=${Version}', owner], env=env, capture=True).strip()
            dependencies.add(f'{owner} (>= {version})')
            resolved_sonames.add(soname)
    return dependencies


def write_metadata(stage, config, packages, dependencies, version, target, root):
    package = config['package']
    name = target.package_name(package['name'])
    control_dir = stage / 'DEBIAN'
    control_dir.mkdir(exist_ok=True)
    doc = stage / 'usr/share/doc' / name
    doc.mkdir(parents=True)
    notices = []
    for filename in package['license_files']:
        path = (root / filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise PackagingError(f'License file must exist inside the workspace: {filename}')
        notices.append(f'License notice from {filename}:\n\n{path.read_text()}')
    (doc / 'copyright').write_text('\n\n'.join(notices))
    (doc / 'workspace-packages').write_text(''.join(
        f'{p.name} {p.version}\n' for p in packages))
    conflicts = sorted({target.package_name(p.name.replace('_', '-')) for p in packages} - {name})
    size = sum(path.lstat().st_size for path in stage.rglob('*') if not path.is_dir())
    fields = [f'Package: {name}', f'Version: {version}', f'Architecture: {target.architecture}',
              f'Maintainer: {package["maintainer"]}', 'Section: misc', 'Priority: optional',
              f'Installed-Size: {(size + 1023) // 1024}',
              'Depends: ' + ', '.join(sorted(dependencies))]
    if conflicts:
        fields.append('Conflicts: ' + ', '.join(conflicts))
    fields.append('Description: ' + package['description'])
    (control_dir / 'control').write_text('\n'.join(fields) + '\n')
    checksums = []
    for path in sorted(stage.rglob('*')):
        if path.is_symlink() or not path.is_file() or path.is_relative_to(control_dir):
            continue
        checksums.append(hashlib.md5(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(stage)))
    (control_dir / 'md5sums').write_text('\n'.join(checksums) + '\n')
    for path in stage.rglob('*'):
        if path.is_symlink():
            continue
        path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)


def build(args):
    root = args.workspace.resolve()
    config = load_config(root / 'packaging.toml', args.maintainer)
    target = detect_target()
    package_name = target.package_name(config['package']['name'])
    if not (target.prefix / 'setup.bash').is_file():
        raise PackagingError(f'Install ROS 2 {target.distro} before building')
    if not re.fullmatch(r'[0-9][A-Za-z0-9.+:~\-]*', args.version):
        raise PackagingError('Invalid Debian version')
    run(['dpkg', '--validate-version', args.version])
    for command in ('colcon', 'rosdep', 'dpkg-checkbuilddeps', 'dpkg-shlibdeps', 'dpkg-deb', 'readelf'):
        if not shutil.which(command, path='/usr/bin:/bin'):
            raise PackagingError(f'Missing {command}; rebuild the dev container or install packaging prerequisites')
    if args.jobs < 1:
        raise PackagingError('--jobs must be positive')
    work = Path(tempfile.mkdtemp(prefix='ros-workspace-deb-'))
    success = False
    print(f'Release work directory: {work}', flush=True)
    try:
        env = clean_environment(work, target)
        env['CMAKE_BUILD_PARALLEL_LEVEL'] = str(args.jobs)
        env['MAKEFLAGS'] = f'-j{args.jobs} -l{args.jobs}'
        packages = discover(root, work, env)
        resolver = Resolver(env, target)
        extra = config.get('dependencies', {})
        runtime = resolver.dependencies(packages, RUNTIME_TYPES)
        runtime.update(extra.get('runtime', []))
        runtime.add(target.package_name('ros-core'))
        build_dependencies = resolver.dependencies(packages, BUILD_TYPES) | runtime
        build_dependencies.update(extra.get('build', []))
        check_dependencies(build_dependencies, work, env)
        install = work / 'install'
        run(['colcon', '--log-base', work / 'log', 'build', '--base-paths', root / 'src',
             '--build-base', work / 'build', '--install-base', install, '--merge-install',
             '--executor', 'sequential', '--event-handlers', 'console_direct+',
             '--cmake-args', '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=OFF',
             '-DAMENT_CMAKE_SYMLINK_INSTALL=OFF'], env=env, cwd=work)
        # dpkg-shlibdeps requires a source control file even for a binary-only bundle.
        (work / 'debian').mkdir()
        (work / 'debian/control').write_text(
            f'Source: {package_name}\n\n'
            f'Package: {package_name}\nArchitecture: any\nDescription: workspace\n')
        stage = work / 'payload'
        destination = stage / target.prefix.relative_to('/')
        stage_install(install, destination, [work, root], target.prefix)
        verify_payload(destination, packages, target.prefix)
        runtime.update(elf_dependencies(stage, package_name, work, env, target.prefix))
        write_metadata(stage, config, packages, runtime, args.version, target, root)
        name = f'{package_name}_{args.version.split(":")[-1]}_{target.architecture}.deb'
        temporary_deb = work / name
        run(['dpkg-deb', '--build', '--root-owner-group', stage, temporary_deb], env=env)
        output = (args.output or root / 'dist').resolve()
        output.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_deb, output / name)
        print(f'Built: {output / name}', flush=True)
        success = True
    finally:
        if success and not args.keep_build:
            shutil.rmtree(work)
        else:
            print(f'Release files retained at {work}', file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, help='Debian release version, e.g. 0.1.0-1')
    parser.add_argument('--maintainer', help='Override package.maintainer: Name <email>')
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, help='Artifact directory (default: workspace/dist)')
    parser.add_argument('--jobs', type=int, default=2, help='Concurrent compilation jobs (default: 2)')
    parser.add_argument('--keep-build', action='store_true', help='Retain successful temporary build files')
    try:
        build(parser.parse_args())
    except (PackagingError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f'Packaging failed: {error}', file=sys.stderr)
        sys.exit(1)
