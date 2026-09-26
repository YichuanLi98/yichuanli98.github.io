import contextlib
import functools
import http.server
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from html.parser import HTMLParser


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def load_gallery_contract(source_dir):
    ruby = r'''
require "date"
require "json"
require "yaml"

root = ARGV.fetch(0)
site = YAML.safe_load(
  File.read(File.join(root, "_data", "site.yml")),
  permitted_classes: [Date],
  aliases: true
)
works = Dir.glob(File.join(root, "_works", "*.md")).sort.map do |path|
  text = File.read(path)
  front_matter = text.match(/\A---\s*\n(.*?)\n---\s*(?:\n|\z)/m)[1]
  data = YAML.safe_load(
    front_matter,
    permitted_classes: [Date],
    aliases: true
  ) || {}
  {
    "slug" => File.basename(path, File.extname(path)),
    "title" => data["title"],
    "category" => data["category"],
    "image" => data["image"],
    "visible" => data["visible"]
  }
end

print JSON.generate({
  "order" => site.dig("sections", "photography", "work_order"),
  "works" => works
})
'''
    result = subprocess.run(
        ["ruby", "-e", ruby, str(source_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    photographs = {
        work["slug"]: work
        for work in data["works"]
        if work["category"] == "photography" and work["visible"] is True
    }
    ordered = [
        photographs[slug]
        for slug in data["order"]
        if slug in photographs
    ]
    ordered_slugs = {work["slug"] for work in ordered}
    fallback = sorted(
        (
            work
            for slug, work in photographs.items()
            if slug not in ordered_slugs
        ),
        key=lambda work: work["title"],
    )
    return ordered + fallback


def update_site_fixture(source_dir, *, featured_work, photography_order):
    ruby = r'''
require "date"
require "json"
require "yaml"

path = ARGV.fetch(0)
data = YAML.safe_load(
  File.read(path),
  permitted_classes: [Date],
  aliases: true
)
data["seo"]["title"] = "Fixture Portfolio — Rendered from YAML"
data["seo"]["description"] = "Fixture description rendered from structured content."
data["hero"]["featured_work"] = ARGV.fetch(1)
data["sections"]["photography"]["work_order"] = JSON.parse(ARGV.fetch(2))
File.write(path, YAML.dump(data))
'''
    subprocess.run(
        [
            "ruby",
            "-e",
            ruby,
            str(source_dir / "_data" / "site.yml"),
            featured_work,
            json.dumps(photography_order),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


class GalleryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.lightbox_buttons = []
        self.galleries = []
        self.ids = set()
        self.meta_description = ""
        self.hero_image = None
        self.painting_holding = False
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag == "img" and "gallery-image" in attributes.get("class", ""):
            self.images.append(attributes)
        if tag == "img" and "hero-image" in attributes.get("class", ""):
            self.hero_image = attributes
        if tag == "button" and "gallery-item" in attributes.get("class", ""):
            self.lightbox_buttons.append(attributes)
        if tag == "div" and "gallery" in attributes.get("class", "").split():
            self.galleries.append(attributes)
        if "painting-holding" in attributes.get("class", "").split():
            self.painting_holding = True
        if tag == "meta" and attributes.get("name") == "description":
            self.meta_description = attributes.get("content", "")
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
        def ignore_local_build_artifacts(directory, names):
            if pathlib.Path(directory) != REPO_ROOT:
                return set()
            return set(names).intersection(
                {
                    ".git",
                    ".worktrees",
                    ".superpowers",
                    ".bundle",
                    "node_modules",
                    "vendor",
                    "_site",
                }
            )

        cls.temp_dir = tempfile.TemporaryDirectory()
        fixture_root = pathlib.Path(cls.temp_dir.name)
        cls.source_dir = fixture_root / "source"
        cls.build_dir = fixture_root / "site"
        shutil.copytree(
            REPO_ROOT,
            cls.source_dir,
            ignore=ignore_local_build_artifacts,
        )

        initial_photography = load_gallery_contract(cls.source_dir)
        fixture_order = [work["slug"] for work in reversed(initial_photography)]
        update_site_fixture(
            cls.source_dir,
            featured_work=fixture_order[0],
            photography_order=fixture_order,
        )

        (cls.source_dir / "_works/99-hidden.md").write_text(
            """---
title: "Hidden Fixture Work"
category: photography
image: "/assets/images/works/hidden-fixture.jpeg"
alt: "This hidden work must not render"
description: ""
location: ""
visible: false
---
""",
            encoding="utf-8",
        )
        (cls.source_dir / "_works/10-painting-fixture.md").write_text(
            """---
title: "Painting Fixture"
category: painting
image: "/assets/images/works/photo-03.jpeg"
alt: "A painting fixture hidden by the coming soon state"
description: ""
location: ""
visible: true
---
""",
            encoding="utf-8",
        )

        cls.expected_photography = load_gallery_contract(cls.source_dir)

        build = subprocess.run(
            [
                "bundle",
                "exec",
                "jekyll",
                "build",
                "--strict_front_matter",
                "--destination",
                str(cls.build_dir),
            ],
            cwd=cls.source_dir,
            capture_output=True,
            env={**os.environ, "BUNDLE_GEMFILE": str(REPO_ROOT / "Gemfile")},
            text=True,
        )
        if build.returncode:
            raise AssertionError(
                f"Jekyll fixture build failed:\n{build.stdout}\n{build.stderr}"
            )

        handler = functools.partial(QuietHandler, directory=cls.build_dir)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp_dir.cleanup()

    def fetch(self, path):
        with contextlib.closing(urllib.request.urlopen(self.base_url + path)) as response:
            return response.status, response.headers, response.read()

    def test_homepage_exposes_the_portfolio_contract(self):
        status, _, body = self.fetch("/")
        self.assertEqual(status, 200)

        parser = GalleryParser()
        parser.feed(body.decode("utf-8"))

        self.assertEqual(parser.title.strip(), "Fixture Portfolio — Rendered from YAML")
        self.assertEqual(
            parser.meta_description,
            "Fixture description rendered from structured content.",
        )
        self.assertEqual(len(parser.images), len(self.expected_photography))
        self.assertEqual(len(parser.lightbox_buttons), len(self.expected_photography))
        self.assertIn("photography", parser.ids)
        self.assertIn("painting", parser.ids)
        self.assertIn("gallery-lightbox", parser.ids)
        self.assertEqual(
            parser.hero_image["src"],
            self.expected_photography[0]["image"],
        )
        self.assertTrue(parser.painting_holding)
        self.assertEqual(
            [gallery.get("data-category") for gallery in parser.galleries],
            ["photography"],
        )
        self.assertNotIn("Hidden Fixture Work", body.decode("utf-8"))

        self.assertEqual(
            [button["data-full"] for button in parser.lightbox_buttons],
            [work["image"] for work in self.expected_photography],
        )

        for image in parser.images:
            self.assertTrue(image.get("alt", "").strip())
            self.assertTrue(image.get("src", "").startswith("/assets/images/works/"))

        for button in parser.lightbox_buttons:
            self.assertTrue(button.get("aria-label", "").strip())

    def test_every_gallery_image_is_served_as_an_image(self):
        _, _, body = self.fetch("/")
        parser = GalleryParser()
        parser.feed(body.decode("utf-8"))

        self.assertEqual(len(parser.images), len(self.expected_photography))
        for image in parser.images:
            status, headers, image_body = self.fetch(image["src"])
            self.assertEqual(status, 200)
            self.assertTrue(headers.get_content_type().startswith("image/"))
            self.assertGreater(len(image_body), 10_000)

    def test_public_photographs_do_not_expose_exif_metadata(self):
        image_paths = sorted(
            path
            for path in (REPO_ROOT / "assets/images/works").iterdir()
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        )
        self.assertGreater(len(image_paths), 0)

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
