# =============================================================================
#   tests/test_file_utils.py — VaultSentry v1.0
#   Egyan | Red Parrot Accounting Ltd
#
#   Tests for utils/file_utils.py
#   All tests use tmp_path (pytest fixture) — no files written to disk permanently.
# =============================================================================

import os
import sys
import zipfile
import hashlib

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import patch

# Patch config before importing anything that uses it
with patch("config.LOG_DIR", "/tmp/vaultsentry_test_logs"), \
     patch("config.LOG_FILE", "/tmp/vaultsentry_test_logs/test.log"):
    from utils.file_utils import (
        calculate_sha256, calculate_entropy,
        is_file_openable, get_file_list, format_size
    )


# =============================================================================
#   calculate_sha256
# =============================================================================

class TestCalculateSha256:
    def test_known_content(self, tmp_path):
        """SHA-256 of known content must match expected hash."""
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert calculate_sha256(str(f)) == expected

    def test_returns_string(self, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"\x00" * 1024)
        result = calculate_sha256(str(f))
        assert isinstance(result, str)
        assert len(result) == 64

    def test_different_content_different_hash(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"content A")
        b.write_bytes(b"content B")
        assert calculate_sha256(str(a)) != calculate_sha256(str(b))

    def test_same_content_same_hash(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"identical")
        b.write_bytes(b"identical")
        assert calculate_sha256(str(a)) == calculate_sha256(str(b))

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert calculate_sha256(str(f)) == expected

    def test_missing_file_returns_none(self):
        assert calculate_sha256("/nonexistent/path/file.txt") is None

    def test_large_file_chunked(self, tmp_path):
        """Files larger than 64KB chunk size must still hash correctly."""
        data = b"X" * 200_000
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert calculate_sha256(str(f)) == expected


# =============================================================================
#   calculate_entropy
# =============================================================================

class TestCalculateEntropy:
    def test_uniform_bytes_high_entropy(self, tmp_path):
        """Random-looking bytes should produce high entropy (>7.0)."""
        import os as _os
        data = bytes(range(256)) * 400  # all 256 byte values equally distributed
        f = tmp_path / "uniform.bin"
        f.write_bytes(data)
        entropy = calculate_entropy(str(f))
        assert entropy > 7.0

    def test_single_byte_zero_entropy(self, tmp_path):
        """File with all identical bytes has entropy near 0."""
        f = tmp_path / "zeros.bin"
        f.write_bytes(b"\x00" * 1024)
        entropy = calculate_entropy(str(f))
        assert entropy == 0.0

    def test_text_file_moderate_entropy(self, tmp_path):
        """Normal text file should have moderate entropy (2–6)."""
        f = tmp_path / "text.txt"
        f.write_text("The quick brown fox jumps over the lazy dog. " * 100)
        entropy = calculate_entropy(str(f))
        assert 2.0 < entropy < 7.0

    def test_empty_file_returns_zero(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert calculate_entropy(str(f)) == 0.0

    def test_missing_file_returns_zero(self):
        assert calculate_entropy("/no/such/file.bin") == 0.0

    def test_returns_float(self, tmp_path):
        f = tmp_path / "f.bin"
        f.write_bytes(b"abcdef" * 100)
        result = calculate_entropy(str(f))
        assert isinstance(result, float)

    def test_entropy_range(self, tmp_path):
        """Entropy must always be between 0.0 and 8.0."""
        f = tmp_path / "f.bin"
        f.write_bytes(b"abcabc" * 500)
        entropy = calculate_entropy(str(f))
        assert 0.0 <= entropy <= 8.0


# =============================================================================
#   is_file_openable
# =============================================================================

class TestIsFileOpenable:
    def test_valid_zip(self, tmp_path):
        f = tmp_path / "ok.zip"
        with zipfile.ZipFile(str(f), "w") as z:
            z.writestr("hello.txt", "hello world")
        ok, msg = is_file_openable(str(f))
        assert ok is True
        assert "OK" in msg or "ok" in msg.lower()

    def test_corrupt_zip(self, tmp_path):
        f = tmp_path / "corrupt.zip"
        f.write_bytes(b"PK\x03\x04" + b"\xff" * 100)  # bad ZIP content
        ok, msg = is_file_openable(str(f))
        assert ok is False

    def test_empty_file_not_openable(self, tmp_path):
        f = tmp_path / "empty.bak"
        f.write_bytes(b"")
        ok, msg = is_file_openable(str(f))
        assert ok is False
        assert "empty" in msg.lower()

    def test_non_zip_extension_readable(self, tmp_path):
        f = tmp_path / "data.sql"
        f.write_bytes(b"SELECT * FROM table;")
        ok, msg = is_file_openable(str(f))
        assert ok is True

    def test_docx_valid_header(self, tmp_path):
        """A valid .docx starts with PK magic bytes."""
        f = tmp_path / "doc.docx"
        with zipfile.ZipFile(str(f), "w") as z:
            z.writestr("word/document.xml", "<doc/>")
        ok, msg = is_file_openable(str(f))
        assert ok is True

    def test_docx_invalid_header(self, tmp_path):
        f = tmp_path / "bad.docx"
        f.write_bytes(b"\xff\xfe garbage")
        ok, msg = is_file_openable(str(f))
        assert ok is False

    def test_missing_file_returns_false(self):
        ok, msg = is_file_openable("/no/such/file.zip")
        assert ok is False


# =============================================================================
#   get_file_list
# =============================================================================

class TestGetFileList:
    def test_returns_files_with_extension_filter(self, tmp_path):
        (tmp_path / "a.zip").write_bytes(b"PK")
        (tmp_path / "b.txt").write_bytes(b"text")
        (tmp_path / "c.zip").write_bytes(b"PK")
        result = get_file_list([str(tmp_path)], [".zip"])
        assert len(result) == 2
        assert all(f.endswith(".zip") for f in result)

    def test_returns_all_files_when_no_extension_filter(self, tmp_path):
        for name in ["a.zip", "b.sql", "c.bak"]:
            (tmp_path / name).write_bytes(b"data")
        result = get_file_list([str(tmp_path)], [])
        assert len(result) == 3

    def test_skips_missing_paths(self):
        result = get_file_list(["/no/such/path"], [".zip"])
        assert result == []

    def test_recurses_subdirectories(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (tmp_path / "top.zip").write_bytes(b"PK")
        (subdir / "nested.zip").write_bytes(b"PK")
        result = get_file_list([str(tmp_path)], [".zip"])
        assert len(result) == 2

    def test_skips_hidden_directories(self, tmp_path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "file.zip").write_bytes(b"PK")
        (tmp_path / "visible.zip").write_bytes(b"PK")
        result = get_file_list([str(tmp_path)], [".zip"])
        assert len(result) == 1
        assert all(".hidden" not in f for f in result)

    def test_multiple_paths(self, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "a.zip").write_bytes(b"PK")
        (dir2 / "b.zip").write_bytes(b"PK")
        result = get_file_list([str(dir1), str(dir2)], [".zip"])
        assert len(result) == 2


# =============================================================================
#   format_size
# =============================================================================

class TestFormatSize:
    def test_bytes(self):
        assert "B" in format_size(512)

    def test_kilobytes(self):
        assert "KB" in format_size(2048)

    def test_megabytes(self):
        assert "MB" in format_size(2 * 1024 * 1024)

    def test_gigabytes(self):
        assert "GB" in format_size(2 * 1024 ** 3)

    def test_zero(self):
        result = format_size(0)
        assert "0" in result

    def test_negative_safe(self):
        """Negative values (size deltas) must not crash."""
        result = format_size(-1024)
        assert "KB" in result

    def test_returns_string(self):
        assert isinstance(format_size(1234567), str)
