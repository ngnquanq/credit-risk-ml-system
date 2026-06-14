import unittest
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_kafka_channel_offsets import partition_lag
from e2e_message_parsing import extract_sk_id_curr


class PredictionMonitorParsingTest(unittest.TestCase):
    def test_extracts_plain_scoring_id(self):
        payload = {"sk_id_curr": "100001_abc", "decision": "approve"}

        self.assertEqual(extract_sk_id_curr(payload), "100001_abc")

    def test_extracts_cloudevent_data_id(self):
        payload = {
            "specversion": "1.0",
            "type": "dev.knative.scoring.response",
            "data": {"sk_id_curr": 12345},
        }

        self.assertEqual(extract_sk_id_curr(payload), "12345")

    def test_extracts_cloudevent_subject(self):
        payload = {
            "specversion": "1.0",
            "type": "dev.knative.scoring.response",
            "subject": "subject-id",
        }

        self.assertEqual(extract_sk_id_curr(payload), "subject-id")

    def test_extracts_json_string_data_id(self):
        payload = {
            "specversion": "1.0",
            "type": "dev.knative.scoring.response",
            "data": json.dumps({"sk_id_curr": "json-string-id"}),
        }

        self.assertEqual(extract_sk_id_curr(payload), "json-string-id")

    def test_extracts_base64_data_id(self):
        data = base64.b64encode(json.dumps({"sk_id_curr": "base64-id"}).encode("utf-8")).decode("ascii")
        payload = {
            "specversion": "1.0",
            "type": "dev.knative.scoring.response",
            "data_base64": data,
        }

        self.assertEqual(extract_sk_id_curr(payload), "base64-id")

    def test_extracts_nested_cdc_id(self):
        payload = {"payload": {"after": {"sk_id_curr": "nested-id"}}}

        self.assertEqual(extract_sk_id_curr(payload), "nested-id")

    def test_missing_id_returns_none(self):
        self.assertIsNone(extract_sk_id_curr({"decision": "review"}))


class KafkaChannelOffsetTest(unittest.TestCase):
    def test_effective_lag_ignores_stale_committed_offset(self):
        self.assertEqual(
            partition_lag(earliest=100, latest=125, committed=80),
            {
                "earliest": 100,
                "latest": 125,
                "committed": 80,
                "raw_lag": 45,
                "stale_lag": 20,
                "effective_lag": 25,
            },
        )

    def test_effective_lag_uses_committed_when_it_is_in_retention_window(self):
        self.assertEqual(partition_lag(earliest=100, latest=125, committed=110)["effective_lag"], 15)

    def test_missing_committed_offset_counts_only_retained_records(self):
        self.assertEqual(partition_lag(earliest=100, latest=125, committed=None)["effective_lag"], 25)


if __name__ == "__main__":
    unittest.main()
