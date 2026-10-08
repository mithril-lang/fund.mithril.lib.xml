"""Bounded native XML custody, pinned offline XSD validation and projections.

XML is retained byte-for-byte. Semantic extraction is explicit and reports loss;
neither a root-name match nor XML well-formedness is schema conformance.
"""
import base64
import hashlib
import json
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote
from lxml import etree
import xmlschema
from . import Refusal

FORMAT = "https://mithril.fund/artifact/native-xml-v1"
MAX_BYTES = 4 * 1024 * 1024
ROOTS = {
    "msdl": {"{urn:sisostds:scenario:military:data:draft:msdl:1}MilitaryScenario"},
    "c2sim": {"{http://www.sisostds.org/schemas/C2SIM/1.1}Message",
              "{http://www.sisostds.org/schemas/C2SIM/1.1}MessageBody"},
    "bpmn": {"{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions"},
    "dmn": {"{https://www.omg.org/spec/DMN/20191111/MODEL/}definitions",
            "{https://www.omg.org/spec/DMN/20230324/MODEL/}definitions"},
    "hla-fom": {"{http://standards.ieee.org/IEEE1516-2010}objectModel"},
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise Refusal("XML must contain 1 through 4194304 bytes")
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                             no_network=True, huge_tree=False, remove_blank_text=False)
    try:
        tree = etree.fromstring(data, parser).getroottree()
    except etree.XMLSyntaxError as exc:
        raise Refusal("malformed XML") from exc
    if tree.docinfo.doctype:
        raise Refusal("DTDs and entities are outside the XML profile")
    elements = [el for el in tree.iter() if isinstance(el.tag, str)]
    if len(elements) > 100000:
        raise Refusal("XML element limit exceeded")
    if any(len(list(el.iterancestors())) > 128 for el in elements):
        raise Refusal("XML depth limit exceeded")
    return tree

class PinnedSchema:
    def __init__(self, manifest, blobs, base):
        # Compile immutable copies: a caller cannot swap a file after hash verification.
        self.temp = tempfile.TemporaryDirectory(prefix="mithril-xsd-")
        directory = Path(self.temp.name).resolve()
        allowed = set()
        for path, data in blobs.items():
            schema_tree = parse(data)
            for element in schema_tree.iter():
                if element.tag in {"{http://www.w3.org/2001/XMLSchema}" + name
                                   for name in ["import", "include", "redefine", "override"]}:
                    location = element.get("schemaLocation")
                    if location:
                        parsed = urlparse(location)
                        target = Path(unquote(parsed.path))
                        if not target.is_absolute():
                            target = path.parent / target
                        if parsed.scheme not in {"", "file"} or target.resolve() not in blobs:
                            self.temp.cleanup()
                            raise Refusal("schema dependency is outside pinned offline bundle")
            target = directory / path.relative_to(base)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            allowed.add(target.resolve())
        def guard(url):
            parsed = urlparse(url)
            if not parsed.scheme and not Path(parsed.path).is_absolute():
                # Preflight pinned every relative import; sandbox resolves it
                # relative to the including document in the frozen directory.
                return url
            target = Path(unquote(parsed.path)).resolve()
            if parsed.scheme not in {"", "file"} or target not in allowed:
                raise Refusal("schema import is outside pinned offline bundle: " + url)
            return target.as_uri()
        try:
            self.schema = xmlschema.XMLSchema11(directory / manifest["entry"],
                base_url=directory.as_uri() + "/", allow="sandbox", defuse="always",
                uri_mapper=guard, use_fallback=False)
        except (xmlschema.XMLSchemaException, ValueError) as exc:
            self.temp.cleanup()
            raise Refusal("offline XSD 1.1 compilation failed") from exc
        self.error = None

    def close(self):
        self.temp.cleanup()

    def __del__(self):
        self.close()

    def validate(self, tree):
        resource = xmlschema.XMLResource(etree.tostring(tree), allow="none", defuse="always")
        self.error = next(self.schema.iter_errors(resource, use_location_hints=False), None)
        return self.error is None

def schema_bundle(manifest_path):
    """Manifest pins every XSD in the dependency closure; no schemaLocation fetch."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if set(manifest) != {"version", "entry", "files", "root"}:
        raise Refusal("schema manifest requires version, entry, files and expanded root QName")
    if not isinstance(manifest["version"], str) or not manifest["version"].strip():
        raise Refusal("schema version must be explicit")
    blobs = {}
    for name, digest in manifest["files"].items():
        path = (manifest_path.parent / name).resolve()
        if not path.is_relative_to(manifest_path.parent):
            raise Refusal("schema path escapes bundle")
        data = path.read_bytes()
        if sha(data) != digest:
            raise Refusal("schema SHA-256 mismatch: " + name)
        parse(data)  # Reject DTD and oversized schema before compilation.
        blobs[path] = data
    entry = (manifest_path.parent / manifest["entry"]).resolve()
    if entry not in blobs:
        raise Refusal("entry schema is not pinned")
    schema = PinnedSchema(manifest, blobs, manifest_path.parent)
    return manifest, schema

def import_xml(data, standard, version, schema_manifest=None):
    if not isinstance(version, str) or not version.strip():
        raise Refusal("source version must be explicit")
    tree = parse(data)
    root = tree.getroot().tag
    # For DM2, C-BML and MIM, a version-pinned bundle supplies the root.
    manifest, schema = schema_bundle(schema_manifest) if schema_manifest else (None, None)
    allowed = ROOTS.get(standard)
    if allowed is None and standard not in {"dm2", "c-bml", "jc3iedm", "mim"}:
        raise Refusal("unsupported XML family")
    if allowed is None and manifest is None:
        raise Refusal("this family requires an explicit pinned schema bundle")
    if root not in (allowed or {manifest["root"]}):
        raise Refusal("root QName is outside the selected native profile")
    if manifest and (root != manifest["root"] or version != manifest["version"]):
        raise Refusal("schema root/version does not match source profile")
    if schema is not None:
        try:
            if not schema.validate(tree):
                raise Refusal("XSD validation failed: " + str(schema.error))
        finally:
            schema.close()
    return {"format": FORMAT, "standard": standard, "version": version,
            "root": root, "sha256": sha(data), "bytesBase64": base64.b64encode(data).decode(),
            "validation": {"wellFormed": True, "xsdValidated": schema is not None,
                           "schemaFiles": manifest["files"] if manifest else {},
                           "semanticConformance": False}}

def export_xml(artifact):
    if artifact.get("format") != FORMAT:
        raise Refusal("not a native XML artifact")
    try:
        data = base64.b64decode(artifact["bytesBase64"], validate=True)
    except (ValueError, KeyError) as exc:
        raise Refusal("invalid archived XML bytes") from exc
    if sha(data) != artifact.get("sha256"):
        raise Refusal("archived XML digest mismatch")
    tree = parse(data)
    if tree.getroot().tag != artifact.get("root"):
        raise Refusal("archived root does not match XML bytes")
    return data

def patch_xml(artifact, patches, schema_manifest=None):
    """Guarded edit of native XML text or attributes; revalidate after edits.
    XPath uses explicit namespace bindings and cannot execute extension functions.
    Each patch must target exactly one element and match its previous value.
    """
    original = export_xml(artifact)
    tree = parse(original)
    if not isinstance(patches, list) or not 1 <= len(patches) <= 1000:
        raise Refusal("expected 1 through 1000 guarded patches")
    for patch in patches:
        if set(patch) != {"xpath", "namespaces", "attribute", "before", "after"}:
            raise Refusal("invalid XML patch fields")
        if not isinstance(patch["after"], str):
            raise Refusal("replacement must be text")
        matches = tree.xpath(patch["xpath"], namespaces=patch["namespaces"])
        if len(matches) != 1 or not isinstance(matches[0], etree._Element):
            raise Refusal("XML patch must select exactly one element")
        el = matches[0]
        attr = patch["attribute"]
        if attr is None:
            if len(el):
                raise Refusal("text patch cannot replace mixed/child content")
            current = el.text
        else:
            current = el.get(attr)
        if current != patch["before"]:
            raise Refusal("stale XML patch precondition")
        if attr is None:
            el.text = patch["after"]
        else:
            el.set(attr, patch["after"])
    data = etree.tostring(tree, encoding="UTF-8", xml_declaration=True)
    updated = import_xml(data, artifact["standard"], artifact["version"], schema_manifest)
    return {"artifact": updated, "receipt": {"before": sha(original), "after": sha(data),
            "patchCount": len(patches), "byteIdentical": False, "effects": False}}

def project(artifact, profile, strict=False):
    """Version-specific explicit XPath mapping into Mithril normalized records.
    Unmapped source leaves remain archived and are reported, never discarded.
    No implicit equivalence between similarly named source metamodel classes.
    """
    tree = parse(export_xml(artifact))
    if profile["standard"] != artifact["standard"] or profile["version"] != artifact["version"]:
        raise Refusal("projection profile standard/version mismatch")
    namespaces = profile["namespaces"]
    document = "urn:sha256:" + artifact["sha256"]
    records, consumed, pending_refs, identities = [], set(), [], {}
    for rule in profile["rules"]:
        for el in tree.xpath(rule["select"], namespaces=namespaces):
            if not isinstance(el, etree._Element):
                raise Refusal("projection must select elements")
            identity = el.xpath(rule["id"], namespaces=namespaces)
            if not isinstance(identity, str) or not identity.strip():
                raise Refusal("projection identity must be a nonblank XPath string")
            path = tree.getpath(el)
            if path in consumed:
                raise Refusal("overlapping projection rules")
            consumed.add(path)
            record = {"@id": "urn:xml-record:" + sha((document + identity).encode()),
                      "standard": rule.get("targetStandard", artifact["standard"]),
                      "version": artifact["version"], "document": document, "record": path,
                      "type": rule["type"], "refs": {},
                      "payload": {"nativeQName": el.tag,
                                  "xmlBase64": base64.b64encode(etree.tostring(el)).decode()}}
            records.append(record)
            identities[identity] = record["@id"]
            pending_refs.append((record, el, rule.get("refs", {})))
    if not records or len({r["@id"] for r in records}) != len(records):
        raise Refusal("projection requires nonempty uniquely identified records")
    for record, el, refs in pending_refs:
        for role, xpath in refs.items():
            targets = el.xpath(xpath, namespaces=namespaces)
            many = isinstance(targets, list)
            targets = targets if many else [targets]
            targets = [str(t.text) if isinstance(t, etree._Element) else str(t) for t in targets]
            if any(t not in identities for t in targets):
                raise Refusal("projection reference points outside mapped identities")
            record["refs"][role] = [identities[t] for t in targets] if many else identities[targets[0]]
    leaves = {tree.getpath(el) for el in tree.iter()
              if isinstance(el.tag, str) and not len(el)}
    unmapped = sorted(p for p in leaves if not any(p == c or p.startswith(c + "/") for c in consumed))
    if strict and unmapped:
        raise Refusal("projection contains unmapped XML leaves")
    return {"model": {"@type": "MissionModel", "@id": document, "records": records},
            "native": artifact,
            "receipt": {"mappedRecords": len(records), "unmappedPaths": unmapped,
                        "losslessArchive": True, "sourceExecution": False}}
