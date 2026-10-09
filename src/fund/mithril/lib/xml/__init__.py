"""Canonical import namespace matching the repository/common library ID."""
from mithril_interop.libraries import resolve_library, invoke_library
from mithril_xml import native_xml
LIBRARY_ID = 'fund.mithril.lib.xml'
def resolve(): return resolve_library(LIBRARY_ID)
def invoke(operation, arguments=None): return invoke_library(LIBRARY_ID, operation, arguments)
