# Project Guidelines

## Code Style
- Follow existing Python 3.10+ style with type hints on public and internal functions.
- Keep names in snake_case and constants in UPPER_CASE.
- Preserve module-level helper patterns used in the package (for example: _dec, _require, and cached JSON loaders).
- Keep the public API surface stable via exports in gnre_automacao/__init__.py.

## Architecture
- This repository is a Python library with a small, explicit module split:
  - gnre_automacao/nfe_parser.py: parse NF-e XML data into normalized dictionaries.
  - gnre_automacao/gnre_xml.py: evaluate GNRE need and build GNRE XML payloads.
  - gnre_automacao/gnre_ws.py: SOAP envelopes, HTTPS communication, SSL/PFX handling, and SOAP response parsing.
  - gnre_automacao/__init__.py: package exports and public API contract.
- UF-specific behavior is data-driven through:
  - gnre_automacao/uf_additional_fields.json
  - gnre_automacao/uf_detalhamento.json

## Build and Test
- Install package for development:
  - pip install -e .
- Build distribution artifacts:
  - python -m pip install build
  - python -m build
- There is currently no committed automated test suite. If a change affects tax calculations, XML generation, or SOAP parsing, validate behavior with focused local checks before finalizing.

## Conventions
- Always use Decimal for monetary values. Do not introduce float arithmetic in tax or total calculations.
- Preserve GNRE domain behavior already encoded in the library, including:
  - receita and guia selection logic in gnre_automacao/gnre_xml.py
  - manual handling for SP/ES scenarios when applicable
- Keep SOAP XML handling defensive:
  - detect and raise on SOAP Fault responses
  - keep parsing resilient when tags are missing
- Keep certificate handling secure:
  - never hardcode secrets
  - preserve temporary file cleanup for PEM material derived from PFX
- Keep compatibility with both test and production endpoints through get_endpoints logic.
- Do not commit certificates, keys, or secret files (.pfx, .pem, .key, .env).
