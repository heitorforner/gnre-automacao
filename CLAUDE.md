# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`gnre-automacao` is a Python library for automating GNRE (Guia Nacional de Recolhimento Estadual) generation and submission in Brazil. It parses NF-e XML files, determines GNRE necessity, builds GNRE XML batches, communicates with the official GNRE webservice via SOAP, and extracts payment information from responses.

## Commands

```bash
# Install for development
pip install -e .

# Build distribution package
python -m build
```

There is no automated test suite. Validation is done via focused local checks.

## Architecture

The library has four modules with a clear data-flow:

**NF-e → Parse → Evaluate → Build XML → SOAP → Submit → Parse Response**

### Modules

- **[gnre_automacao/nfe_parser.py](gnre_automacao/nfe_parser.py)** — Parses NF-e XML (supports NFe, nfeProc, infNFe formats) into normalized dicts. Extracts emitter/destination data, tax values (ICMS, ICMS-UF/DIFAL, ST, FCP, IPI, PIS, COFINS, IBS, CBS).

- **[gnre_automacao/gnre_xml.py](gnre_automacao/gnre_xml.py)** — Core GNRE logic. `evaluate_gnre_need()` determines if GNRE is required (returns `"S"`, `"N"`, or `"M"` for manual). Builds GNRE XML batches with state-specific rules loaded from JSON configs.

- **[gnre_automacao/gnre_ws.py](gnre_automacao/gnre_ws.py)** — SOAP envelope assembly, HTTPS communication using PFX certificates (converted to temp PEM files), response parsing, and `GNREError` exception.

- **[gnre_automacao/__init__.py](gnre_automacao/__init__.py)** — Public API contract. All 19 exported functions are the stable interface.

### State-Specific Behavior (JSON configs)

- **[gnre_automacao/uf_additional_fields.json](gnre_automacao/uf_additional_fields.json)** — Extra XML fields required per UF
- **[gnre_automacao/uf_detalhamento.json](gnre_automacao/uf_detalhamento.json)** — Detalhamento codes per receita per UF

### GNRE Tax Receitas

| Receita | Tax Type | Trigger Condition |
|---------|----------|-------------------|
| 100102  | ICMS-DIFAL | Interstate, final consumer, non-taxpayer, value > 0 |
| 100129  | FCP | FCP-UF or FCP-ST value > 0 |
| 100099  | ICMS-ST | ST value > 0 |

### Manual Mode (necessario="M")

SP and ES inter-state operations with guides return `"M"` — these states require manual GNRE submission and are not supported via webservice.

## Key Conventions

- Always use `Decimal` for monetary values — never float arithmetic
- Keep public API stable in `__init__.py`; internal refactors must not break exports
- Certificate handling: PFX bytes → temp PEM files → SSL context → clean up; never hardcode secrets
- SOAP parsing must be defensive: detect SOAP Faults, handle partial/malformed responses
- Both `teste` and `producao` endpoints must be supported via `get_endpoints(ambiente)`
- CNPJ must be registered at the GNRE portal before use; SP and ES do not support webservice submission
