import os
import unittest
from unittest.mock import patch

from backend.api import app


class TestGoogleAuthentication(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-session-secret",
            SESSION_COOKIE_SECURE=False,
        )
        self.client = app.test_client()

    def tearDown(self):
        app.config.update(
            SECRET_KEY=os.getenv("SESSION_SECRET"),
            SESSION_COOKIE_SECURE=True,
        )

    def test_login_page_offers_google_sign_in(self):
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Continue with Google", response.data)
        self.assertIn(b"/auth/google", response.data)

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_protected_api_returns_json_401(self):
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["status"], "unauthorized")

    def test_google_login_fails_closed_without_server_configuration(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CLIENT_ID", None)
            os.environ.pop("GOOGLE_CLIENT_SECRET", None)
            response = self.client.get("/auth/google")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"not configured", response.data)

    def test_callback_rejects_google_error_without_creating_session(self):
        response = self.client.get("/auth/google/callback?error=access_denied")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        with self.client.session_transaction() as session:
            self.assertNotIn("user", session)

    def test_callback_error_is_not_500_without_session_secret(self):
        app.secret_key = None
        response = self.client.get("/auth/google/callback?error=access_denied")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    @patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
        },
    )
    @patch("backend.api.oauth.google.authorize_access_token")
    def test_verified_callback_creates_session_and_redirects(self, authorize):
        authorize.return_value = {
            "userinfo": {
                "sub": "google-subject-123",
                "email": "trader@example.com",
                "email_verified": True,
                "name": "Demo Trader",
            }
        }
        with self.client.session_transaction() as session:
            session["oauth_next"] = "/dashboard"

        response = self.client.get("/auth/google/callback")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/dashboard"))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user"]["email"], "trader@example.com")
            self.assertTrue(session.permanent)

        dashboard = self.client.get("/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Authenticated", dashboard.data)

    def test_logout_clears_session(self):
        with self.client.session_transaction() as session:
            session["user"] = {"sub": "subject", "email": "trader@example.com"}

        response = self.client.get("/auth/logout")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/login"))
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


if __name__ == "__main__":
    unittest.main()
