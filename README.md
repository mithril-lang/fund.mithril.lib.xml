# fund.mithril.lib.xml

Independent specification plugin for Mithril JSON RPC v1. Plugin ID `fund.mithril.lib.xml`.

Operations: xml-import, xml-export, xml-patch, xml-project.

Install with `python -m pip install -e .`; discovery uses the `mithril.interop.plugins` entry-point group.

Pinned offline XSD1.1, byte-exact XML custody, guarded edits and explicit structural projection. No general semantic-conformance claim.

[Detailed boundaries](https://github.com/mithril-lang/fund.mithril.lib.interop/blob/main/docs/design.md)

## Common library ID and imports

Repository, plugin and library ID: `fund.mithril.lib.xml`. Python/Hy namespace: `fund.mithril.lib.xml`. `.cljk` and `.kotoba` facades are under the matching `src/` namespace path; the packaged `.mith` Library binds this ID to `https://mithril.fund/lib/fund.mithril.lib.xml` with its canonical graph digest.

See the [cross-language contract](https://github.com/mithril-lang/fund.mithril.lib.interop/blob/main/docs/language-adapters.md). Import resolution performs no automatic downloads or network effects.
