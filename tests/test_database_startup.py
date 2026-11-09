import os
import ssl
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
_saved_environment = {
    name: os.environ.get(name)
    for name in ("FLASK_CONFIG", "MONGODB_URI", "MONGODB_DATABASE", "VERCEL")
}
os.environ.update({
    "FLASK_CONFIG": "development",
    "MONGODB_URI": "mongodb://127.0.0.1:27017/",
    "MONGODB_DATABASE": "mma_hostel_mess_test",
})
os.environ.pop("VERCEL", None)
import app as backend
for _name, _value in _saved_environment.items():
    if _value is None:
        os.environ.pop(_name, None)
    else:
        os.environ[_name] = _value


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []
        self.application_writes = 0

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))
        return options["name"]

    def index_information(self):
        return {}

    def insert_one(self, document):
        self.application_writes += 1
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id="inserted")

    def find_one(self, query):
        return next(
            (document for document in self.documents if document.get("id") == query["id"]),
            None,
        )


class DatabaseStartupTests(unittest.TestCase):
    def create_test_app(self):
        app = backend.create_app("testing")
        app.extensions["mma_mongo_initialized"] = True
        return app

    def test_application_startup_does_not_run_index_migration(self):
        with patch.object(backend, "ensure_indexes") as migration:
            with patch.object(backend.mongo, "init_app") as initialize:
                app = backend.create_app("development")
        migration.assert_not_called()
        initialize.assert_not_called()
        self.assertIn("/health", {rule.rule for rule in app.url_map.iter_rules()})

    def test_database_client_is_initialized_once_with_serverless_pool_limits(self):
        class FakeDatabase:
            def command(self, name):
                self.asserted_command = name
                return {"ok": 1}

        class FakeClient:
            database = FakeDatabase()

            def __getitem__(self, _name):
                return self.database

        client = FakeClient()
        extension = SimpleNamespace(db=None, cx=client)
        initialize = Mock()
        extension.init_app = initialize
        app = backend.create_app("testing")
        with patch.object(backend, "mongo", extension):
            test_client = app.test_client()
            first = test_client.get("/health")
            second = test_client.get("/health")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        initialize.assert_called_once()
        options = initialize.call_args.kwargs
        self.assertFalse(options["connect"])
        self.assertEqual(options["maxPoolSize"], 10)
        self.assertEqual(options["minPoolSize"], 0)
        self.assertEqual(options["maxIdleTimeMS"], 30000)
        self.assertEqual(options["tlsCAFile"], backend.certifi.where())

    def test_admin_entries_page_keeps_two_day_view_and_removes_duplicate_reports(self):
        app = self.create_test_app()
        response = app.test_client().get("/admin")
        self.assertEqual(response.status_code, 200)
        markup = response.get_data(as_text=True)
        self.assertIn('id="entriesBody"', markup)
        self.assertIn("No-Food Requests", markup)
        for obsolete in (
            'id="entryDateFilter"',
            'id="entryDateReport"',
            'id="entryMonthFilter"',
            'id="entryMonthReport"',
            'id="entriesTotals"',
            "Monthly Mess Entries",
        ):
            self.assertNotIn(obsolete, markup)

        frontend = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        self.assertIn("entryTodayDateFilter", frontend)
        self.assertIn("entryTomorrowDateFilter", frontend)
        self.assertIn('html[data-page="admin"]{color-scheme:light;}', styles)
        self.assertIn('html[data-page="admin"][data-theme="dark"]{color-scheme:dark;}', styles)
        self.assertIn("@media(max-width:600px)", styles)

    def test_index_migration_preserves_existing_index_definitions(self):
        collections = {}

        def collection_for(name):
            return collections.setdefault(name, FakeCollection())

        with patch.object(backend, "get_collection", side_effect=collection_for):
            backend.ensure_indexes(backend.app)

        created = [
            (name, keys, options)
            for name, collection in collections.items()
            for keys, options in collection.indexes
        ]
        self.assertEqual(len(created), 12)
        definitions = {options["name"]: (name, keys, options) for name, keys, options in created}
        self.assertEqual(
            {options["name"] for _, _, options in created},
            {
                "bill_user_month_unique",
                "bill_draft_user_month_unique",
                "general_settings_key_unique",
                "user_date_v2_unique",
                "entry_date_updated",
                "meal_record_date_updated",
                "meal_cancellation_date_meal_unique",
                "notification_dedupe_unique",
                "cancellation_adjustment_dedupe_unique",
                "no_food_user_date_meal_unique",
                "no_food_status_date_requested",
            },
        )
        self.assertEqual(
            sum(options["name"] == "user_date_v2_unique" for _, _, options in created),
            2,
        )
        self.assertTrue(definitions["bill_user_month_unique"][2]["unique"])
        self.assertEqual(
            definitions["user_date_v2_unique"][2]["partialFilterExpression"],
            {"writeVersion": 2},
        )
        self.assertEqual(
            definitions["notification_dedupe_unique"][2]["partialFilterExpression"],
            {"dedupeKey": {"$type": "string"}},
        )
        self.assertEqual(sum(collection.application_writes for collection in collections.values()), 0)

    def test_explicit_migration_command_pings_then_runs_indexes(self):
        calls = []

        class FakeDatabase:
            def command(self, name):
                calls.append(("command", name))
                return {"ok": 1}

        app = self.create_test_app()
        with patch.object(backend, "mongo", SimpleNamespace(db=FakeDatabase())):
            with patch.object(backend, "ensure_indexes") as migration:
                result = app.test_cli_runner().invoke(args=["ensure-indexes"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(calls, [("command", "ping")])
        migration.assert_called_once_with(app)

    def test_health_reports_ping_result_and_tls_failure_category(self):
        class FakeDatabase:
            def __init__(self, error=None):
                self.error = error

            def command(self, _name):
                if self.error:
                    raise self.error
                return {"ok": 1}

        app = self.create_test_app()
        with patch.object(backend, "mongo", SimpleNamespace(db=FakeDatabase())):
            response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["application"], "available")
        self.assertEqual(response.json["database"], "connected")
        self.assertIsNone(response.json["connection_failure_category"])

        from pymongo.errors import ServerSelectionTimeoutError

        error = ServerSelectionTimeoutError("TLSV1_ALERT_INTERNAL_ERROR")
        with patch.object(
            backend,
            "mongo",
            SimpleNamespace(db=FakeDatabase(error)),
        ):
            response = app.test_client().get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["database"], "disconnected")
        self.assertEqual(response.json["connection_failure_category"], "tls_handshake")
        self.assertNotIn("TLSV1_ALERT_INTERNAL_ERROR", response.get_data(as_text=True))

    def test_database_connection_failure_returns_503_for_api_requests(self):
        from pymongo.errors import ServerSelectionTimeoutError

        class FakeDatabase:
            def __getitem__(self, _name):
                raise ServerSelectionTimeoutError("temporary network failure")

        app = self.create_test_app()
        with patch.object(backend, "mongo", SimpleNamespace(db=FakeDatabase())):
            response = app.test_client().post(
                "/api/auth/login",
                json={"uid": "student-1", "pw": "test-password"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["database"], "disconnected")
        self.assertEqual(
            response.json["connection_failure_category"],
            "server_selection_timeout",
        )

    def test_srv_dns_initialization_failure_returns_503(self):
        from pymongo.errors import ConfigurationError

        app = backend.create_app("testing")
        with patch.object(
            backend.mongo,
            "init_app",
            side_effect=ConfigurationError("SRV DNS lookup failed"),
        ):
            client = app.test_client()
            page_response = client.get("/")
            response = client.get("/health")
        self.assertEqual(page_response.status_code, 200)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["database"], "disconnected")
        self.assertEqual(response.json["connection_failure_category"], "srv_dns_failure")

    def test_login_preserves_authentication_and_session_behavior(self):
        from werkzeug.security import generate_password_hash

        user_data = {
            "id": "student-1",
            "name": "Student",
            "role": "student",
            "status": "active",
            "password_hash": generate_password_hash("test-password"),
            "auth_version": 2,
        }
        app = self.create_test_app()
        client = app.test_client()
        with patch.object(backend, "get_user_by_identity", return_value=user_data):
            response = client.post(
                "/api/auth/login",
                json={"uid": "student-1", "pw": "test-password"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["success"])
        with client.session_transaction() as browser_session:
            self.assertEqual(browser_session["auth_version"], 2)

    def test_database_helpers_read_and_write_without_touching_a_real_database(self):
        collection = FakeCollection()
        with patch.object(backend, "get_collection", return_value=collection):
            inserted = backend.create_user({
                "id": "student-1",
                "email": "STUDENT@example.test",
                "phone": "+1 (555) 010-2000",
                "password": "test-password",
            })
            user = backend.get_user("student-1")

        self.assertEqual(inserted.inserted_id, "inserted")
        self.assertEqual(user["email"], "student@example.test")
        self.assertEqual(user["phone"], "15550102000")
        self.assertNotIn("password", user)
        self.assertTrue(backend.check_password_hash(user["password_hash"], "test-password"))
        self.assertEqual(collection.application_writes, 1)

    def test_certifi_bundle_and_production_tls_configuration(self):
        context = ssl.create_default_context(cafile=backend.certifi.where())
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertTrue(backend._validate_mongodb_uri(
            "mongodb://127.0.0.1:27017/db?tls=true",
            is_production=True,
        ))
        for uri in (
            "mongodb://127.0.0.1:27017/db?tlsInsecure=true",
            "mongodb://127.0.0.1:27017/db?tlsAllowInvalidCertificates=true",
            "mongodb://127.0.0.1:27017/db?tls=false",
        ):
            with self.assertRaises(ValueError):
                backend._validate_mongodb_uri(uri, is_production=False)

    def test_vercel_entrypoint_requires_and_uses_production_config(self):
        environment = os.environ.copy()
        environment.update({
            "VERCEL": "1",
            "FLASK_CONFIG": "production",
            "FLASK_SECRET_KEY": "Vercel-production-secret-unique-2026!abc",
            "FRONTEND_ORIGIN": "https://frontend.example.test",
            "MONGODB_URI": "mongodb+srv://does-not-exist.invalid/",
            "MONGODB_DATABASE": "mma_hostel_mess_test",
        })
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import app; assert app.app.config['DEBUG'] is False; print('production')",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("production", result.stdout)

        environment.pop("FLASK_CONFIG")
        result = subprocess.run(
            [sys.executable, "-c", "import app"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set FLASK_CONFIG=production", result.stderr)


if __name__ == "__main__":
    unittest.main()
