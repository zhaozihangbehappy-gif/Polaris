import unittest

from config_loader import load_service_config


class ConfigTest(unittest.TestCase):
    def test_service_config_loads(self):
        config = load_service_config()
        self.assertEqual(config["service"]["name"], "tiny-api")
        self.assertEqual(config["service"]["port"], 8080)
