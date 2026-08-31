from __future__ import annotations

import re
from pathlib import Path
import tomllib
import unittest

from PySide6.QtGui import QImage, QImageReader

from streamer_console import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\]\((?!https?://|mailto:|#)([^)#]+)(?:#[^)]*)?\)")
HTML_IMAGE = re.compile(r'<img[^>]+src="(?!https?://)([^"]+)"', re.IGNORECASE)


class RepositoryQualityTests(unittest.TestCase):
    def test_project_version_is_consistent(self) -> None:
        project = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertEqual(project["project"]["version"], __version__)
        self.assertEqual(__version__, "1.1.0")

    def test_local_documentation_links_resolve(self) -> None:
        missing: list[str] = []
        markdown_files = [PROJECT_ROOT / "README.md"]
        markdown_files.extend(PROJECT_ROOT.glob("*.md"))
        markdown_files.extend((PROJECT_ROOT / "docs").rglob("*.md"))
        for document in sorted(set(markdown_files)):
            content = document.read_text(encoding="utf-8")
            targets = list(MARKDOWN_LINK.findall(content))
            targets.extend(HTML_IMAGE.findall(content))
            for raw_target in targets:
                target = raw_target.strip().strip("<>")
                resolved = (document.parent / target).resolve()
                if not resolved.exists():
                    missing.append(
                        f"{document.relative_to(PROJECT_ROOT)} -> {target}"
                    )

        self.assertEqual(missing, [])

    def test_public_preview_assets_are_bounded_and_metadata_free(self) -> None:
        expected = {
            "streamer-console-preview.png": (1080, 1920),
            "social-preview.png": (1280, 640),
        }
        for name, dimensions in expected.items():
            with self.subTest(name=name):
                path = PROJECT_ROOT / "docs" / "images" / name
                image = QImage(str(path))
                reader = QImageReader(str(path))
                self.assertFalse(image.isNull())
                self.assertEqual((image.width(), image.height()), dimensions)
                self.assertLess(path.stat().st_size, 1_000_000)
                self.assertEqual(reader.textKeys(), [])

    def test_ci_actions_are_pinned_to_full_commit_shas(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        action_uses = re.findall(r"uses:\s+[^@\s]+@([^\s]+)", workflow)

        self.assertGreaterEqual(len(action_uses), 2)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_uses))


if __name__ == "__main__":
    unittest.main()
