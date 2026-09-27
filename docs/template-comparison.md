# Template comparison and adoption contract

Compared on 2026-09-27 with the local `arm-p7-ros` and
`stations/drawer/third_party/five_axis_platform` working trees. The applicants
were inspected but not modified. Pre-existing skeleton devcontainer and LFS
changes were retained.

| Area | Skeleton before this change | P7 / five-axis evidence | Template result |
| --- | --- | --- | --- |
| ROS packages | Discovers ament CMake/Python packages under `src/` | P7 has custom interfaces, upstream model preparation, launch tests; five-axis has six layered packages | Keep colcon discovery and package install rules; application architecture stays in `src/` |
| Submodules / LFS | Development source preparation exists as uncommitted work, CI never invokes it | P7 adds a hardcoded mesh subset and CI credential helper | Shared preparation runs in development and CI; recursive submodules, LFS pulls with optional `packaging/lfs.toml` subsets, HTTPS checkout and host-scoped temporary credentials |
| Python dependencies | rosdep packaging resolver rejects `#pip` | Five-axis resolves pip keys, constraints and a private vendor wheel | Separate APT and pip resolution; system pip uses TUNA in development and deb `postinst` |
| Vendor payload | No wheel convention | Five-axis expands wheels into its private Python tree | Compatible archives copied unchanged under `share/<deb-name>/python/wheels/<ros-package>/`; no expanded third-party Python files in dpkg payload |
| Smoke tests | Framework hardcodes `hello_py` and `hello_cpp` | Both applicants replace framework tests | Discover optional `src/<package>/test/installed/`; ship them in the deb and run in a clean environment; always check every bundled ROS package using a share manifest (survives minimal images that exclude docs) |
| Configuration / services | No delivery mechanism | Five-axis renders systemd units and registers station YAML as conffiles | Optional `packaging/systemd/` and `packaging/conffiles`, no automatic service activation |
| Licenses | Root config lists hello licenses explicitly | P7 adds NOTICE; vendor notices differ by application | Discover package LICENSE/COPYING and manifest license files; root config may add vendor/workspace notices |
| Runtime verification | Fresh-container install/remove and ROS underlay checks | Five-axis also checks reinstallation, conffiles and purge | Generic reinstallation/configuration preservation/purge checks; installed-test JUnit artifacts; real two-deb pip coexistence regression |
| CI policy | Four native targets, advisory tests, release on tag | Both retain this policy; five-axis additionally uses full Git history | Preserve matrix/release policy; fetch full history, pin CMake to system Python and limit DDS discovery for tests |
| Version identity | Explicit Debian version, fixed development base | Five-axis has application-specific VERSION/changelog/SCM rules | Development base follows the highest ROS manifest version; explicit tag/DEB_VERSION contract retained; release governance and changelog policy remain application choices |

## Files template users edit

1. Set the bundle identity once in `packaging.toml` (name, maintainer, description;
   optionally additional licenses or APT overrides).
2. Keep application code, manifests, CMake/setup rules, launch/config resources,
   licenses and tests under `src/`.
3. For each package, optionally add `requirements.txt`, `pip-constraints.txt`,
   `wheels/*.whl`, and `test/installed/test_*.py`. No framework edits are needed.
   Test dependencies belong in `package.xml`; installed tests must use only the
   installed runtime and pytest, not the source tree or build/test dependencies.
4. Add delivery-only services under `packaging/systemd/` and operator-edited
   configuration patterns to `packaging/conffiles` when needed.
5. Upstream repositories still require `.gitmodules`; LFS tracking/filter policy
   belongs in `.gitattributes` / `.lfsconfig` or repository-local Git settings.
   P7 can declare selective include/exclude globs for its model submodule in
   `packaging/lfs.toml` without modifying scripts. Source
   asset conversion belongs in the consuming ROS package's build rules.

`Dockerfile`, `.devcontainer`, `.gitlab-ci.yml`, `scripts/` and framework `tests/`
should remain reusable. Registry credentials, runner architecture tags and
cross-project CI job-token read access are deployment settings.

## pip delivery contract

APT rosdep results form Debian `Depends`; pip results never become Debian
package names. Python inputs from the packages are resolved together. The deb
owns only wheel archives, an installation manifest and the pip installer under
`/opt/ros/<distro>/share/<deb-name>/python/`. Configuration invokes system Python
pip with TUNA; vendor wheels are local arguments. Public and transitive
requirements may require network access. Failures propagate to dpkg so operators
can fix the cause and retry configuration.

Named PEP 508 requirements (including version constraints and markers) are
accepted. Index options, URLs, nested `-r` files and local project paths are
rejected so requirements remain portable. Use `wheels/` for vendor archives.
Only wheels compatible with the native system Python/platform are included;
missing compatible wheels, LFS pointers and multiple versions fail early.

Pip uses the Ubuntu system-Python `/usr/local` scheme, with the externally
managed environment override needed on Noble. No `--target`, `--upgrade` or
`--ignore-installed` is used. Reconfiguration lets pip reuse satisfying installed
versions. Removing or purging a deb does not uninstall pip packages, because
other applications may share them. This prevents dpkg file-ownership collisions;
it does **not** isolate incompatible Python version requirements across apps.
Such applications still need compatible constraints or separate environments.

Five-axis currently uses a private prefix, so its expanded wheels are already
isolated from packages at other prefixes. The collision concern applies when
multiple debs claim the same installation paths. This template intentionally
uses the shared ROS prefix plus pip ownership requested for new consumers; it
does not migrate existing applicant installations.

References: [pip install](https://pip.pypa.io/en/stable/cli/pip_install/),
[TUNA PyPI](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/),
[GitLab LFS](https://docs.gitlab.com/topics/git/lfs/),
[GitLab submodule authentication](https://docs.gitlab.com/ci/runners/git_submodules/).

## Validation on 2026-09-27

- Jazzy/Noble amd64: 51 framework tests run, 50 passed; the opt-in dpkg lifecycle
  test was skipped in the ordinary suite and then passed separately. This
  includes real recursive LFS repositories, missing-object failure and selective
  mesh fetching, dependency parsing, staging and release API fixtures.
- Jazzy/Noble amd64: clean `ci-build` completed; all three colcon Python tests and
  both explicit ROS publisher checks passed; Release deb generated successfully.
- Fresh Jazzy ROS-core container: installed that deb, checked every bundled ROS
  package and both publishers, reinstalled, removed and purged it, and verified
  ROS underlay checksums. Installed-test JUnit output was generated successfully.
- Humble/Jammy amd64: the same 51 framework tests ran with Python 3.10 (50 passed,
  one opt-in skip); the real dpkg/pip lifecycle test then passed separately.
- The lifecycle test installs two separate debs with the same local vendor wheel
  and TUNA requirement, confirms no dpkg-owned site/dist-packages files, preserves
  edited conffiles on reinstallation/removal, purges conffiles, and confirms pip
  imports remain usable after either/both debs are removed.
- Modified shell entry points passed ShellCheck; Python compilation, CI YAML
  parsing and `git diff --check` passed.

Full Humble ROS build/install, native ARM64, live GitLab authentication/pipelines,
release publishing and service behavior on a booted systemd host were not run.
Systemd rendering/lifecycle commands are covered by unit tests; no services were
started. Existing applicant worktrees were not changed.
