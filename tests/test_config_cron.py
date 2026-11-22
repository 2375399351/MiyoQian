import tempfile
import unittest
from pathlib import Path

from miyouqian.core.config import load_config


class CronConfigMigrationTests(unittest.TestCase):
    def test_legacy_time_is_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(
                'schedule:\n  enable: true\n  time: "07:35"\n  jitter_minutes: 20\n',
                encoding="utf-8",
            )
            config = load_config(config_path)
            self.assertEqual(config["schedule"]["cron"], "35 7 * * *")
            self.assertNotIn("time", config["schedule"])
            self.assertEqual(config["schedule"]["jitter_minutes"], 20)


if __name__ == "__main__":
    unittest.main()
