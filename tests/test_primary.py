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


class DiallingTheStandby(unittest.TestCase):
    """Neon's pooler publishes AAAA as well as A, and GitHub's runners have no IPv6 route. A resolver
    that answers AAAA first stranded the mirror on "Network is unreachable", which reads like the
    database is down when it is only unreachable. `_connect` pins an IPv4 address with `hostaddr`."""

    def dial(self, addrs, outcomes):
        """Run _connect against a fake resolver and a fake psycopg, returning the URLs it dialled."""
        seen = []

        def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            if family != nbt.socket.AF_INET:
                raise OSError("fake resolver is asked only for A records")
            if not addrs:
                raise OSError("no A record")
            return [(family, type, proto, "", (a, 0)) for a in addrs]

        class Conn:
            def execute(self, *_a, **_k):
                return None

        def connect(url, **_kw):
            seen.append(url)
            out = outcomes.pop(0)
            if out is not None:
                raise out
            return Conn()

        real_gai, real_connect = nbt.socket.getaddrinfo, nbt.psycopg.connect
        nbt.socket.getaddrinfo, nbt.psycopg.connect = getaddrinfo, connect
        try:
            conn = nbt._connect(NEON)
        finally:
            nbt.socket.getaddrinfo, nbt.psycopg.connect = real_gai, real_connect
        return seen, conn

    def test_it_pins_ipv4_and_never_dials_the_ipv6(self):
        seen, _ = self.dial(["203.0.113.7"], [None])
        self.assertEqual(len(seen), 1)
        self.assertIn("hostaddr=203.0.113.7", seen[0])
        # the name stays in the URL, so SNI routing and certificate verification are unchanged
        self.assertIn("ep-x-pooler.us-east-2.aws.neon.tech", seen[0])
        self.assertNotIn("channel_binding", seen[0])

    def test_an_unroutable_address_moves_on_to_the_next(self):
        unreachable = nbt.psycopg.OperationalError(
            'connection to server at "2600:1f16::1", port 5432 failed: Network is unreachable'
        )
        seen, _ = self.dial(["203.0.113.7", "203.0.113.8"], [unreachable, None])
        self.assertEqual([u.split("hostaddr=")[1] for u in seen], ["203.0.113.7", "203.0.113.8"])

    def test_a_refusal_is_an_answer_and_is_not_retried(self):
        quota = nbt.psycopg.OperationalError(
            "ERROR:  Your account or project has exceeded the quota. Upgrade your plan"
        )
        with self.assertRaises(nbt.psycopg.OperationalError):
            self.dial(["203.0.113.7", "203.0.113.8"], [quota, None])

    def test_a_host_with_no_a_record_is_dialled_as_before(self):
        seen, _ = self.dial([], [None])
        self.assertEqual(len(seen), 1)
        self.assertNotIn("hostaddr", seen[0])


if __name__ == "__main__":
    unittest.main()
