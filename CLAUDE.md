# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python library (`gnre-automacao`) for generating and submitting GNRE (tax payment slips) and DUA-e (Espírito Santo) from NF-e data. Published to PyPI. No test suite exists — validation is done manually against the webservices.

## Build & Install

```bash
pip install -e .                   # editable install
python -m build                    # build wheel/sdist for distribution
```

**Only dependency:** `cryptography >= 41.0.0`. No dev dependencies are defined — add tools (pytest, ruff, etc.) manually as needed.

## Release Process

Releases are published to PyPI automatically via GitHub Actions when a GitHub release is created. To release:
1. Bump `version` in `pyproject.toml`
2. Push and create a GitHub release — CI handles the PyPI upload.

## Architecture

The package is a single Python module (`gnre_automacao/`) with these files:

| File | Responsibility |
|------|---------------|
| `nfe_parser.py` | Parses NF-e XML (`nfeProc`, `NFe`, or `infNFe` roots) into a flat `dados_nfe` dict with tax values and addresses |
| `gnre_xml.py` | Builds GNRE XML lotes, evaluates tax need, emits/consults GNRE receipts. Loads UF config from bundled JSON files |
| `gnre_ws.py` | SOAP envelope construction, HTTPS transport (stdlib only), XML response parsing, `GNREError` exception |
| `dua_es.py` | Full DUA-e (ES) implementation: SOAP 1.2 envelopes, emit/consult/boleto download, municipality/service-area lookups |
| `receipts.py` | Routing layer: `generate_receipts` and `consult_receipts` dispatch to DUA-e for ES, GNRE for all other states |
| `uf_additional_fields.json` | Per-UF extra XML fields required by some states (lazy-loaded) |
| `uf_detalhamento.json` | Per-UF/receita `detalhamento` codes (lazy-loaded) |

### Data flow

```
NF-e XML bytes
  → parse_nfe_xml_bytes()          → dados_nfe dict
  → evaluate_gnre_need(dados_nfe)  → {necessario, guias, taxes, ...}
  → generate_receipts() / emit_gnre_receipt() / emit_dua_es()
      → build XML lote → wrap in SOAP → post_soap() → parse response → recibo
  → consult_receipts() / consult_gnre_receipt() / consult_dua_es()
      → build consulta XML → SOAP → parse TResultLote_GNRE / DUA response
```

### Key routing rules

- `uf_destinatario == "ES"` → DUA-e webservice (`dua_es.py`)
- `uf_destinatario == "SP"` → manual GNRE only (`necessario="M"`)
- `uf_destinatario in {"PE","RJ","RO","SC"}` with 2+ taxes → single multi-receita GNRE lote
- All other UFs → one GNRE lote per receita

### `GNREError`

Raised throughout the codebase. Has fields: `codigo`, `descricao`, `recibo`, `raw_xml`, `details`. Always catch this when calling emit/consult functions.

### Certificate handling

PFX bytes are converted to temporary PEM files via `ssl_context_from_pfx_bytes()`, used for the HTTPS request, then immediately deleted. The library uses only stdlib `http.client` for transport — no `requests` or `httpx`.

### GNRE ambiente values

The `ambiente` parameter is normalized at the call site:
- GNRE: `"producao"` or `"teste"` → `get_endpoints(ambiente)`
- DUA-e: `"producao"` or `"homologacao"` → `get_dua_es_endpoints(ambiente)`
- The routing layer (`receipts.py`) accepts any of these and passes them through unchanged.
