"""Exercise source preparation with real Git/LFS repositories, without a server."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HAS_LFS = shutil.which('git-lfs') is not None
P7 = (ROOT / 'scripts/prepare-ci-sources').is_file()
MODEL = 'products/hy6310_p7/assets/hy6310_p7_arm'


@unittest.skipUnless(HAS_LFS, 'requires git-lfs from install-build-tools')
class SourcePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null',
                        GIT_CONFIG_NOSYSTEM='1', GIT_ALLOW_PROTOCOL='file',
                        GIT_TERMINAL_PROMPT='0')
        for name in ('GIT_CONFIG_COUNT', 'GIT_LFS_SKIP_SMUDGE', 'CI_JOB_TOKEN'):
            self.env.pop(name, None)
        self.meshes = {
            f'{MODEL}/meshes/v4_wx_10/base_link.STL': b'arm mesh\n',
            f'{MODEL}/meshes_collision/v4_wx_10/base_link.STL': b'collision mesh\n',
            f'{MODEL}/gripper/v3/meshes/base_link.STL': b'gripper mesh\n',
        }
        self.child = self.repository('models', self.meshes | {'unrelated.STL': b'other model\n'})
        if not P7:
            nested = self.repository('nested', {'nested.STL': b'nested mesh\n'})
            self.git(self.child, 'submodule', 'add', str(nested), 'nested')
            self.git(self.child, 'commit', '-am', 'Add nested model')
        parent = self.repository('parent', {'root.STL': b'workspace asset\n'})
        self.git(parent, 'submodule', 'add', str(self.child), 'third_party/robot_descriptions')
        self.git(parent, 'commit', '-am', 'Add models')
        self.checkout = self.root / 'checkout'
        self.run_command(['git', 'clone', str(parent), str(self.checkout)], self.root,
                         env=dict(self.env, GIT_LFS_SKIP_SMUDGE='1'))
        scripts = self.checkout / 'scripts'
        scripts.mkdir()
        shutil.copyfile(ROOT / 'scripts/prepare-sources', scripts / 'prepare-sources')
        shutil.copyfile(ROOT / 'scripts/fetch-lfs.py', scripts / 'fetch-lfs.py')
        if P7:
            shutil.copyfile(ROOT / 'scripts/prepare-ci-sources', scripts / 'prepare-ci-sources')
        (scripts / 'install-deps').write_text('touch dependencies-started\n')
        self.post_create = json.loads((ROOT / '.devcontainer/devcontainer.json').read_text())[
            'postCreateCommand']

    def run_command(self, command, cwd, *, env=None, check=True):
        result = subprocess.run(command, cwd=cwd, env=self.env if env is None else env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout)
        return result

    def git(self, cwd, *arguments):
        return self.run_command(['git', *arguments], cwd)

    def repository(self, name, assets):
        path = self.root / name
        path.mkdir()
        self.git(path, 'init')
        self.git(path, 'config', 'user.name', 'Source preparation test')
        self.git(path, 'config', 'user.email', 'test@example.invalid')
        self.git(path, 'lfs', 'install', '--local')
        self.git(path, 'lfs', 'track', '*.STL')
        for relative, content in assets.items():
            destination = path / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        self.git(path, 'add', '.')
        self.git(path, 'commit', '-m', 'LFS fixtures')
        return path

    def test_post_create_fetches_root_and_submodule_lfs_and_can_be_repeated(self):
        self.assertTrue((self.checkout / 'root.STL').read_bytes().startswith(b'version https://'))
        for _ in range(2):
            self.run_command(['bash', '-c', self.post_create], self.checkout)
            self.assertTrue((self.checkout / 'dependencies-started').is_file())
            self.assertEqual((self.checkout / 'root.STL').read_bytes(), b'workspace asset\n')
            models = self.checkout / 'third_party/robot_descriptions'
            for relative, content in self.meshes.items():
                self.assertEqual((models / relative).read_bytes(), content)
            if P7:
                self.assertTrue((models / 'unrelated.STL').read_bytes().startswith(b'version https://'))
            else:
                self.assertEqual((models / 'nested/nested.STL').read_bytes(), b'nested mesh\n')

    def test_configured_subset_skips_unrelated_assets_but_fetches_nested_repositories(self):
        config = self.checkout / 'packaging'
        config.mkdir()
        (config / 'lfs.toml').write_text(
            '[repositories."third_party/robot_descriptions"]\n'
            'include = ["products/**"]\n')
        self.run_command(['bash', '-c', self.post_create], self.checkout)
        models = self.checkout / 'third_party/robot_descriptions'
        self.assertTrue((models / 'unrelated.STL').read_bytes().startswith(b'version https://'))
        for relative, content in self.meshes.items():
            self.assertEqual((models / relative).read_bytes(), content)
        self.assertEqual((models / 'nested/nested.STL').read_bytes(), b'nested mesh\n')

    def test_missing_lfs_object_stops_before_dependency_installation(self):
        digest = hashlib.sha256(b'arm mesh\n').hexdigest()
        (self.child / '.git/lfs/objects' / digest[:2] / digest[2:4] / digest).unlink()
        result = self.run_command(['bash', '-c', self.post_create], self.checkout, check=False)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.checkout / 'dependencies-started').exists())


if __name__ == '__main__':
    unittest.main()
