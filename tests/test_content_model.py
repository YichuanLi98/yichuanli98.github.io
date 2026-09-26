import json
import pathlib
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SITE_PATH = REPO_ROOT / "_data" / "site.yml"
WORKS_DIR = REPO_ROOT / "_works"
VALIDATOR = REPO_ROOT / "scripts" / "validate_content.rb"


def load_yaml(path):
    ruby = textwrap.dedent(
        """
        require "date"
        require "json"
        require "yaml"
        value = YAML.safe_load(
          File.read(ARGV.fetch(0)),
          permitted_classes: [Date],
          aliases: true
        )
        print JSON.generate(value)
        """
    )
    result = subprocess.run(
        ["ruby", "-e", ruby, str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def load_work(path):
    text = path.read_text(encoding="utf-8")
    _, front_matter, _ = text.split("---", 2)
    with tempfile.NamedTemporaryFile("w", suffix=".yml", encoding="utf-8") as handle:
        handle.write(front_matter)
        handle.flush()
        return load_yaml(pathlib.Path(handle.name))


def site_yaml(featured_work="one", photography_order=None):
    if photography_order is None:
        photography_order = ["one", "two"]
    order_block = "\n".join(f"      - {slug}" for slug in photography_order)
    return textwrap.dedent(
        """
        owner:
          name: Yichuan Li
          mark_subtitle: Visual journal
        seo:
          title: Yichuan Li — Photography & Painting
          description: Photography and painting by Yichuan Li.
        navigation:
          photography: Photography
          painting: Painting
          soon: Soon
        hero:
          eyebrow: Selected works
          heading_first: Yichuan
          heading_second: Li
          discipline: Photography & Painting
          scroll_label: View the work
          featured_work: __FEATURED_WORK__
        sections:
          photography:
            eyebrow: 01 / Photography
            heading: Light, distance, and quiet moments.
            note: Eight photographs from an ongoing visual journal.
            work_order:
        __ORDER_BLOCK__
          painting:
            eyebrow: 02 / Painting
            heading: The next collection.
            note: Paintings will join the archive soon.
            coming_soon: true
            orbit_text: Painting · Coming soon · Painting · Coming soon ·
            work_order: []
        footer:
          signature: Yichuan Li
          discipline: Photography & Painting
          back_to_top: Back to top ↑
        contact:
          email: ""
          social: []
        """
    ).lstrip().replace("__FEATURED_WORK__", featured_work).replace(
        "__ORDER_BLOCK__", order_block
    )


def work_yaml(title, *, visible=True, image=None, category="photography"):
    image = image or "/assets/images/works/fixture.jpeg"
    return textwrap.dedent(
        f"""
        ---
        title: {title}
        category: {category}
        image: {image}
        alt: Description for {title}
        description: ""
        location: ""
        visible: {str(visible).lower()}
        ---
        """
    ).lstrip()


class ContentModelTest(unittest.TestCase):
    def test_site_settings_expose_every_editor_section(self):
        site = load_yaml(SITE_PATH)
        self.assertEqual(
            set(site),
            {"owner", "seo", "navigation", "hero", "sections", "footer", "contact"},
        )
        self.assertEqual(site["owner"]["name"], "Yichuan Li")
        self.assertTrue(site["sections"]["painting"]["coming_soon"])
        self.assertEqual(site["hero"]["featured_work"], "01-paris-sunset")
        self.assertEqual(
            site["sections"]["photography"]["work_order"],
            [
                "01-paris-sunset",
                "02-louvre-night",
                "03-vaudeville-table",
                "04-gull-by-sea",
                "05-west-pier",
                "06-bell-tower",
                "07-coastal-rooftops",
                "08-birds-over-sea",
            ],
        )

    def test_eight_photographs_have_complete_unique_metadata(self):
        works = [load_work(path) for path in sorted(WORKS_DIR.glob("*.md"))]
        self.assertEqual(len(works), 8)
        self.assertEqual({work["category"] for work in works}, {"photography"})
        self.assertTrue(any(work["visible"] for work in works))
        for work in works:
            self.assertTrue(work["title"].strip())
            self.assertTrue(work["image"].startswith("/assets/images/works/"))
            self.assertTrue(work["alt"].strip())
            self.assertTrue(
                {
                    "title",
                    "category",
                    "image",
                    "alt",
                    "description",
                    "location",
                    "visible",
                }.issubset(work)
            )
            self.assertTrue(set(work).issubset({
                "title",
                "category",
                "image",
                "alt",
                "description",
                "location",
                "date",
                "visible",
            }))


class ContentValidatorTest(unittest.TestCase):
    def run_validator(self, works, site_contents=None):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            site = root / "site.yml"
            works_dir = root / "works"
            site.write_text(site_contents or site_yaml(), encoding="utf-8")
            works_dir.mkdir()
            for filename, contents in works.items():
                (works_dir / filename).write_text(contents, encoding="utf-8")
            return subprocess.run(
                ["ruby", str(VALIDATOR), "--site", str(site), "--works", str(works_dir)],
                capture_output=True,
                text=True,
            )

    def test_duplicate_site_order_is_rejected(self):
        result = self.run_validator(
            {
                "one.md": work_yaml("One"),
                "two.md": work_yaml("Two"),
            },
            site_contents=site_yaml(photography_order=["one", "one"]),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("work_order", result.stderr)

    def test_featured_work_must_name_a_visible_photograph(self):
        result = self.run_validator(
            {
                "one.md": work_yaml("One"),
                "two.md": work_yaml("Two", visible=False),
            },
            site_contents=site_yaml(featured_work="two"),
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("featured_work", result.stderr)

    def test_zero_visible_photographs_are_rejected(self):
        result = self.run_validator(
            {"one.md": work_yaml("One", visible=False)}
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("visible photograph", result.stderr)


if __name__ == "__main__":
    unittest.main()
