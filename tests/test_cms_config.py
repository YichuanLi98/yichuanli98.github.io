import json
import pathlib
import subprocess
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ADMIN_DIR = REPO_ROOT / "admin"
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"


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


class CmsConfigTest(unittest.TestCase):
    def setUp(self):
        self.config = load_yaml(ADMIN_DIR / "config.yml")
        self.collections = {
            collection["name"]: collection
            for collection in self.config["collections"]
        }

    def test_backend_drafts_locale_and_media_are_fixed(self):
        self.assertEqual(self.config["backend"]["name"], "git-gateway")
        self.assertEqual(self.config["backend"]["branch"], "master")
        self.assertEqual(self.config["publish_mode"], "editorial_workflow")
        self.assertEqual(self.config["locale"], "zh_Hans")
        self.assertTrue(self.config["show_preview_links"])
        self.assertEqual(self.config["media_folder"], "assets/images/works")
        self.assertEqual(self.config["public_folder"], "/assets/images/works")

    def test_editor_exposes_site_photography_and_painting(self):
        self.assertEqual(
            set(self.collections),
            {"site_settings", "photography", "painting"},
        )

        settings = self.collections["site_settings"]
        self.assertFalse(settings["delete"])
        self.assertEqual(settings["files"][0]["file"], "_data/site.yml")
        self.assertEqual(
            {field["name"] for field in settings["files"][0]["fields"]},
            {"owner", "seo", "navigation", "hero", "sections", "footer", "contact"},
        )

        for name in ("photography", "painting"):
            with self.subTest(collection=name):
                collection = self.collections[name]
                self.assertEqual(collection["folder"], "_works")
                self.assertTrue(collection["create"])
                self.assertEqual(collection["filter"], {"field": "category", "value": name})
                fields = {field["name"]: field for field in collection["fields"]}
                self.assertEqual(
                    set(fields),
                    {
                        "title",
                        "category",
                        "image",
                        "alt",
                        "description",
                        "location",
                        "date",
                        "order",
                        "featured",
                        "visible",
                    },
                )
                self.assertEqual(fields["category"]["widget"], "hidden")
                self.assertEqual(fields["category"]["default"], name)
                self.assertFalse(fields["date"]["required"])

    def test_admin_shell_pins_dependencies_and_registers_previews(self):
        shell = (ADMIN_DIR / "index.html").read_text(encoding="utf-8")
        preview = (ADMIN_DIR / "preview.js").read_text(encoding="utf-8")

        self.assertIn("decap-cms@3.8.3", shell)
        self.assertIn("netlify-identity-widget@1.9.2", shell)
        for name in ("site_settings", "photography", "painting"):
            self.assertIn(f'CMS.registerPreviewTemplate("{name}"', preview)
        self.assertIn('CMS.registerPreviewStyle("/admin/preview.css")', preview)
        self.assertIn("entry.getIn", preview)
        self.assertIn("getAsset", preview)


class AutomationContractTest(unittest.TestCase):
    def test_legacy_template_workflows_are_removed(self):
        for filename in ("bad-pr.yml", "scrape_talks.yml", "jekyll-build.yml"):
            with self.subTest(workflow=filename):
                self.assertFalse((WORKFLOW_DIR / filename).exists())

    def test_cms_drafts_are_sanitized_validated_and_reported(self):
        workflow = (WORKFLOW_DIR / "cms-draft.yml").read_text(encoding="utf-8")
        for expected in (
            "pull_request:",
            "contents: write",
            "statuses: write",
            "github.event.pull_request.head.repo.full_name == github.repository",
            "requirements-dev.txt",
            "scripts/sanitize_media.py --write",
            "scripts/validate_content.rb",
            "python3 -m unittest discover -s tests -v",
            "bundle exec jekyll build --strict_front_matter",
            "npm ci",
            "npx playwright install --with-deps chromium",
            "npm run test:browser",
            "Sanitize uploaded media",
            "git push",
            "git rev-parse HEAD",
            "content-quality",
        ):
            with self.subTest(contract=expected):
                self.assertIn(expected, workflow)

    def test_production_quality_is_read_only_on_master_and_manual_runs(self):
        workflow = (WORKFLOW_DIR / "site-quality.yml").read_text(encoding="utf-8")
        for expected in (
            "push:",
            "master",
            "workflow_dispatch:",
            "contents: read",
            "scripts/sanitize_media.py --check",
            "scripts/validate_content.rb",
            "python3 -m unittest discover -s tests -v",
            "bundle exec jekyll build --strict_front_matter",
            "npm run test:browser",
        ):
            with self.subTest(contract=expected):
                self.assertIn(expected, workflow)
        self.assertNotIn("contents: write", workflow)

    def test_netlify_builds_the_strict_jekyll_site(self):
        config = (REPO_ROOT / "netlify.toml").read_text(encoding="utf-8")
        self.assertIn('command = "bundle exec jekyll build --strict_front_matter"', config)
        self.assertIn('publish = "_site"', config)
        self.assertIn('JEKYLL_ENV = "production"', config)


if __name__ == "__main__":
    unittest.main()
