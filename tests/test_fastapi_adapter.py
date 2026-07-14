from __future__ import annotations

import unittest

from fastapi import FastAPI

from app.backend import fastapi_adapter
from app.backend.main import create_app


class FastApiAdapterTests(unittest.TestCase):
    def test_adapter_exports_the_fastapi_contract(self) -> None:
        self.assertEqual(fastapi_adapter.BACKEND_MODE, "fastapi")
        self.assertIsInstance(fastapi_adapter.app, FastAPI)
        self.assertIs(fastapi_adapter.create_app, create_app)


if __name__ == "__main__":
    unittest.main()
