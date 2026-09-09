"""Strict language-neutral frame codec."""

import json
import struct
import time
from dataclasses import dataclass

import numpy as np

MAX_PACKET = 257 * 1024 * 1024
DTYPES = {"float32": np.dtype("<f4"), "uint8": np.dtype("u1")}


@dataclass
class Frame:
    header: dict
    arrays: dict[str, np.ndarray]
    receive_age_ms: float | None = None
    skipped: int = 0

    @property
    def seq(self):
        return self.header["seq"]

    @property
    def generation(self):
        return self.header["generation"]


def encode_frame(header, arrays, *, stamp_emitted_at=False):
    """Pack payload before stamping, returning a read-only, owned buffer view.

    Reserved prefix space avoids a full payload copy after the timestamp, matching
    the Rust encoder. The underlying buffer is never mutated after publication.
    """
    reserved = 4096
    packet = bytearray(reserved)
    descriptors, offset = [], 0
    for name, array in arrays.items():
        if array.dtype.kind == "f":
            array = np.asarray(array, dtype="<f4", order="C")
            dtype = "float32"
        elif array.dtype == np.uint8:
            array = np.ascontiguousarray(array)
            dtype = "uint8"
        else:
            raise ValueError(f"unsupported array dtype {array.dtype}")
        raw = memoryview(array).cast("B")
        descriptors.append(
            dict(name=name, dtype=dtype, shape=list(array.shape), offset=offset, nbytes=len(raw))
        )
        packet.extend(raw)
        offset += len(raw)
    header = dict(header)
    if stamp_emitted_at:
        header["emitted_at_ms"] = time.time_ns() / 1e6
    raw_header = json.dumps(
        dict(header, version=1, arrays=descriptors), separators=(",", ":"), allow_nan=False
    ).encode()
    prefix_size = (len(raw_header) + 7) & ~3
    if prefix_size > reserved:
        raise ValueError("frame header exceeds reserved prefix")
    start = reserved - prefix_size
    struct.pack_into("<I", packet, start, len(raw_header))
    packet[start + 4 : start + 4 + len(raw_header)] = raw_header
    return memoryview(packet)[start:].toreadonly()


def decode_frame(packet):
    if not 4 <= len(packet) <= MAX_PACKET:
        raise ValueError("invalid frame size")
    header_size = struct.unpack_from("<I", packet)[0]
    if header_size > 65536 or header_size + 4 > len(packet):
        raise ValueError("invalid frame header length")
    header = json.loads(bytes(packet[4 : 4 + header_size]))
    if not isinstance(header, dict) or header.get("version") != 1:
        raise ValueError("unsupported protocol version")
    for key in ("seq", "generation"):
        if type(header.get(key)) is not int or header[key] < 0:
            raise ValueError(f"invalid {key}")
    base = (header_size + 7) // 4 * 4
    arrays, end = {}, 0
    for descriptor in header["arrays"]:
        name, shape = descriptor["name"], descriptor["shape"]
        if name not in ("waveform", "image") or name in arrays:
            raise ValueError("invalid or repeated array name")
        if not isinstance(shape, list) or not 1 <= len(shape) <= 3:
            raise ValueError("invalid shape")
        if any(type(n) is not int or n <= 0 for n in shape):
            raise ValueError("invalid array dimension")
        dtype = DTYPES.get(descriptor["dtype"])
        if dtype is None:
            raise ValueError("unsupported dtype")
        count = 1
        for n in shape:
            count *= n
        size = count * dtype.itemsize
        if descriptor["offset"] != end or descriptor["nbytes"] != size:
            raise ValueError("noncontiguous array descriptor or size mismatch")
        if base + end + size > len(packet):
            raise ValueError("truncated array")
        arrays[name] = np.frombuffer(packet, dtype=dtype, count=count, offset=base + end).reshape(
            shape
        )
        end += size
    if base + end != len(packet):
        raise ValueError("unexpected trailing bytes")
    return Frame(header, arrays)


def decode_replay(data):
    if len(data) < 4:
        raise ValueError("truncated replay")
    count = struct.unpack_from("<I", data)[0]
    if not 2 <= count <= 256:
        raise ValueError("replay must contain between 2 and 256 changing frames")
    offset, frames = 4, []
    for _ in range(count):
        if offset + 4 > len(data):
            raise ValueError("truncated replay length")
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        if offset + length > len(data):
            raise ValueError("truncated replay frame")
        frames.append(decode_frame(data[offset : offset + length]))
        offset += length
    if offset != len(data):
        raise ValueError("unexpected replay trailing bytes")
    return frames
