"""Which database is the primary (brain.md rule 97): Supabase unless PRIMARY=neon, the same answer in the
jobs, the Node writer, the site, the schema lane and the mirror."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import nbt  # noqa: E402

NEON = "postgresql://u:p@ep-x-pooler.us-east-2.aws.neon.tech/neondb"
SUPA = "postgresql://postgres.abc:p@aws-0-x.pooler.supabase.com:5432/postgres"


class ThePrimary(unittest.TestCase):
    def test_supabase_unless_told_otherwise(self):
        env = {"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA}
        self.assertEqual(nbt.primary_choice(env), ("SUPABASE_DATABASE_URL", SUPA))
        self.assertEqual(nbt.primary_choice({**env, "PRIMARY": "neon"}), ("DATABASE_URL", NEON))
        self.assertEqual(nbt.primary_choice({**env, "PRIMARY": "Supabase"}), ("SUPABASE_DATABASE_URL", SUPA))
        # No Supabase configured: DATABASE_URL, as it always was.
        self.assertEqual(nbt.primary_choice({"DATABASE_URL": NEON}), ("DATABASE_URL", NEON))

    def test_neon_is_the_standby_when_supabase_is_the_primary(self):
        env = {"DATABASE_URL": NEON, "SUPABASE_DATABASE_URL": SUPA}
        self.assertEqual(nbt.standby_url(SUPA, env), ("DATABASE_URL", NEON))
        self.assertEqual(nbt.standby_url(NEON, env), ("SUPABASE_DATABASE_URL", SUPA))
        self.assertIsNone(nbt.standby_url(SUPA, {**env, "WRITE_FAILOVER": "off"}))
        self.assertIsNone(nbt.standby_url(SUPA, {"SUPABASE_DATABASE_URL": SUPA}))

    def test_every_layer_states_the_same_rule(self):
        writer = (ROOT / "tools" / "writer.mjs").read_text(encoding="utf-8")
        self.assertIn('(env.PRIMARY ?? "supabase").trim().toLowerCase() === "supabase" && supabase', writer)
        self.assertIn('const primary = primaryChoice(env).url;', writer)
        site = (ROOT / "lib" / "db.ts").read_text(encoding="utf-8")
        self.assertIn('(env.PRIMARY ?? "supabase").trim().toLowerCase() === "supabase" && supabase', site)
        self.assertIn("const url = primaryUrl();", site)
        for tool in ("standby_parity.py", "logic_audit.py"):
            src = (ROOT / "tools" / tool).read_text(encoding="utf-8")
            self.assertIn('("PRIMARY") or "supabase").strip().lower() == "supabase" and supabase', src, tool)
        for wf in ("schema.yml", "cron-mirror.yml"):
            src = (ROOT / ".github" / "workflows" / wf).read_text(encoding="utf-8")
            self.assertIn('${PRIMARY_VAR:-supabase}', src, wf)
        mirror = (ROOT / ".github" / "workflows" / "cron-mirror.yml").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r'--from-env "\$\{\{ steps\.targets\.outputs\.from \}\}"', mirror)), 3)
        self.assertNotIn("--from-env DATABASE_URL ", mirror)

    def test_reconcile_copies_back_into_the_chosen_primary(self):
        src = (ROOT / "jobs" / "reconcile.py").read_text(encoding="utf-8")
        self.assertIn("primary_name, primary_url = primary_choice()", src)
        self.assertEqual(src.count('"--to-env", primary_name'), 2)


if __name__ == "__main__":
    unittest.main()
