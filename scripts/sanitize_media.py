#!/usr/bin/env python3

import argparse
import pathlib
import struct
import sys


SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
JPEG_STRIPPED_MARKERS = {0xE1, 0xED, 0xFE}
PNG_STRIPPED_CHUNKS = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
WEBP_STRIPPED_CHUNKS = {b"EXIF", b"XMP "}


class MediaFormatError(ValueError):
    pass


def _sanitize_jpeg(data):
    if not data.startswith(b"\xff\xd8"):
        raise MediaFormatError("invalid JPEG signature")

    output = bytearray(data[:2])
    offset = 2
    while offset < len(data):
        marker_start = offset
        if data[offset] != 0xFF:
            raise MediaFormatError(f"invalid JPEG marker at byte {offset}")

        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            raise MediaFormatError("truncated JPEG marker")

        marker = data[offset]
        offset += 1
        if marker == 0xDA:
            output.extend(data[marker_start:])
            return bytes(output)
        if marker == 0xD9:
            output.extend(data[marker_start:])
            return bytes(output)
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            output.extend(data[marker_start:offset])
            continue

        if offset + 2 > len(data):
            raise MediaFormatError("truncated JPEG segment length")
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if segment_length < 2:
            raise MediaFormatError("invalid JPEG segment length")
        segment_end = offset + segment_length
        if segment_end > len(data):
            raise MediaFormatError("truncated JPEG segment")

        if marker not in JPEG_STRIPPED_MARKERS:
            output.extend(data[marker_start:segment_end])
        offset = segment_end

    raise MediaFormatError("JPEG is missing scan data")


def _sanitize_png(data):
    signature = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(signature):
        raise MediaFormatError("invalid PNG signature")

    output = bytearray(signature)
    offset = len(signature)
    found_end = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise MediaFormatError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise MediaFormatError("truncated PNG chunk payload")
        kind = data[offset + 4 : offset + 8]
        if kind not in PNG_STRIPPED_CHUNKS:
            output.extend(data[offset:chunk_end])
        offset = chunk_end
        if kind == b"IEND":
            found_end = True
            output.extend(data[offset:])
            break

    if not found_end:
        raise MediaFormatError("PNG is missing IEND")
    return bytes(output)


def _webp_chunk(kind, payload, padding=b""):
    pad = padding if len(payload) % 2 else b""
    if len(payload) % 2 and not pad:
        pad = b"\x00"
    return kind + struct.pack("<I", len(payload)) + payload + pad[:1]


def _sanitize_webp(data):
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise MediaFormatError("invalid WebP signature")
    declared_size = struct.unpack("<I", data[4:8])[0]
    if declared_size + 8 > len(data):
        raise MediaFormatError("truncated WebP RIFF payload")

    chunks = bytearray()
    offset = 12
    while offset < len(data):
        if offset + 8 > len(data):
            raise MediaFormatError("truncated WebP chunk")
        kind = data[offset : offset + 4]
        size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        payload_start = offset + 8
        payload_end = payload_start + size
        padded_end = payload_end + (size % 2)
        if padded_end > len(data):
            raise MediaFormatError("truncated WebP chunk payload")
        payload = data[payload_start:payload_end]
        padding = data[payload_end:padded_end]

        if kind not in WEBP_STRIPPED_CHUNKS:
            if kind == b"VP8X":
                if len(payload) < 10:
                    raise MediaFormatError("invalid WebP VP8X chunk")
                payload = bytes([payload[0] & ~0x0C]) + payload[1:]
                chunks.extend(_webp_chunk(kind, payload, padding))
            else:
                chunks.extend(data[offset:padded_end])
        offset = padded_end

    body = b"WEBP" + bytes(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def sanitize_bytes(data, suffix):
    suffix = suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return _sanitize_jpeg(data)
    if suffix == ".png":
        return _sanitize_png(data)
    if suffix == ".webp":
        return _sanitize_webp(data)
    raise MediaFormatError(f"unsupported image extension: {suffix or '(none)'}")


def sanitize_file(path, write=False):
    path = pathlib.Path(path)
    original = path.read_bytes()
    sanitized = sanitize_bytes(original, path.suffix)
    changed = sanitized != original
    if changed and write:
        path.write_bytes(sanitized)
    return changed


def _expand_paths(paths):
    expanded = []
    for raw_path in paths:
        path = pathlib.Path(raw_path)
        if path.is_dir():
            expanded.extend(
                candidate
                for candidate in sorted(path.rglob("*"))
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES
            )
        else:
            expanded.append(path)
    return expanded


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remove private metadata from portfolio media.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if a file would change")
    mode.add_argument("--write", action="store_true", help="sanitize files in place")
    parser.add_argument("paths", nargs="+", help="image files or directories")
    args = parser.parse_args(argv)

    dirty = []
    failed = False
    for path in _expand_paths(args.paths):
        try:
            changed = sanitize_file(path, write=args.write)
        except (OSError, MediaFormatError) as error:
            print(f"{path}: {error}", file=sys.stderr)
            failed = True
            continue
        if changed:
            if args.check:
                dirty.append(path)
            else:
                print(f"sanitized: {path}")

    if failed:
        return 2
    if dirty:
        for path in dirty:
            print(f"{path}: removable metadata detected", file=sys.stderr)
        return 1

    print("media metadata: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
