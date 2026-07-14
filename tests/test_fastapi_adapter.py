from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.backend.fastapi_adapter import BACKEND_MODE, app, create_app


class FastApiAdapterTests(unittest.TestCase):
    def test_adapter_exports_usable_fastapi_applications(self) -> None:
        self.assertEqual(BACKEND_MODE, "fastapi")
        self.assertIsInstance(app, FastAPI)

        created_app = create_app()
        self.assertIsInstance(created_app, FastAPI)
        for candidate in (app, created_app):
            with self.subTest(app=candidate):
                with TestClient(candidate) as client:
                    response = client.get("/api/v1/health")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["service"], "Insta360_HW")


if __name__ == "__main__":
    unittest.main()
