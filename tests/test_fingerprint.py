import os
import pytest
from importer import fingerprint


def test_fingerprint_is_size_and_mtime(tmp_path):
    p = tmp_path / "a.grf"
    p.write_bytes(b"hello")
    fp = fingerprint.of_file(str(p))
    size, mtime_ns = fp.split(":")
    assert int(size) == 5
    assert int(mtime_ns) == os.stat(p).st_mtime_ns


def test_fingerprint_changes_when_content_grows(tmp_path):
    p = tmp_path / "a.grf"
    p.write_bytes(b"hello")
    fp1 = fingerprint.of_file(str(p))
    p.write_bytes(b"hello world")
    assert fingerprint.of_file(str(p)) != fp1


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        fingerprint.of_file(str(tmp_path / "nope.grf"))
