import copy
import json
from pathlib import Path
import tempfile
import unittest
from mithril_interop import Refusal
from mithril_xml import native_xml as xml

ROOT = Path(__file__).resolve().parents[1]
MSDL = (ROOT / "examples/msdl-relief.xml").read_bytes()

class XMLTests(unittest.TestCase):
    def artifact(self):
        return xml.import_xml(MSDL, "msdl", "SISO-STD-007-2008")

    def test_byte_exact_roundtrip_unknown_extensions_comments_and_non_utf8(self):
        data = MSDL.replace(b"<Environment/>", b"<Environment><!--keep--><x:unknown xmlns:x='urn:extension'>a&amp;b</x:unknown></Environment>")
        for raw in [data, data.decode().replace('encoding="UTF-8"', 'encoding="UTF-16"').encode("utf-16")]:
            self.assertEqual(raw, xml.export_xml(xml.import_xml(raw, "msdl", "2008")))

    def test_dtd_entities_malformed_wrong_namespace_and_digest_are_refused(self):
        for data in [b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>',
                     b"<broken>", MSDL.replace(b"urn:sisostds:scenario:military:data:draft:msdl:1", b"urn:wrong")]:
            with self.assertRaises(Refusal):
                xml.import_xml(data, "msdl", "2008")
        a = self.artifact()
        a["sha256"] = "0" * 64
        with self.assertRaises(Refusal):
            xml.export_xml(a)

    def test_projection_reports_unmapped_data_and_keeps_archive(self):
        a = self.artifact()
        profile = json.loads((ROOT / "examples/msdl-profile.json").read_text())
        result = xml.project(a, profile)
        self.assertEqual(1, result["receipt"]["mappedRecords"])
        self.assertTrue(result["receipt"]["unmappedPaths"])
        self.assertEqual(MSDL, xml.export_xml(result["native"]))
        self.assertEqual("Unit", result["model"]["records"][0]["type"])
        with self.assertRaises(Refusal):
            xml.project(a, profile, strict=True)
        profile["version"] = "different-version"
        with self.assertRaises(Refusal):
            xml.project(a, profile)

    def test_guarded_native_edit_and_stale_patch(self):
        patch = {"xpath": "//m:Unit/m:Name", "namespaces": {"m": xml.ROOTS["msdl"].copy().pop()[1:].split("}")[0]},
                 "attribute": None, "before": "Relief team", "after": "Team A & B"}
        result = xml.patch_xml(self.artifact(), [patch])
        self.assertIn(b"Team A &amp; B", xml.export_xml(result["artifact"]))
        self.assertFalse(result["receipt"]["byteIdentical"])
        with self.assertRaises(Refusal):
            xml.patch_xml(result["artifact"], [patch])

    def test_pinned_schema_import_closure_and_xsd11_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            data = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:fixture" xmlns="urn:fixture" elementFormDefault="qualified"><xs:include schemaLocation="types.xsd"/><xs:element name="Root" type="Checked"/></xs:schema>'''
            types = b'''<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" targetNamespace="urn:fixture" xmlns="urn:fixture"><xs:complexType name="Checked"><xs:attribute name="n" type="xs:integer" use="required"/><xs:assert test="@n gt 0"/></xs:complexType></xs:schema>'''
            (p / "root.xsd").write_bytes(data)
            (p / "types.xsd").write_bytes(types)
            manifest = {"version": "fixture", "entry": "root.xsd", "root": "{urn:fixture}Root",
                        "files": {"root.xsd": xml.sha(data), "types.xsd": xml.sha(types)}}
            m = p / "manifest.json"
            m.write_text(json.dumps(manifest))
            a = xml.import_xml(b'<Root xmlns="urn:fixture" n="2"/>', "dm2", "fixture", m)
            self.assertTrue(a["validation"]["xsdValidated"])
            self.assertFalse(a["validation"]["semanticConformance"])
            with self.assertRaises(Refusal):
                xml.import_xml(b'<Root xmlns="urn:fixture" n="0"/>', "dm2", "fixture", m)
            (p / "types.xsd").write_bytes(types + b" ")
            with self.assertRaises(Refusal):
                xml.import_xml(b'<Root xmlns="urn:fixture" n="2"/>', "dm2", "fixture", m)

    def test_unpinned_import_remote_schema_and_version_mismatch_refuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for location in ["http://127.0.0.1:9/never.xsd", "unlisted.xsd"]:
                data = f'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"><xs:include schemaLocation="{location}"/></xs:schema>'.encode()
                (p / "root.xsd").write_bytes(data)
                manifest = {"version": "fixture", "entry": "root.xsd", "root": "Root", "files": {"root.xsd": xml.sha(data)}}
                (p / "manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(Refusal):
                    xml.schema_bundle(p / "manifest.json")

    @unittest.skipUnless((ROOT / ".cache/schemas/c2sim/manifest.json").exists(), "run scripts/fetch-c2sim-schema.py")
    def test_public_c2sim_schema_accepts_fixture_and_rejects_unknown_command(self):
        manifest = ROOT / ".cache/schemas/c2sim/manifest.json"
        data = (ROOT / "examples/c2sim-command.xml").read_bytes()
        a = xml.import_xml(data, "c2sim", "OpenC2SIM-SMX-LOX-1.0.1", manifest)
        self.assertTrue(a["validation"]["xsdValidated"])
        with self.assertRaises(Refusal):
            xml.import_xml(data.replace(b"ShareScenario", b"NotACommand"), "c2sim", "OpenC2SIM-SMX-LOX-1.0.1", manifest)

if __name__ == "__main__":
    unittest.main()
