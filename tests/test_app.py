import unittest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash

import app as medical_app


class MedicalSystemTestCase(unittest.TestCase):
    def setUp(self):
        medical_app.app.config["TESTING"] = True
        medical_app.app.config["SECRET_KEY"] = "test-secret-key"
        self.client = medical_app.app.test_client()

    # =========================================================================
    # 1. AUTHENTICATION & ACCESS CONTROL TESTS
    # =========================================================================

    def test_anonymous_redirected_to_login(self):
        """Anonymous requests to protected endpoints must redirect to /login."""
        protected_urls = ["/", "/admin", "/doktor", "/sestra", "/users", "/patients", "/appointments"]
        for url in protected_urls:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 302, f"Expected redirect for {url}")
            self.assertIn("/login", response.headers["Location"], f"Expected redirect to /login for {url}")

    def test_login_page_renders(self):
        """Login page must render with HTTP 200."""
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Prijava", response.data)

    def test_register_page_renders(self):
        """Registration page must render with HTTP 200."""
        response = self.client.get("/register")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Registracija", response.data)

    def test_logout_clears_session(self):
        """Logging out must clear user session and redirect to /login."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.get("/logout", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

        with self.client.session_transaction() as sess:
            self.assertNotIn("user_id", sess)
            self.assertNotIn("role", sess)

    # =========================================================================
    # 2. ROLE-BASED ACCESS CONTROL (RBAC) TESTS
    # =========================================================================

    def test_nurse_cannot_access_admin_or_users(self):
        """Nurses must not access /admin or /users."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "sestra"
            sess["ime"] = "Sestra Test"

        for url in ["/admin", "/users"]:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_doctor_cannot_access_admin_or_users(self):
        """Doctors must not access /admin or /users."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        for url in ["/admin", "/users"]:
            response = self.client.get(url, follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login", response.headers["Location"])

    def test_admin_cannot_delete_own_account(self):
        """An administrator cannot delete their own active account."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.get("/users/delete/1", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users", response.headers["Location"])

    # =========================================================================
    # 3. INPUT VALIDATION TESTS
    # =========================================================================

    def test_patient_add_validation_empty_names(self):
        """Adding a patient with empty first/last name must be rejected."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        response = self.client.post("/patients/add", data={
            "ime": "",
            "prezime": "",
            "jmbg": "1234567890123",
            "telefon": "060123456"
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/patients/add", response.headers["Location"])

    def test_patient_add_validation_invalid_jmbg(self):
        """Adding a patient with invalid JMBG (not 13 digits) must be rejected."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["role"] = "admin"
            sess["ime"] = "Admin Test"

        # Less than 13 digits
        response = self.client.post("/patients/add", data={
            "ime": "Petar",
            "prezime": "Petrovic",
            "jmbg": "12345",
            "telefon": "060123456"
        }, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/patients/add", response.headers["Location"])

        # Non-digits
        response2 = self.client.post("/patients/add", data={
            "ime": "Petar",
            "prezime": "Petrovic",
            "jmbg": "123456789012A",
            "telefon": "060123456"
        }, follow_redirects=False)
        self.assertEqual(response2.status_code, 302)
        self.assertIn("/patients/add", response2.headers["Location"])

    def test_appointment_add_validation_empty_datum(self):
        """Scheduling an appointment without datetime must be rejected."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["role"] = "sestra"
            sess["ime"] = "Sestra Test"

        response = self.client.post("/appointments/add", data={
            "patient_id": "1",
            "doctor_id": "3",
            "datum": ""
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/appointments/add", response.headers["Location"])

    # =========================================================================
    # 4. MEDICAL RECORD OWNERSHIP & INTEGRITY TESTS
    # =========================================================================

    @patch("app.get_db_connection")
    def test_doctor_cannot_edit_another_doctors_medical_record(self, mock_db_conn):
        """A doctor cannot edit a medical record authored by another doctor."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        # Record belongs to doctor_id = 99
        mock_cursor.fetchone.return_value = {
            "id": 1,
            "patient_id": 10,
            "doctor_id": 99,
            "dijagnoza": "Prehlada",
            "terapija": "Caj"
        }

        # Current doctor is user_id = 3
        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.get("/medical/edit/1", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/medical/10", response.headers["Location"])

    @patch("app.get_db_connection")
    def test_doctor_cannot_delete_another_doctors_medical_record(self, mock_db_conn):
        """A doctor cannot delete a medical record authored by another doctor."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_db_conn.return_value = mock_conn

        mock_cursor.fetchone.return_value = {
            "id": 1,
            "patient_id": 10,
            "doctor_id": 99,
            "dijagnoza": "Prehlada",
            "terapija": "Caj"
        }

        with self.client.session_transaction() as sess:
            sess["user_id"] = 3
            sess["role"] = "doktor"
            sess["ime"] = "Dr Test"

        response = self.client.get("/medical/delete/1", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/medical/10", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
