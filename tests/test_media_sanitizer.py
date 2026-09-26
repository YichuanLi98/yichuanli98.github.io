import io
import pathlib
import struct
import subprocess
import tempfile
import textwrap
import unittest
import zlib

from scripts import sanitize_media
from PIL import Image


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SANITIZER = REPO_ROOT / "scripts/sanitize_media.py"
VALIDATOR = REPO_ROOT / "scripts/validate_content.rb"


def image_bytes(image_format):
    output = io.BytesIO()
    Image.new("RGB", (2, 2), (132, 91, 64)).save(output, format=image_format)
    return output.getvalue()


def assert_decodes(test_case, data):
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    test_case.assertGreater(len(data), 20)


def jpeg_segment(marker, payload):
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def png_chunk(kind, payload):
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def webp_chunk(kind, payload):
    return kind + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")


def webp_chunks(data):
    chunks = []
    offset = 12
    while offset < len(data):
        kind = data[offset : offset + 4]
        size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        payload = data[offset + 8 : offset + 8 + size]
        chunks.append((kind, payload))
        offset += 8 + size + (size % 2)
    return chunks


class MediaSanitizerTest(unittest.TestCase):
    def test_jpeg_metadata_is_removed_without_touching_scan_data(self):
        clean = image_bytes("JPEG")
        dirty = (
            clean[:2]
            + jpeg_segment(0xE1, b"Exif\x00\x00camera-data")
            + jpeg_segment(0xED, b"Photoshop metadata")
            + jpeg_segment(0xFE, b"editor comment")
            + clean[2:]
        )

        sanitized = sanitize_media.sanitize_bytes(dirty, ".jpeg")

        self.assertNotIn(b"Exif\x00\x00", sanitized)
        self.assertNotIn(b"Photoshop metadata", sanitized)
        self.assertNotIn(b"editor comment", sanitized)
        self.assertEqual(
            sanitized[sanitized.index(b"\xff\xda") :],
            dirty[dirty.index(b"\xff\xda") :],
        )
        self.assertEqual(sanitize_media.sanitize_bytes(sanitized, ".jpeg"), sanitized)
        assert_decodes(self, sanitized)

    def test_png_metadata_chunks_are_removed_and_image_chunks_are_preserved(self):
        clean = image_bytes("PNG")
        metadata = b"".join(
            (
                png_chunk(b"eXIf", b"camera-data"),
                png_chunk(b"tEXt", b"Author\x00Yichuan"),
                png_chunk(b"zTXt", b"Comment\x00\x00compressed"),
                png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00xmp"),
                png_chunk(b"tIME", b"\x07\xe8\x01\x02\x03\x04\x05"),
            )
        )
        dirty = clean[:-12] + metadata + clean[-12:]

        sanitized = sanitize_media.sanitize_bytes(dirty, ".png")

        for kind in (b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"):
            self.assertNotIn(kind, sanitized)
        self.assertEqual(sanitized, clean)
        self.assertEqual(sanitize_media.sanitize_bytes(sanitized, ".png"), sanitized)
        assert_decodes(self, sanitized)

    def test_webp_metadata_chunks_and_feature_flags_are_removed(self):
        clean = image_bytes("WEBP")
        encoded_image_chunks = clean[12:]
        vp8x = bytes([0x0C, 0, 0, 0, 1, 0, 0, 1, 0, 0])
        body = (
            b"WEBP"
            + webp_chunk(b"VP8X", vp8x)
            + encoded_image_chunks
            + webp_chunk(b"EXIF", b"Exif\x00\x00camera-data")
            + webp_chunk(b"XMP ", b"<x:xmpmeta>data</x:xmpmeta>")
        )
        dirty = b"RIFF" + struct.pack("<I", len(body)) + body

        sanitized = sanitize_media.sanitize_bytes(dirty, ".webp")
        chunks = webp_chunks(sanitized)

        self.assertNotIn(b"EXIF", [kind for kind, _ in chunks])
        self.assertNotIn(b"XMP ", [kind for kind, _ in chunks])
        vp8x_payload = next(payload for kind, payload in chunks if kind == b"VP8X")
        self.assertEqual(vp8x_payload[0] & 0x0C, 0)
        self.assertIn(encoded_image_chunks, sanitized)
        self.assertEqual(struct.unpack("<I", sanitized[4:8])[0], len(sanitized) - 8)
        self.assertEqual(sanitize_media.sanitize_bytes(sanitized, ".webp"), sanitized)
        assert_decodes(self, sanitized)

    def test_check_and_write_cli_report_dirty_then_clean(self):
        clean = image_bytes("JPEG")
        dirty = clean[:2] + jpeg_segment(0xFE, b"private comment") + clean[2:]

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "work.jpeg"
            path.write_bytes(dirty)

            check_dirty = subprocess.run(
                ["python3", str(SANITIZER), "--check", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(check_dirty.returncode, 1)
            self.assertIn(str(path), check_dirty.stderr)

            write = subprocess.run(
                ["python3", str(SANITIZER), "--write", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(write.returncode, 0)
            self.assertNotEqual(path.read_bytes(), dirty)

            check_clean = subprocess.run(
                ["python3", str(SANITIZER), "--check", str(path)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(check_clean.returncode, 0)
            self.assertIn("media metadata: clean", check_clean.stdout)


class MediaReferenceValidationTest(unittest.TestCase):
    def run_validator(self, image, create_image=False):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            data_dir = root / "_data"
            works_dir = root / "_works"
            data_dir.mkdir()
            works_dir.mkdir()
            (data_dir / "site.yml").write_text(
                "\n".join(
                    (
                        "owner: {}",
                        "seo: {}",
                        "navigation: {}",
                        "hero: {}",
                        "sections: {}",
                        "footer: {}",
                        "contact: {}",
                    )
                ),
                encoding="utf-8",
            )
            work = textwrap.dedent(
                f"""
                ---
                title: Test work
                category: photography
                image: {image}
                alt: Test image
                description: ""
                location: ""
                order: 1
                featured: true
                visible: true
                ---
                """
            ).lstrip()
            (works_dir / "one.md").write_text(work, encoding="utf-8")
            if create_image:
                image_path = root / image.lstrip("/")
                image_path.parent.mkdir(parents=True)
                image_path.write_bytes(b"GIF89a")

            return subprocess.run(
                [
                    "ruby",
                    str(VALIDATOR),
                    "--site",
                    str(data_dir / "site.yml"),
                    "--works",
                    str(works_dir),
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )

    def test_missing_work_image_names_work_and_field(self):
        result = self.run_validator("/assets/images/works/missing.jpeg")
        self.assertEqual(result.returncode, 1)
        self.assertIn("one.md", result.stderr)
        self.assertIn("image", result.stderr)

    def test_unsupported_work_image_names_work_and_field(self):
        result = self.run_validator(
            "/assets/images/works/unsupported.gif",
            create_image=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("one.md", result.stderr)
        self.assertIn("image", result.stderr)
        self.assertIn("unsupported", result.stderr)


if __name__ == "__main__":
    unittest.main()
