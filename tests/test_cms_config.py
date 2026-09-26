import json
import os
import pathlib
import re
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

    def test_media_uploads_strip_metadata_before_storage(self):
        self.assertEqual(
            self.config.get("media_processing"),
            {
                "enabled": True,
                "strip_metadata": True,
            },
        )

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

        settings_fields = {
            field["name"]: field for field in settings["files"][0]["fields"]
        }
        hero_fields = {
            field["name"]: field for field in settings_fields["hero"]["fields"]
        }
        self.assertEqual(hero_fields["featured_work"]["widget"], "relation")
        self.assertEqual(hero_fields["featured_work"]["collection"], "photography")
        self.assertEqual(hero_fields["featured_work"]["value_field"], "{{slug}}")

        section_fields = {
            field["name"]: field for field in settings_fields["sections"]["fields"]
        }
        for name in ("photography", "painting"):
            category_fields = {
                field["name"]: field for field in section_fields[name]["fields"]
            }
            order = category_fields["work_order"]
            self.assertEqual(order["widget"], "list")
            self.assertEqual(order["field"]["widget"], "relation")
            self.assertEqual(order["field"]["collection"], name)
            self.assertEqual(order["field"]["value_field"], "{{slug}}")

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
                        "visible",
                    },
                )
                self.assertEqual(fields["category"]["widget"], "hidden")
                self.assertEqual(fields["category"]["default"], name)
                self.assertFalse(fields["date"]["required"])

    def test_admin_shell_pins_dependencies_and_registers_previews(self):
        shell = (ADMIN_DIR / "index.html").read_text(encoding="utf-8")
        preview = (ADMIN_DIR / "preview.js").read_text(encoding="utf-8")

        self.assertIn("decap-cms@3.16.3", shell)
        self.assertIn("netlify-identity-widget@1.9.2", shell)
        for name in ("site", "photography", "painting"):
            self.assertIn(f'CMS.registerPreviewTemplate("{name}"', preview)
        self.assertIn('CMS.registerPreviewStyle("/admin/preview.css")', preview)
        self.assertIn("entry.getIn", preview)
        self.assertIn("getAsset", preview)
        self.assertNotIn("React.createElement", preview)

        smoke_test = textwrap.dedent(
            """
            const registrations = [];
            global.window = { h: (...args) => ({ args }) };
            global.CMS = {
              registerPreviewStyle: () => {},
              registerPreviewTemplate: (name, component) => {
                component({
                  entry: { getIn: () => undefined },
                  getAsset: () => ({ toString: () => "" }),
                });
                registrations.push(name);
              },
            };
            require(process.argv[1]);
            if (registrations.join(",") !== "site,photography,painting") {
              throw new Error(`unexpected preview registrations: ${registrations}`);
            }
            """
        )
        subprocess.run(
            ["node", "-e", smoke_test, str(ADMIN_DIR / "preview.js")],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ,
        )


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
        production_command = re.search(
            r'(?ms)^\[build\]\s+command = "(.+?)"$', config
        ).group(1)
        preview_command = re.search(
            r'(?ms)^\[context\.deploy-preview\]\s+command = "(.+?)"$', config
        ).group(1)
        command = (
            'command = "python3 scripts/sanitize_media.py --write assets/images/works '
            "&& ruby scripts/validate_content.rb --site _data/site.yml --works _works "
            '&& bundle exec jekyll build --strict_front_matter"'
        )
        self.assertIn(command, config)
        self.assertNotIn(
            "scripts/configure_cms_branch.py",
            production_command,
        )
        self.assertIn(
            "python3 scripts/configure_cms_branch.py --config _site/admin/config.yml --branch ",
            preview_command,
        )
        self.assertIn("$HEAD", preview_command)
        self.assertIn('publish = "_site"', config)
        self.assertIn('JEKYLL_ENV = "production"', config)
        self.assertIn('for = "/*"', config)
        self.assertIn('X-Robots-Tag = "noindex, nofollow"', config)

    def test_ruby_dependencies_are_locked_for_local_and_linux_builds(self):
        lockfile = (REPO_ROOT / "Gemfile.lock").read_text(encoding="utf-8")
        ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("github-pages (232)", lockfile)
        self.assertIn("arm64-darwin", lockfile)
        self.assertIn("x86_64-linux", lockfile)
        self.assertNotIn("Gemfile.lock", ignored)


if __name__ == "__main__":
    unittest.main()
