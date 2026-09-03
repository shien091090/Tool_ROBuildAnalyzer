import struct
import zlib
from dataclasses import dataclass
from typing import Dict

HEADER_SIZE = 46


@dataclass
class GrfEntry:
    comp_len: int
    comp_len_aligned: int
    uncomp_len: int
    flags: int
    offset: int


def build_index(grf_path: str) -> Dict[str, GrfEntry]:
    with open(grf_path, "rb") as f:
        header = f.read(HEADER_SIZE)
        if header[0:15] != b"Master of Magic":
            raise ValueError(f"not a GRF file: {grf_path}")
        file_table_offset, seed, files, version = struct.unpack_from("<IIII", header, 30)

        f.seek(HEADER_SIZE + file_table_offset)
        pack_size, real_size = struct.unpack("<II", f.read(8))
        raw = zlib.decompress(f.read(pack_size))
        if len(raw) != real_size:
            raise ValueError(f"file table size mismatch: expected {real_size}, got {len(raw)}")

    index: Dict[str, GrfEntry] = {}
    pos = 0
    while pos < len(raw):
        nul = raw.find(b"\x00", pos)
        if nul == -1:
            break
        name = raw[pos:nul]
        pos = nul + 1
        if pos + 17 > len(raw):
            break
        comp_len, comp_len_aligned, uncomp_len, flags, offset = struct.unpack_from("<IIIBI", raw, pos)
        pos += 17
        key = name.decode("cp949", errors="replace").lower().replace("/", "\\")
        index[key] = GrfEntry(comp_len, comp_len_aligned, uncomp_len, flags, offset)
    return index


def extract(grf_path: str, entry: GrfEntry) -> bytes:
    if entry.flags != 1:
        raise ValueError(f"unsupported flags={entry.flags} (encrypted entries not implemented)")
    with open(grf_path, "rb") as f:
        f.seek(HEADER_SIZE + entry.offset)
        data = f.read(entry.comp_len)
    decompressed = zlib.decompress(data)
    if len(decompressed) != entry.uncomp_len:
        raise ValueError(f"size mismatch: expected {entry.uncomp_len}, got {len(decompressed)}")
    return decompressed
