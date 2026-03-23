from __future__ import annotations
import re
from typing import Optional, Dict, Any, List

from .gnre_ws import GNREError
from .dua_es import emit_dua_es, consult_dua_es, download_boleto_dua_es


def generate_receipts(
    dados_nfe: Dict[str, Optional[str]],
    ambiente: str,
    receita: str,
    data_vencimento: str,
    data_pagamento: str,
    pfx_bytes: bytes,
    pfx_password: str,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
    xide: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Unified receipt emitter: routes ES → DUA-e, all other states → GNRE."""
    uf_dest = (dados_nfe.get("uf_destinatario") or "").strip().upper()
    if uf_dest == "ES":
        return emit_dua_es(
            dados_nfe, receita, ambiente, pfx_bytes, pfx_password,
            data_vencimento, data_pagamento=data_pagamento,
            xide=xide, timeout=timeout,
        )
    from .gnre_xml import emit_gnre_receipt
    return emit_gnre_receipt(
        dados_nfe, ambiente, receita, data_vencimento, data_pagamento,
        pfx_bytes, pfx_password, certfile=certfile, keyfile=keyfile,
    )


def consult_receipts(
    nfe_bytes: bytes,
    receipt_numbers: List[str],
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Unified receipt consultation: routes ES → DUA-e, all other states → GNRE.

    Parses nfe_bytes to determine uf_destinatario and cnpj_emitente, then queries
    each receipt number against the appropriate backend.

    Returns a list of dicts — one per receipt_number — each containing:
      - receipt_number: str           (the input receipt ID)
      - source: str                   ("dua_es" or "gnre")
      - status: dict | None           (parsed status, or None on error)
      - linhaDigitavel: str | None
      - valor: str | None
      - dataVencimento: str | None
      - pdfBase64: str | None         (base64 PDF; available for both GNRE and DUA-e)
      - raw: dict                     (full response from the underlying call)
      - error: str                    (only present on failure)
    """
    from .nfe_parser import parse_nfe_xml_bytes

    dados_nfe = parse_nfe_xml_bytes(nfe_bytes)
    uf_dest = (dados_nfe.get("uf_destinatario") or "").strip().upper()
    cnpj_emitente = dados_nfe.get("emitente_cnpj") or ""

    results: List[Dict[str, Any]] = []

    if uf_dest == "ES":
        for n_dua in receipt_numbers:
            entry: Dict[str, Any] = {
                "receipt_number": n_dua,
                "source": "dua_es",
                "status": None,
                "linhaDigitavel": None,
                "valor": None,
                "dataVencimento": None,
                "pdfBase64": None,
            }
            try:
                raw = consult_dua_es(
                    n_dua, cnpj_emitente, ambiente, pfx_bytes, pfx_password, timeout=timeout
                )
                entry["raw"] = raw
                entry["status"] = {
                    "codigo": raw.get("cStat"),
                    "descricao": raw.get("xMotivo"),
                }
                dua_data = raw.get("dua") or {}
                entry["linhaDigitavel"] = dua_data.get("nBar")
                entry["valor"] = dua_data.get("vTot")
                entry["dataVencimento"] = dua_data.get("dVen")
                try:
                    cnpj_digits = re.sub(r"\D", "", cnpj_emitente)
                    boleto = download_boleto_dua_es(
                        n_dua, cnpj_digits, ambiente, pfx_bytes, pfx_password, timeout=timeout
                    )
                    entry["pdfBase64"] = boleto.get("pdf")
                except Exception as e:
                    entry["pdfError"] = str(e)
            except GNREError as e:
                entry["error"] = str(e)
                entry["raw"] = {}
            results.append(entry)

    else:
        from .gnre_xml import consult_gnre_receipt
        for recibo in receipt_numbers:
            entry = {
                "receipt_number": recibo,
                "source": "gnre",
                "status": None,
                "linhaDigitavel": None,
                "valor": None,
                "dataVencimento": None,
                "pdfBase64": None,
            }
            try:
                raw = consult_gnre_receipt(ambiente, recibo, pfx_bytes, pfx_password, incluir_pdf=True, incluir_arquivo_pagamento=True)
                entry["raw"] = raw
                entry["status"] = raw.get("status")
                entry["linhaDigitavel"] = raw.get("linhaDigitavel")
                entry["valor"] = raw.get("valor")
                entry["dataVencimento"] = raw.get("dataVencimento")
                entry["pdfBase64"] = raw.get("pdfBase64")
                if "status_error" in raw:
                    entry["error"] = raw["status_error"]
            except GNREError as e:
                entry["error"] = str(e)
                entry["raw"] = {}
            results.append(entry)

    return results
