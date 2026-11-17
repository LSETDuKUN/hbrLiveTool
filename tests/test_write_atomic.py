import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hbr_data.sync import write_atomic


class WriteAtomicTest(unittest.TestCase):
    def test_writes_and_leaves_no_partial_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'a.json'
            write_atomic(path, b'data')
            self.assertEqual(path.read_bytes(), b'data')
            self.assertEqual(list(Path(root).iterdir()), [path])

    def test_failed_write_does_not_create_target(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'a.json'
            with mock.patch.object(Path, 'replace', side_effect=OSError('boom')):
                with self.assertRaises(OSError):
                    write_atomic(path, b'data')
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_retries_once_on_windows_permission_error(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'a.json'
            real_replace = Path.replace
            calls = []

            def flaky_replace(self_path, target):
                calls.append(target)
                if len(calls) == 1:
                    raise PermissionError('transient lock')
                return real_replace(self_path, target)

            with mock.patch.object(Path, 'replace', autospec=True, side_effect=flaky_replace):
                write_atomic(path, b'data')
            self.assertEqual(len(calls), 2)
            self.assertEqual(path.read_bytes(), b'data')
            self.assertEqual(list(Path(root).iterdir()), [path])


if __name__ == '__main__':
    unittest.main()
