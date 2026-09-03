import struct
import zlib
from typing import Dict

from importer.grf import build_index, extract

HEADER_SIZE = 46


def _make_grf(files: Dict[str, bytes]) -> bytes:
    """files: {relative_path: raw_content} — 組一個最小合法 0x200 版 GRF。"""
    entries_blob = b""
    file_data_blob = b""
    running_offset = 0
    entry_records = []
    for name, content in files.items():
        compressed = zlib.compress(content)
        entry_records.append((name, compressed, len(content)))
        file_data_blob += compressed
    for name, compressed, uncomp_len in entry_records:
        record = (
            name.encode("cp949") + b"\x00"
            + struct.pack("<IIIBI", len(compressed), len(compressed), uncomp_len, 1, running_offset)
        )
        entries_blob += record
        running_offset += len(compressed)

    seed = 0
    real_count = len(files)
    files_field = real_count + seed + 7
    version = 0x200

    table_pack = zlib.compress(entries_blob)
    table_section = struct.pack("<II", len(table_pack), len(entries_blob)) + table_pack

    file_table_offset = len(file_data_blob)
    header = (
        b"Master of Magic" + b"\x00"
        + b"\x00" * 14
        + struct.pack("<IIII", file_table_offset, seed, files_field, version)
    )
    return header + file_data_blob + table_section


def test_build_index_and_extract(tmp_path):
    content_a = b"hello world " * 50
    content_b = b'Item = {[1] = {Type = "ammo"}}'
    grf_bytes = _make_grf({
        "data\\LuaFiles514\\Lua Files\\A.lub": content_a,
        "data\\LuaFiles514\\Lua Files\\B.lub": content_b,
    })
    grf_path = tmp_path / "test.grf"
    grf_path.write_bytes(grf_bytes)

    index = build_index(str(grf_path))
    assert "data\\luafiles514\\lua files\\a.lub" in index
    assert "data\\luafiles514\\lua files\\b.lub" in index

    entry_a = index["data\\luafiles514\\lua files\\a.lub"]
    assert extract(str(grf_path), entry_a) == content_a

    entry_b = index["data\\luafiles514\\lua files\\b.lub"]
    assert extract(str(grf_path), entry_b) == content_b
