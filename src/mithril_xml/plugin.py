from pathlib import Path
import base64
from . import Refusal
from . import native_xml as xml
ROOT = Path(__file__).resolve().parents[2]
def call(request):
    operation = request.get("operation")
    if operation == "xml-import":
        return xml.import_xml(base64.b64decode(request["bytesBase64"], validate=True),
                              request["standard"], request["version"], request.get("schemaManifest"))
    if operation == "xml-export":
        return {"bytesBase64": base64.b64encode(xml.export_xml(request["artifact"])).decode()}
    if operation == "xml-patch":
        return xml.patch_xml(request["artifact"], request["patches"], request.get("schemaManifest"))
    if operation == "xml-project":
        return xml.project(request["artifact"], request["profile"], request.get("strict", False))
    raise Refusal("unsupported plugin operation")

class Plugin:
    id = "fund.mithril.lib.xml"
    rpc_version = 1
    operations = ('xml-import', 'xml-export', 'xml-patch', 'xml-project')
    call = staticmethod(call)
