"""Check native bundle launch, Linux bridge behavior, and client cleanup."""
import argparse
import contextlib
import io
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

LAB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LAB))
import launch


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix='hackpack-launch-test-')
        self.root = Path(self.work.name).resolve()
        self.app = self.root / 'Client With Spaces.app'
        self.contents = self.app / 'Contents'
        self.runtime = self.contents / 'Resources' / 'Runtime'
        self.runtime.mkdir(parents=True)
        self.executable = self.contents / 'MacOS' / 'NativeClient'
        self.executable.parent.mkdir()
        self.executable.write_text('#!/bin/sh\nexit 0\n')
        self.executable.chmod(0o755)
        with (self.contents / 'Info.plist').open('wb') as stream:
            plistlib.dump({'CFBundleExecutable': self.executable.name}, stream)
        self.args = argparse.Namespace(name='Test Player', server='example.test:27015',
                                       port=49100, team=None)

    def tearDown(self):
        self.work.cleanup()

    @patch.object(launch.sys, 'platform', 'darwin')
    def test_bundle_executable_and_arguments_with_spaces(self):
        command, cwd, bridge = launch.launch_command(
            self.app, self.args, ['-width', '800', '+password', 'two words'])
        self.assertEqual(command, [str(self.executable), '+name', 'Test Player',
                                   '-width', '800', '+password', 'two words',
                                   '+connect', 'example.test:27015'])
        self.assertEqual(cwd, self.runtime)
        self.assertFalse(bridge)

    @patch.object(launch.sys, 'platform', 'darwin')
    def test_malformed_and_incomplete_bundles_are_rejected(self):
        info = self.contents / 'Info.plist'
        info.write_bytes(b'invalid plist')
        with self.assertRaisesRegex(ValueError, 'Info.plist'):
            launch.launch_command(self.app, self.args, [])
        for metadata in [[], {}, {'CFBundleExecutable': '../outside'}]:
            with self.subTest(metadata=metadata):
                with info.open('wb') as stream:
                    plistlib.dump(metadata, stream)
                with self.assertRaisesRegex(ValueError, 'CFBundleExecutable'):
                    launch.launch_command(self.app, self.args, [])
        with info.open('wb') as stream:
            plistlib.dump({'CFBundleExecutable': self.executable.name}, stream)
        self.executable.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'executable'):
            launch.launch_command(self.app, self.args, [])
        self.executable.chmod(0o755)
        self.runtime.rmdir()
        with self.assertRaisesRegex(ValueError, 'Runtime'):
            launch.launch_command(self.app, self.args, [])

    def test_runtime_platform_mismatch_is_rejected(self):
        with patch.object(launch.sys, 'platform', 'linux'):
            with self.assertRaisesRegex(ValueError, 'macOS'):
                launch.launch_command(self.app, self.args, [])
        with patch.object(launch.sys, 'platform', 'darwin'):
            with self.assertRaisesRegex(ValueError, 'CS16Client.app'):
                launch.launch_command(self.root, self.args, [])

    @patch.object(launch.sys, 'platform', 'darwin')
    def test_stock_mac_launch_uses_no_bridge_or_linux_debug_opt_in(self):
        child = Mock()
        child.wait.return_value = 7
        with patch.object(launch, 'start_serialized', return_value=child) as start, \
                patch.object(launch, 'send_command') as send, \
                patch.dict(os.environ, {}, clear=True):
            result = launch.main([str(self.app), '--name', 'Test Player', '--debug',
                                  '--server', self.args.server, '--', '-width', '800'])
        self.assertEqual(result, 7)
        command, cwd, env = start.call_args.args
        self.assertEqual(command[-4:], ['-width', '800', '+connect', self.args.server])
        self.assertEqual(cwd, self.runtime)
        self.assertNotIn('HACKPACK_ALLOW_PTRACE', env)
        send.assert_not_called()

    @patch.object(launch.sys, 'platform', 'darwin')
    def test_mac_team_flag_reports_overlay_requirement_before_launch(self):
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors), patch.object(launch, 'start_serialized') as start:
            with self.assertRaises(SystemExit) as result:
                launch.main([str(self.app), '--team', 'ct'])
        self.assertEqual(result.exception.code, 2)
        self.assertIn('--team requires the Linux lab overlay', errors.getvalue())
        start.assert_not_called()

    @patch.object(launch.sys, 'platform', 'linux')
    def test_linux_keeps_overlay_team_debug_and_delayed_connection(self):
        entrypoint = self.root / 'start.sh'
        entrypoint.write_text('#!/bin/sh\nexit 0\n')
        entrypoint.chmod(0o755)
        child = Mock()
        child.poll.return_value = None
        child.wait.return_value = 0
        with patch.object(launch, 'start_serialized', return_value=child) as start, \
                patch.object(launch, 'send_command') as send, \
                patch.object(launch.time, 'sleep') as sleep:
            self.assertEqual(launch.main([str(self.root), '--team', 'ct', '--debug',
                                          '--port', '49200', '--', '-nosound']), 0)
        command, cwd, env = start.call_args.args
        self.assertEqual(command, [str(entrypoint), '+name', 'HackPack-Instructor',
                                   '+exec', 'hackpack.cfg', '+hp_bridge_port', '49200',
                                   '+hp_autojoin', '2', '-nosound'])
        self.assertEqual(cwd, self.root)
        self.assertEqual(env['HACKPACK_ALLOW_PTRACE'], '1')
        sleep.assert_called_once_with(2)
        send.assert_called_once_with('connect cs.mahaloz.re:27015', 49200)

    @patch.object(launch.sys, 'platform', 'darwin')
    def test_ctrl_c_terminates_native_client(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [KeyboardInterrupt, 0]
        with patch.object(launch, 'start_serialized', return_value=child), \
                patch.object(launch, 'send_command') as send:
            self.assertEqual(launch.main([str(self.app)]), 0)
        child.terminate.assert_called_once()
        child.kill.assert_not_called()
        send.assert_not_called()

    def test_unresponsive_linux_client_is_killed_after_bridge_quit(self):
        child = Mock()
        child.poll.return_value = None
        child.wait.side_effect = [subprocess.TimeoutExpired('client', 3), 0]
        with patch.object(launch, 'send_command') as send:
            launch.stop_client(child, 49200, True)
        send.assert_called_once_with('hp_off\nquit', 49200)
        child.kill.assert_called_once()


if __name__ == '__main__':
    unittest.main()
