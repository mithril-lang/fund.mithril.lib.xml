import importlib, unittest
from mithril_interop import Refusal
class NamespaceTests(unittest.TestCase):
    def test_repo_and_import_namespace_agree(self):
        name="fund.mithril.lib.xml"
        api=importlib.import_module(name)
        self.assertEqual(name,api.LIBRARY_ID)
        self.assertEqual(name,api.resolve()["libraryId"])
        self.assertEqual("https://github.com/mithril-lang/"+name,api.resolve()["repository"])
        self.assertEqual("https://mithril.fund/lib/"+name,api.resolve()["source"]["@id"])
    def test_foreign_member_is_refused(self):
        api=importlib.import_module("fund.mithril.lib.xml")
        with self.assertRaises(Refusal):api.invoke("foreign-operation",{})
