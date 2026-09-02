import unittest

from goratio.plugins import (
    KINDS,
    get_plugin,
    is_whitelisted,
    list_plugins,
    whitelisted_plugins,
)


class PluginWhitelistTests(unittest.TestCase):
    def test_builtin_plugins_are_static_whitelist(self) -> None:
        plugins = list_plugins()
        self.assertGreaterEqual(len(plugins), 5)
        for plugin in plugins:
            self.assertIn(plugin["kind"], KINDS)
            self.assertIsInstance(plugin["read_only"], bool)
            self.assertIn("entry", plugin)

    def test_protocols_and_agent_tools_are_read_only(self) -> None:
        for plugin in list_plugins(kind="protocol"):
            self.assertTrue(plugin["read_only"])
        for plugin in list_plugins(kind="agent_tool"):
            self.assertTrue(plugin["read_only"])

    def test_whitelist_does_not_admit_unknown_plugin(self) -> None:
        self.assertFalse(is_whitelisted("unknown_plugin"))
        with self.assertRaises(KeyError):
            get_plugin("unknown_plugin")

    def test_data_sources_are_not_marked_read_only(self) -> None:
        self.assertTrue(whitelisted_plugins("data_source"))
        for plugin in whitelisted_plugins("data_source"):
            self.assertFalse(plugin.read_only)


if __name__ == "__main__":
    unittest.main()
