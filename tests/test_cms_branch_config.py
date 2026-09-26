import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "configure_cms_branch.py"


class CmsBranchConfigTest(unittest.TestCase):
    def test_rewrites_only_the_git_gateway_backend_branch(self):
        source = textwrap.dedent(
            """\
            backend:
              name: git-gateway
              branch: master

            editorial:
              branch: leave-this-alone
            """
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            config = pathlib.Path(temporary_directory) / "config.yml"
            config.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--config",
                    str(config),
                    "--branch",
                    "feature/visual-editor",
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                config.read_text(encoding="utf-8"),
                source.replace(
                    "  branch: master",
                    "  branch: feature/visual-editor",
                    1,
                ),
            )

    def test_rejects_a_branch_that_could_inject_yaml(self):
        source = "backend:\n  name: git-gateway\n  branch: master\n"

        with tempfile.TemporaryDirectory() as temporary_directory:
            config = pathlib.Path(temporary_directory) / "config.yml"
            config.write_text(source, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--config",
                    str(config),
                    "--branch",
                    "feature/preview\nmedia_folder: stolen",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid branch", result.stderr)
            self.assertEqual(config.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    unittest.main()
