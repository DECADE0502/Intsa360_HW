from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReleaseDocsTests(unittest.TestCase):
    def test_release_docs_exist_and_are_chinese(self) -> None:
        for relative, title in [
            ("docs/INSTALL.md", "安装"),
            ("docs/UPDATE.md", "更新"),
            ("docs/ROLLBACK.md", "回滚"),
        ]:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("硬件效率工具集", text)
                self.assertIn(title, text)

    def test_verify_all_script_runs_required_checks(self) -> None:
        text = (ROOT / "scripts" / "verify_all.ps1").read_text(encoding="utf-8")

        self.assertIn("unittest discover", text)
        self.assertIn("py_compile", text)
        self.assertIn("npm run build", text)
        self.assertIn("English UI text found", text)


if __name__ == "__main__":
    unittest.main()
