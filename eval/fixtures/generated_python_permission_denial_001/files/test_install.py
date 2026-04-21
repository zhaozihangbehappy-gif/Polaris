import unittest

import pip_env
from installer import install_marker


class InstallModeTest(unittest.TestCase):
    def test_install_uses_user_site_packages(self):
        pip_env.configure_install_environment()
        marker = install_marker()
        self.assertIn("user-site-packages", str(marker))


if __name__ == "__main__":
    unittest.main()
