"""Static Compose contract checks. Never invoke Docker, load dotenv, or import the app."""

import ast
import unittest
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


class DevComposeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compose: dict[str, Any] = yaml.safe_load((ROOT / "compose.yaml").read_text("utf-8"))
        cls.services = cls.compose["services"]

    def test_single_root_stack_and_opt_in_seed(self) -> None:
        self.assertNotIn("include", self.compose)
        self.assertEqual(set(self.services), {"db", "migrate", "api", "worker", "web", "seed"})
        self.assertFalse((ROOT / "infra/compose.yaml").exists())
        for name, service in self.services.items():
            self.assertEqual(service.get("profiles", []), ["seed"] if name == "seed" else [])

    def test_database_is_healthy_persistent_and_internal(self) -> None:
        db = self.services["db"]
        self.assertEqual(db["image"], "pgvector/pgvector:pg17")
        self.assertIn("postgres_data:/var/lib/postgresql/data", db["volumes"])
        self.assertIn("pg_isready", db["healthcheck"]["test"][1])
        self.assertNotIn("ports", db)
        self.assertEqual(set(self.compose["volumes"]), {"postgres_data", "app_data"})

    def test_migrations_gate_both_processes(self) -> None:
        migrate = self.services["migrate"]
        self.assertEqual(migrate["command"], ["alembic", "upgrade", "head"])
        self.assertEqual(migrate["restart"], "no")
        self.assertEqual(migrate["depends_on"]["db"]["condition"], "service_healthy")
        for name in ("api", "worker"):
            self.assertEqual(
                self.services[name]["depends_on"]["migrate"]["condition"],
                "service_completed_successfully",
            )
        self.assertNotIn("command", self.services["api"])
        self.assertEqual(self.services["worker"]["command"], ["python", "-m", "app.worker"])

    def test_shared_storage_and_explicit_dev_settings(self) -> None:
        for name in ("api", "worker", "seed"):
            service = self.services[name]
            self.assertIn("app_data:/data", service["volumes"])
            self.assertEqual(service["environment"]["STORAGE_ROOT"], "/data/storage")
            self.assertEqual(service["environment"]["ENVIRONMENT"], "development")
        for name in ("api", "worker"):
            env = self.services[name]["environment"]
            self.assertEqual(env["COOKIE_SECURE"], "false")
            self.assertEqual(env["EMBEDDING_PROVIDER"], "openai")
        urls = {
            self.services[name]["environment"]["DATABASE_URL"]
            for name in ("migrate", "api", "worker", "seed")
        }
        self.assertEqual(len(urls), 1)

    def test_provider_credentials_are_required_interpolation_only(self) -> None:
        for name in ("api", "worker"):
            env = self.services[name]["environment"]
            for key in ("CHAT_OPENAI_API_KEY", "CHAT_OPENAI_MODEL"):
                self.assertTrue(env[key].startswith("${" + key + ":?Set " + key))
            self.assertEqual(env["CHAT_OPENROUTER_API_KEY"], "${CHAT_OPENROUTER_API_KEY:-}")
            self.assertEqual(env["CHAT_FREE_MODEL_CHAIN"], "${CHAT_FREE_MODEL_CHAIN:-[]}")
        for name, service in self.services.items():
            self.assertNotIn("env_file", service)
            if name not in ("api", "worker"):
                self.assertNotIn("CHAT_OPENAI_API_KEY", service.get("environment", {}))
        seed_env = self.services["seed"]["environment"]
        self.assertEqual(seed_env["PLATFORM_STAFF_PASSWORD"], "${PLATFORM_STAFF_PASSWORD:-}")

    def test_web_proxy_and_loopback_ports(self) -> None:
        web = self.services["web"]
        self.assertEqual(web["build"]["args"]["API_PROXY_TARGET"], "http://api:8000")
        self.assertEqual(web["environment"]["API_PROXY_TARGET"], "http://api:8000")
        self.assertEqual(web["ports"], ["127.0.0.1:3000:3000"])
        self.assertEqual(self.services["api"]["ports"], ["127.0.0.1:8000:8000"])
        self.assertEqual(web["depends_on"]["api"]["condition"], "service_healthy")

    def test_build_inputs_seed_module_and_dependency_graph(self) -> None:
        for name, service in self.services.items():
            if build := service.get("build"):
                self.assertEqual(build["context"], ".")
                self.assertTrue((ROOT / build["dockerfile"]).is_file())
            for dependency in service.get("depends_on", {}):
                self.assertIn(dependency, self.services)
                self.assertNotEqual(name, dependency)
        for name in ("migrate", "api", "worker", "seed"):
            self.assertEqual(self.services[name]["image"], "saas-chats-ai-api:dev")
            self.assertEqual(self.services[name]["build"]["target"], "runtime")
        seed = self.services["seed"]
        self.assertEqual(seed["command"], ["python", "-m", "scripts.seed_dev_stack"])
        self.assertEqual(seed["restart"], "no")
        for name in ("api", "worker", "web"):
            self.assertEqual(seed["depends_on"][name]["condition"], "service_healthy")
        ast.parse((ROOT / "apps/api/scripts/seed_dev_stack.py").read_text("utf-8"))

        def visit(name: str, ancestors: set[str]) -> None:
            self.assertNotIn(name, ancestors, "Compose dependency cycle")
            for dependency in self.services[name].get("depends_on", {}):
                visit(dependency, ancestors | {name})

        for name in self.services:
            visit(name, set())


if __name__ == "__main__":
    unittest.main()
