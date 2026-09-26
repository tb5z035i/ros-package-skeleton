"""Exercise the publisher's HTTP contract without publishing to GitLab."""

from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    'ci_publish_gitlab_release',
    Path(__file__).resolve().parents[1] / 'scripts/ci_publish_gitlab_release.py')
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublishTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'packaging.toml').write_text('[package]\nname = "example-workspace"\n')
        (self.root / 'dist').mkdir()
        self.filename = 'ros-jazzy-example-workspace_1.2.3+test-1_amd64.deb'
        (self.root / 'dist' / self.filename).write_bytes(b'debian package contents')
        (self.root / 'dist' / 'test-results.xml').write_text('<testsuites/>')
        self.requests = []
        self.upload_status = 201
        self.release_status = 201
        test = self

        class Handler(BaseHTTPRequestHandler):
            def handle_request(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                test.requests.append((self.command, self.path, self.headers, body))
                self.send_response(test.upload_status if self.command == 'PUT'
                                   else test.release_status)
                self.end_headers()
                self.wfile.write(b'{"message":"test response"}')

            do_PUT = handle_request
            do_POST = handle_request

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        self.api = f'http://127.0.0.1:{server.server_port}/api/v4'
        self.env = {
            'CI_API_V4_URL': self.api + '/',
            'CI_PROJECT_ID': 'group/project',
            'CI_JOB_TOKEN': 'test-job-token',
            'CI_COMMIT_TAG': 'v1.2.3+test-1',
            'NO_PROXY': '127.0.0.1',
        }
        self.stderr = io.StringIO()

    def publish(self):
        with (patch.object(publisher, 'REPO_ROOT', self.root),
              patch.dict(os.environ, self.env, clear=True),
              redirect_stdout(io.StringIO()), redirect_stderr(self.stderr)):
            return publisher.main()

    def test_uploads_debs_and_creates_release_with_registry_links(self):
        self.assertEqual(self.publish(), 0)
        self.assertEqual([request[0] for request in self.requests], ['PUT', 'POST'])
        upload, release = self.requests
        self.assertEqual(upload[1],
                         '/api/v4/projects/group%2Fproject/packages/generic/'
                         'example-workspace/1.2.3%2Btest-1/'
                         'ros-jazzy-example-workspace_1.2.3%2Btest-1_amd64.deb')
        self.assertEqual(upload[3], b'debian package contents')
        for request in self.requests:
            self.assertEqual(request[2]['JOB-TOKEN'], 'test-job-token')
        self.assertEqual(release[1], '/api/v4/projects/group%2Fproject/releases')
        self.assertEqual(release[2]['Content-Type'], 'application/json')
        payload = json.loads(release[3])
        self.assertEqual(payload['tag_name'], 'v1.2.3+test-1')
        self.assertEqual(payload['name'], 'example-workspace v1.2.3+test-1')
        self.assertIn('v1.2.3+test-1', payload['description'])
        self.assertEqual(payload['assets']['links'], [{
            'name': self.filename,
            'url': self.api.removesuffix('/api/v4') + upload[1],
            'link_type': 'package',
        }])

    def test_version_override_and_release_notes_without_v_tag_prefix(self):
        self.env.update(CI_COMMIT_TAG='1.2.3', DEB_VERSION='2.0-1')
        notes = self.root / 'docs/release-notes/v1.2.3.md'
        notes.parent.mkdir(parents=True)
        notes.write_text('# Release notes\n修复节点。\n', encoding='utf-8')
        self.publish()
        self.assertIn('/example-workspace/2.0-1/', self.requests[0][1])
        payload = json.loads(self.requests[-1][3])
        self.assertEqual(payload['tag_name'], '1.2.3')
        self.assertEqual(payload['description'], notes.read_text(encoding='utf-8'))

    def test_missing_artifacts_fail_before_any_request(self):
        (self.root / 'dist' / self.filename).unlink()
        with self.assertRaises(SystemExit):
            self.publish()
        self.assertIn('no .deb files', self.stderr.getvalue())
        self.assertEqual(self.requests, [])

    def test_all_four_targets_are_linked_in_one_release(self):
        (self.root / 'dist' / self.filename).unlink()
        filenames = set()
        for distro in ('jazzy', 'humble'):
            for architecture in ('amd64', 'arm64'):
                directory = self.root / 'dist' / distro / architecture
                directory.mkdir(parents=True)
                name = f'ros-{distro}-example-workspace_1.2.3+test-1_{architecture}.deb'
                (directory / name).write_bytes(b'package')
                filenames.add(name)
        self.publish()
        self.assertEqual([request[0] for request in self.requests], ['PUT'] * 4 + ['POST'])
        payload = json.loads(self.requests[-1][3])
        self.assertEqual(payload['name'], 'example-workspace v1.2.3+test-1')
        self.assertEqual({link['name'] for link in payload['assets']['links']}, filenames)
        self.assertEqual(len({link['url'] for link in payload['assets']['links']}), 4)

    def test_duplicate_filenames_fail_before_upload(self):
        directory = self.root / 'dist' / 'duplicate'
        directory.mkdir()
        (directory / self.filename).write_bytes(b'duplicate package')
        with self.assertRaises(SystemExit):
            self.publish()
        self.assertIn('duplicate .deb filenames', self.stderr.getvalue())
        self.assertEqual(self.requests, [])

    def test_missing_tag_or_token_fails_before_any_request(self):
        for key in ('CI_COMMIT_TAG', 'CI_JOB_TOKEN'):
            with self.subTest(key=key):
                value = self.env.pop(key)
                with self.assertRaises(SystemExit):
                    self.publish()
                self.assertIn(f'missing required env: {key}', self.stderr.getvalue())
                self.assertEqual(self.requests, [])
                self.env[key] = value

    def test_failed_upload_does_not_create_release(self):
        self.upload_status = 403
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertEqual([request[0] for request in self.requests], ['PUT'])

    def test_existing_release_is_reported_as_failure(self):
        self.release_status = 409
        with self.assertRaises(SystemExit):
            self.publish()
        self.assertIn('GitLab release create failed with HTTP 409', self.stderr.getvalue())
        self.assertIn('test response', self.stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
