# Project Guidelines

## Architecture
- This repository is a Python library, not an application. Keep changes focused on the public package in `gnre_automacao/`.
- Use the existing module split:
  - `nfe_parser.py` parses NF-e XML into a flat `dados_nfe` dict.
  - `gnre_xml.py` contains GNRE tax evaluation and XML builders.
  - `gnre_ws.py` contains SOAP transport, SSL/PFX handling, and XML response parsing.
  - `dua_es.py` contains the ES-specific DUA-e integration.
  - `receipts.py` is the routing layer: ES uses DUA-e, other UFs use GNRE.
- Preserve the public API exported by `gnre_automacao/__init__.py` unless the task explicitly requires an API change.

## Build And Validation
- Install for development with `pip install -e .`.
- Build distributable artifacts with `python -m build`.
- There is no automated test suite in this repo. For changes to tax logic, XML generation, SOAP parsing, routing, or certificate handling, run focused local validation and call out any validation gaps in the final response.

## Conventions
- Use Python 3.10+ style consistent with the existing codebase.
- Use `Decimal` for monetary and tax values. Do not introduce float arithmetic.
- Keep XML handling defensive and namespace-aware with `xml.etree.ElementTree`, matching the existing helpers and patterns.
- Keep transport code on the standard library stack already used here. Do not introduce `requests` or `httpx` unless explicitly requested.
- Preserve secure certificate handling: PFX material is converted to temporary PEM files and must be cleaned up after use.
- Prefer raising or propagating `GNREError` for domain and webservice failures, and preserve its structured details when possible.
- Keep UF-specific behavior data-driven through `uf_additional_fields.json` and `uf_detalhamento.json` when applicable.

## Project-Specific Rules
- `uf_destinatario == "ES"` routes to DUA-e, not GNRE.
- `uf_destinatario == "SP"` is manual-only for GNRE webservice flows.
- PE, RJ, RO, and SC with multiple applicable taxes should stay on the existing multi-receita GNRE flow.
- Avoid committing certificates, keys, secrets, or sample credentials.

## References
- Use `README.md` for usage examples and return-shape expectations.
- Use `CLAUDE.md` for architecture, data flow, and release-process details.
