import contextlib
import functools
import http.server
import json
import pathlib
import subprocess
import threading
import unittest
import urllib.request
from html.parser import HTMLParser


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


class GalleryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.lightbox_buttons = []
        self.ids = set()
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag == "img" and "gallery-image" in attributes.get("class", ""):
            self.images.append(attributes)
        if tag == "button" and "gallery-item" in attributes.get("class", ""):
            self.lightbox_buttons.append(attributes)
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass


class GallerySiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = functools.partial(QuietHandler, directory=REPO_ROOT)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def fetch(self, path):
        with contextlib.closing(urllib.request.urlopen(self.base_url + path)) as response:
            return response.status, response.headers, response.read()

    def test_homepage_exposes_the_portfolio_contract(self):
        status, _, body = self.fetch("/")
        self.assertEqual(status, 200)

        parser = GalleryParser()
        parser.feed(body.decode("utf-8"))

        self.assertEqual(parser.title.strip(), "Yichuan Li — Photography & Painting")
        self.assertEqual(len(parser.images), 8)
        self.assertEqual(len(parser.lightbox_buttons), 8)
        self.assertIn("photography", parser.ids)
        self.assertIn("painting", parser.ids)
        self.assertIn("gallery-lightbox", parser.ids)

        for image in parser.images:
            self.assertTrue(image.get("alt", "").strip())
            self.assertTrue(image.get("src", "").startswith("/assets/images/photography/"))

        for button in parser.lightbox_buttons:
            self.assertTrue(button.get("aria-label", "").strip())

    def test_every_gallery_image_is_served_as_jpeg(self):
        _, _, body = self.fetch("/")
        parser = GalleryParser()
        parser.feed(body.decode("utf-8"))

        self.assertEqual(len(parser.images), 8)
        for image in parser.images:
            status, headers, image_body = self.fetch(image["src"])
            self.assertEqual(status, 200)
            self.assertEqual(headers.get_content_type(), "image/jpeg")
            self.assertGreater(len(image_body), 10_000)

    def test_public_photographs_do_not_expose_exif_metadata(self):
        image_paths = sorted((REPO_ROOT / "assets/images/photography").glob("*.jpeg"))
        self.assertEqual(len(image_paths), 8)

        for image_path in image_paths:
            with self.subTest(image=image_path.name):
                contains_exif = b"Exif\x00\x00" in image_path.read_bytes()
                self.assertFalse(contains_exif, f"{image_path.name} contains EXIF metadata")

    def test_jekyll_config_does_not_publish_template_content(self):
        ruby_script = (
            'require "yaml"; require "json"; '
            'print JSON.generate(YAML.load_file("_config.yml"))'
        )
        result = subprocess.run(
            ["ruby", "-e", ruby_script],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        config = json.loads(result.stdout)

        expected_exclusions = {
            "_pages",
            "_posts",
            "_publications",
            "_talks",
            "_teaching",
            "_portfolio",
            "tests",
        }
        self.assertTrue(expected_exclusions.issubset(set(config["exclude"])))

        for collection_name in ("teaching", "publications", "portfolio", "talks"):
            with self.subTest(collection=collection_name):
                self.assertFalse(config["collections"][collection_name]["output"])


if __name__ == "__main__":
    unittest.main()
