"""Offline source invariants for C3; no dotenv, Docker, service or DB access."""
from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeployReadinessSourceTests(unittest.TestCase):
    def test_template_has_one_blank_channel_key_entry(self) -> None:
        entries = re.findall(r"^CHANNEL_SECRET_ENCRYPTION_KEYS=(.*)$", (ROOT / ".env.production.example").read_text(encoding="utf-8"), re.M)
        self.assertEqual(entries, [""])

    def test_key_reaches_both_service_environments_and_is_required(self) -> None:
        compose = (ROOT / "compose.prod.yaml").read_text(encoding="utf-8")
        shared = compose.split("x-app-environment: &app-environment", 1)[1].split("x-logging:", 1)[0]
        self.assertIn("CHANNEL_SECRET_ENCRYPTION_KEYS: ${CHANNEL_SECRET_ENCRYPTION_KEYS:?", shared)
        api = compose.split("\n  api:", 1)[1].split("\n  worker:", 1)[0]
        worker = compose.split("\n  worker:", 1)[1].split("\n  web:", 1)[0]
        self.assertIn("environment: *app-environment", api)
        self.assertIn("<<: *app-environment", worker)
        self.assertIn('command: ["python", "-m", "app.worker"]', worker)

    def test_worker_dispatches_channels_and_schedules_health_maintenance(self) -> None:
        worker = ast.parse((ROOT / "apps/api/app/worker/__main__.py").read_text(encoding="utf-8"))
        calls = {node.func.id for node in ast.walk(worker) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertTrue({"schedule_health_polls", "sweep_unconfirmed", "execute_claimed_job"} <= calls)
        runner = ast.parse((ROOT / "apps/api/app/jobs/runner.py").read_text(encoding="utf-8"))
        compared_types = {item.value for node in ast.walk(runner) if isinstance(node, ast.Compare) for item in node.comparators if isinstance(item, ast.Constant)}
        self.assertTrue({"channel_inbound", "channel_send", "channel_health_poll"} <= compared_types)

    def test_release_chain_has_one_head_with_0022_ancestor(self) -> None:
        revisions: dict[str, str | None] = {}
        for path in (ROOT / "apps/api/alembic/versions").glob("*.py"):
            values = {}
            for statement in ast.parse(path.read_text(encoding="utf-8")).body:
                if isinstance(statement, ast.Assign):
                    names, value = statement.targets, statement.value
                elif isinstance(statement, ast.AnnAssign):
                    names, value = [statement.target], statement.value
                else:
                    continue
                for name in names:
                    if isinstance(name, ast.Name) and name.id in {"revision", "down_revision"}:
                        values[name.id] = ast.literal_eval(value)
            if "revision" in values:
                revisions[values["revision"]] = values["down_revision"]
        heads = set(revisions) - set(revisions.values())
        self.assertEqual(len(heads), 1)
        current = heads.pop()
        ancestors = []
        while current is not None:
            self.assertNotIn(current, ancestors)
            ancestors.append(current)
            current = revisions[current]
        self.assertIn("0022_knowledge_hygiene", ancestors)
        self.assertIn("0030_channel_health_poll_index", ancestors)
        self.assertIn("0031_contact_erasure", ancestors)
        self.assertLess(ancestors.index("0031_contact_erasure"), ancestors.index("0030_channel_health_poll_index"))

    def test_backup_is_checked_before_build_or_restart(self) -> None:
        script = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", script)
        self.assertIn("umask 077", script)
        self.assertIn("set -o noclobber", script)
        dump = script.index("exec pg_dump")
        nonempty = script.index('test -s "${backup_path}.partial"')
        listing = script.index("pg_restore --list")
        complete = script.index('mv -- "${backup_path}.partial" "$backup_path"')
        build = script.index('"${DC[@]}" build')
        restart = script.index('"${DC[@]}" up -d --wait --remove-orphans')
        self.assertLess(dump, nonempty)
        self.assertLess(nonempty, listing)
        self.assertLess(listing, complete)
        self.assertLess(complete, build)
        self.assertLess(build, restart)
        self.assertNotIn('|| echo "WARNING: pre-deploy backup failed"', script)
        no_database = script.split('else\n  echo "No running database', 1)[1].split('fi', 1)[0]
        self.assertIn("exit 1", no_database)

    def test_documented_events_path_matches_router(self) -> None:
        router = ast.parse((ROOT / "apps/api/app/channels/events.py").read_text(encoding="utf-8"))
        routes = {node.args[0].value for node in ast.walk(router) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "post" and node.args and isinstance(node.args[0], ast.Constant)}
        self.assertTrue(routes)
        runbook = (ROOT / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertTrue(any(route in runbook for route in routes))


if __name__ == "__main__":
    unittest.main()
