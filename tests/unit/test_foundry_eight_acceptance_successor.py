"""Offline per-read auth timing checks; no Azure or inference."""
import base64
from datetime import UTC, datetime
import json
import unittest
from unittest.mock import patch

from scripts.deployment import foundry_eight_acceptance_successor as s


def token(remaining=300, **overrides):
    claims = {"tid": s.original.rt.TENANT, "oid": s.original.rt.OPERATOR,
              "aud": "https://management.azure.com/", "exp": datetime.now(UTC).timestamp() + remaining, **overrides}
    return "synthetic." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".synthetic"


class Offline(unittest.TestCase):
    def test_consumed_zero_send_predecessor_bytes_exact(self):
        self.assertTrue(s.predecessor())
        self.assertNotEqual(s.HOME, s.original.HOME)

    def test_valid_existing_five_minute_auth_for_one_read_no_retry(self):
        client = s.FreshClient.__new__(s.FreshClient)
        client.token = None
        with patch.object(s.original, "cli", return_value={"accessToken": token()}) as cli, patch.object(
                s.original.Client, "arm", return_value={"synthetic": True}) as arm:
            self.assertEqual(client.arm(s.original.ACCOUNT), {"synthetic": True})
            self.assertEqual(cli.call_count, 1)
            self.assertEqual(arm.call_count, 1)
            self.assertIsNone(client.token)

    def test_expired_wrong_identity_wrong_audience_rejected_before_wire(self):
        for value in (token(90), token(oid="wrong"), token(tid="wrong"), token(aud="wrong")):
            client = s.FreshClient.__new__(s.FreshClient)
            with patch.object(s.original, "cli", return_value={"accessToken": value}), patch.object(
                    s.original.Client, "arm") as arm, self.assertRaises(s.original.AcceptanceError):
                client.arm(s.original.ACCOUNT)
            arm.assert_not_called()

    def test_wire_failure_clears_token_no_retry(self):
        client = s.FreshClient.__new__(s.FreshClient)
        with patch.object(s.original, "cli", return_value={"accessToken": token()}), patch.object(
                s.original.Client, "arm", side_effect=ValueError("synthetic")) as arm, self.assertRaises(ValueError):
            client.arm(s.original.ACCOUNT)
        self.assertEqual(arm.call_count, 1)
        self.assertIsNone(client.token)


if __name__ == "__main__":
    unittest.main()