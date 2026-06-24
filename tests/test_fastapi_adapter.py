from __future__ import annotations

import unittest

from app.backend.fastapi_adapter import BACKEND_MODE, create_app


class FastApiAdapterTests(unittest.TestCase):
    def test_default_backend_mode_stays_stdlib_compatible(self) -> None:
        self.assertEqual(BACKEND_MODE, "stdlib")
        self.assertIsNone(create_app())


if __name__ == "__main__":
    unittest.main()
