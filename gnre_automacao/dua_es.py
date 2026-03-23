from __future__ import annotations
from typing import Optional, Dict, Any, List
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal
import http.client
from urllib.parse import urlparse

from .gnre_ws import GNREError, ssl_context_from_pfx_bytes
from .gnre_xml import _dec, _digits, _mun5

DUA_ES_NS = "http://www.sefaz.es.gov.br/duae"
DUA_SEFAZ_CNPJ = "27080571000130"

RECEITA_TO_CSERV: Dict[str, str] = {
    "100102": "3867",  # DIFAL
    "100099": "1376",  # ST
    "100129": "1627",  # FCP
}

# {ambiente: {cServ: cArea}} — populated lazily on first emit per environment
_CSERV_CAREA_CACHE: Dict[str, Dict[str, str]] = {}

# {ambiente: {ibge7: cMunDuae, ibge5: cMunDuae, nome_upper: cMunDuae}} — municipality cache
_MUN_CACHE: Dict[str, Dict[str, str]] = {}

# Known cArea fallback values for ICMS services at SEFAZ-ES (CNPJ 27080571000130).
# Used when duaConsultaAreaServico is unavailable or returns an error.
# Update these if SEFAZ-ES changes the area configuration.
_CSERV_CAREA_FALLBACK: Dict[str, str] = {
    "3867": "1902",  # DIFAL — ICMS-UF destino (área: Receita de ICMS)
    "1376": "1902",  # ST — Substituição Tributária (área: Receita de ICMS)
    "1627": "1902",  # FCP — Fundo de Combate à Pobreza (área: Receita de ICMS)
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

def get_dua_es_endpoints(ambiente: str = "producao") -> str:
    if ambiente.lower() in {"homologacao", "teste", "homologação", "2"}:
        return "https://homologacao.sefaz.es.gov.br/WsDua/DuaService.asmx"
    return "https://app.sefaz.es.gov.br/WsDua/DuaService.asmx"


# ---------------------------------------------------------------------------
# SOAP 1.2 envelope
# ---------------------------------------------------------------------------

def build_soap_envelope_dua_es(method: str, xml_payload: str) -> str:
    ns = DUA_ES_NS
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope'
        ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
        ' xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Header>"
        f'<DuaServiceHeader xmlns="{ns}">'
        "<versao>1.01</versao>"
        "</DuaServiceHeader>"
        "</soap12:Header>"
        "<soap12:Body>"
        f'<{method} xmlns="{ns}">'
        "<duaDadosMsg>"
        f"{xml_payload}"
        "</duaDadosMsg>"
        f"</{method}>"
        "</soap12:Body>"
        "</soap12:Envelope>"
    )


# ---------------------------------------------------------------------------
# HTTP transport (SOAP 1.2 content-type)
# ---------------------------------------------------------------------------

def post_soap_dua_es(
    url: str,
    envelope_xml: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> str:
    parsed = urlparse(url)
    context = ssl_context_from_pfx_bytes(pfx_bytes, pfx_password)
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, context=context, timeout=timeout
    )
    path = parsed.path or "/"
    conn.request(
        "POST",
        path,
        body=envelope_xml.encode("utf-8"),
        headers={
            "Content-Type": "application/soap+xml; charset=utf-8",
            "SOAPAction": '""',
        },
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return data.decode("utf-8")


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _tp_amb(ambiente: str) -> str:
    return "2" if ambiente.lower() in {"homologacao", "teste", "homologação"} else "1"


def build_dua_es_emissao_xml(
    dados_nfe: Dict[str, Optional[str]],
    cserv: str,
    carea: str,
    ambiente: str,
    data_vencimento: str,
    valor: Decimal,
    data_pagamento: Optional[str] = None,
    xide: Optional[str] = None,
    cmun: Optional[str] = None,
    cnpj_pes: Optional[str] = None,
) -> str:
    """Build <emisDua> XML for DUA-e emission.

    cmun: DUA-e municipality code (5 digits). If None, <cMun> is omitted.
    cnpj_pes: CNPJ da empresa emitente (quem recolhe o imposto).
              Defaults to emitente CNPJ if not provided.
    """
    cnpj_emi = _digits(dados_nfe.get("emitente_cnpj") or "")
    chave = _digits(dados_nfe.get("chave_nfe") or "")
    d_pag = data_pagamento or data_vencimento
    d_ref = data_vencimento[:7]  # YYYY-MM
    x_inf = (xide or chave[-20:] or "")[:30]
    tpAmb = _tp_amb(ambiente)

    # cnpjPes: CPF/CNPJ of the contributor (payer).
    # Pass CPF as 11 digits (no zero-padding) or CNPJ as 14 digits.
    if cnpj_pes is None:
        cnpj_pes = cnpj_emi
    else:
        cnpj_pes = _digits(cnpj_pes)

    root = ET.Element("emisDua", {"versao": "1.01", "xmlns": DUA_ES_NS})
    ET.SubElement(root, "tpAmb").text = tpAmb
    ET.SubElement(root, "cnpjEmi").text = cnpj_emi
    ET.SubElement(root, "cnpjOrg").text = DUA_SEFAZ_CNPJ
    ET.SubElement(root, "cArea").text = carea
    ET.SubElement(root, "cServ").text = cserv
    ET.SubElement(root, "cnpjPes").text = cnpj_pes
    ET.SubElement(root, "dRef").text = d_ref
    ET.SubElement(root, "dVen").text = data_vencimento
    ET.SubElement(root, "dPag").text = d_pag
    if cmun:
        ET.SubElement(root, "cMun").text = cmun
    ET.SubElement(root, "xInf").text = x_inf
    ET.SubElement(root, "vRec").text = f"{valor:.2f}"
    ET.SubElement(root, "qtde").text = "1"
    return ET.tostring(root, encoding="unicode")


def build_dua_es_consulta_xml(n_dua: str, cnpj: str, ambiente: str) -> str:
    root = ET.Element("consDua", {"versao": "1.01", "xmlns": DUA_ES_NS})
    ET.SubElement(root, "tpAmb").text = _tp_amb(ambiente)
    ET.SubElement(root, "nDua").text = n_dua
    ET.SubElement(root, "cnpj").text = _digits(cnpj)
    return ET.tostring(root, encoding="unicode")


def _build_boleto_xml(n_dua: str, cnpj: str, ambiente: str) -> str:
    root = ET.Element("obterPdfDua", {"versao": "1.01", "xmlns": DUA_ES_NS})
    ET.SubElement(root, "tpAmb").text = _tp_amb(ambiente)
    ET.SubElement(root, "nDua").text = n_dua
    ET.SubElement(root, "cnpj").text = _digits(cnpj)
    return ET.tostring(root, encoding="unicode")


def _build_cons_area_serv_xml(cnpj_org: str, ambiente: str) -> str:
    root = ET.Element("consAreaServico", {"versao": "1.01", "xmlns": DUA_ES_NS})
    ET.SubElement(root, "tpAmb").text = _tp_amb(ambiente)
    ET.SubElement(root, "cnpj").text = _digits(cnpj_org)
    return ET.tostring(root, encoding="unicode")


def _build_cons_municipio_xml(ambiente: str) -> str:
    root = ET.Element("consMunicipio", {"versao": "1.01", "xmlns": DUA_ES_NS})
    ET.SubElement(root, "tpAmb").text = _tp_amb(ambiente)
    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def _ns(tag: str) -> str:
    return f"{{{DUA_ES_NS}}}{tag}"


def _txt(el: Optional[ET.Element]) -> Optional[str]:
    return el.text.strip() if el is not None and el.text else None


def _extract_soap12_body_child(soap_xml: str) -> ET.Element:
    """Return the ret* payload element from the DUA-e SOAP response.

    DUA-e response structure:
      Body > duaXxxResponse > duaXxxResult > retXxx (target)
    """
    ns12 = "{http://www.w3.org/2003/05/soap-envelope}"
    ns11 = "{http://schemas.xmlsoap.org/soap/envelope/}"
    try:
        root = ET.fromstring(soap_xml)
    except ET.ParseError as exc:
        raise GNREError("Resposta DUA-e: XML inválido", raw_xml=soap_xml) from exc
    body = root.find(f"{ns12}Body") or root.find(f"{ns11}Body")
    if body is None:
        raise GNREError("Resposta DUA-e: Body SOAP não encontrado", raw_xml=soap_xml)
    # Check for SOAP Fault
    fault = body.find(f"{ns12}Fault") or body.find(f"{ns11}Fault")
    if fault is not None:
        msg = ET.tostring(fault, encoding="unicode")
        raise GNREError("SOAP Fault DUA-e", descricao=msg, raw_xml=soap_xml)
    # Walk into Body > Response > Result > retXxx
    for resp_el in body:         # duaXxxResponse
        for result_el in resp_el:  # duaXxxResult
            for ret_el in result_el:  # retXxx (the actual payload)
                return ret_el
            return result_el  # fallback: return Result if no child
        return resp_el  # fallback: return Response if no child
    raise GNREError("Resposta DUA-e: Body vazio", raw_xml=soap_xml)


def parse_dua_es_emissao_response(soap_xml: str) -> Dict[str, Any]:
    payload = _extract_soap12_body_child(soap_xml)
    # Strip namespace from tag for comparison
    tag = payload.tag.split("}")[-1] if "}" in payload.tag else payload.tag
    if tag != "retEmisDua":
        # maybe the payload IS retEmisDua already
        if not tag.endswith("retEmisDua"):
            raise GNREError(
                f"Resposta DUA-e: elemento raiz inesperado '{tag}'", raw_xml=soap_xml
            )
    c_stat = _txt(payload.find(_ns("cStat")))
    x_motivo = _txt(payload.find(_ns("xMotivo")))
    if c_stat != "105":
        raise GNREError(
            "Emissão DUA-e falhou",
            codigo=c_stat,
            descricao=x_motivo,
            raw_xml=soap_xml,
        )
    # nDua, dEmi, vTot, nBar are inside the <dua> child element
    dua_el = payload.find(_ns("dua"))
    def _dua(tag: str) -> Optional[str]:
        if dua_el is not None:
            return _txt(dua_el.find(_ns(tag)))
        return _txt(payload.find(".//" + _ns(tag)))
    return {
        "nDua": _dua("nDua"),
        "dEmi": _dua("dEmi"),
        "vTot": _dua("vTot"),
        "nBar": _dua("nBar"),
        "cStat": c_stat,
        "xMotivo": x_motivo,
    }


def _el_to_dict(el: ET.Element) -> Any:
    """Recursively convert an XML element to a nested dict."""
    children = list(el)
    if not children:
        return el.text.strip() if el.text else None
    out: Dict[str, Any] = {}
    for child in children:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        out[local] = _el_to_dict(child)
    return out


def parse_dua_es_consulta_response(soap_xml: str) -> Dict[str, Any]:
    payload = _extract_soap12_body_child(soap_xml)
    out: Dict[str, Any] = {}
    for child in payload:
        local = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        out[local] = _el_to_dict(child)
    return out


def _parse_boleto_response(soap_xml: str) -> Dict[str, Any]:
    payload = _extract_soap12_body_child(soap_xml)
    c_stat = _txt(payload.find(_ns("cStat")))
    x_motivo = _txt(payload.find(_ns("xMotivo")))
    pdf_el = payload.find(_ns("xPdf"))
    pdf = _txt(pdf_el)
    if not pdf and c_stat and c_stat != "105":
        raise GNREError(
            "Download boleto DUA-e falhou",
            codigo=c_stat,
            descricao=x_motivo,
            raw_xml=soap_xml,
        )
    return {
        "pdf": pdf,
        "nDua": _txt(payload.find(_ns("nDua"))),
        "cStat": c_stat,
        "xMotivo": x_motivo,
    }


def _parse_cons_area_serv_response(soap_xml: str) -> List[Dict[str, Any]]:
    payload = _extract_soap12_body_child(soap_xml)
    areas: List[Dict[str, Any]] = []
    # Response: <retConsAreaServico> > <orgao> > <area cod="..." desc="..."> > <servico cod="..." desc="..." codReceita="..." />
    # Attributes are used, not child elements.
    for orgao_el in payload.findall(_ns("orgao")):
        for area_el in orgao_el.findall(_ns("area")):
            c_area = area_el.get("cod")
            x_area = area_el.get("desc")
            servicos = []
            for serv_el in area_el.findall(_ns("servico")):
                servicos.append(
                    {
                        "cServ": serv_el.get("cod"),
                        "xServ": serv_el.get("desc"),
                        "codReceita": serv_el.get("codReceita"),
                    }
                )
            areas.append({"cArea": c_area, "xArea": x_area, "servicos": servicos})
    return areas


def _parse_cons_municipio_response(soap_xml: str) -> List[Dict[str, Any]]:
    """Parse duaConsultaMunicipio response.

    Expected: <retConsMun> > <municipio cod="57053" desc="VITORIA" codIBGE="3205309"/>
    (attribute-based, similar to consAreaServico)
    """
    payload = _extract_soap12_body_child(soap_xml)
    muns: List[Dict[str, Any]] = []
    # Try both direct children and nested under any wrapper element
    candidates = list(payload.findall(_ns("municipio")))
    if not candidates:
        for child in payload:
            candidates.extend(child.findall(_ns("municipio")))
    for el in candidates:
        muns.append(
            {
                "cMun": el.get("cod") or el.get("cMun") or _txt(el.find(_ns("cod"))),
                "xMun": el.get("desc") or el.get("xMun") or _txt(el.find(_ns("desc"))),
                "codIBGE": el.get("codIBGE") or el.get("codigoIBGE") or _txt(el.find(_ns("codIBGE"))),
            }
        )
    return muns


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_carea_for_cserv(
    cserv: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
) -> str:
    cache = _CSERV_CAREA_CACHE.get(ambiente)
    if not cache:
        try:
            areas = consult_area_servico_dua_es(DUA_SEFAZ_CNPJ, ambiente, pfx_bytes, pfx_password)
            mapping: Dict[str, str] = {}
            for area in areas:
                for serv in area.get("servicos", []):
                    cs = serv.get("cServ")
                    ca = area.get("cArea")
                    if cs and ca:
                        mapping[cs] = ca
            _CSERV_CAREA_CACHE[ambiente] = mapping
            cache = mapping
        except Exception:
            # Fallback: use hardcoded known values when consultation fails
            cache = {}
    result = cache.get(cserv) or _CSERV_CAREA_FALLBACK.get(cserv)
    if not result:
        raise GNREError(
            f"cArea não encontrada para cServ={cserv}. "
            "Verifique se o CNPJ está cadastrado no portal DUA-e (SEFAZ-ES) "
            "ou atualize _CSERV_CAREA_FALLBACK no módulo dua_es.py.",
            details={"cserv": cserv, "ambiente": ambiente},
        )
    return result


def _normalize_mun_name(name: str) -> str:
    """Normalize municipality name: uppercase, remove accents, keep only letters/spaces."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    return ascii_str.upper().strip()


def _get_cmun_dua_es(
    ibge_cod: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    nome_mun: Optional[str] = None,
) -> Optional[str]:
    """Resolve an IBGE municipality code (or name) to the DUA-e internal code.

    DUA-e municipality response does not include IBGE codes, so matching is done
    by normalized municipality name obtained from the NF-e or passed directly.

    Returns None if the municipality cannot be resolved (caller may omit <cMun>).
    """
    cache = _MUN_CACHE.get(ambiente)
    if not cache:
        try:
            muns = consult_municipio_dua_es(ambiente, pfx_bytes, pfx_password)
            mapping: Dict[str, str] = {}
            for m in muns:
                cmun = m.get("cMun") or ""
                if not cmun:
                    continue
                nome = _normalize_mun_name(m.get("xMun") or "")
                if nome:
                    mapping[nome] = cmun
            _MUN_CACHE[ambiente] = mapping
            cache = mapping
        except Exception:
            cache = {}

    # Try by normalized municipality name (from NF-e xMun)
    if nome_mun:
        result = cache.get(_normalize_mun_name(nome_mun))
        if result:
            return result

    return None


# ---------------------------------------------------------------------------
# High-level public functions
# ---------------------------------------------------------------------------

def consult_area_servico_dua_es(
    cnpj_org: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    xml_payload = _build_cons_area_serv_xml(cnpj_org, ambiente)
    envelope = build_soap_envelope_dua_es("duaConsultaAreaServico", xml_payload)
    url = get_dua_es_endpoints(ambiente)
    resp = post_soap_dua_es(url, envelope, pfx_bytes, pfx_password, timeout=timeout)
    return _parse_cons_area_serv_response(resp)


_BOLETO_BASE_URL = (
    "https://internet.sefaz.es.gov.br/agenciavirtual/area_publica"
    "/e-dua/views/imprimir-dua.php"
)


def get_boleto_url_dua_es(n_dua: str, cpf_cnpj_pes: str) -> str:
    """Return the public URL to view/print the DUA-e boleto as HTML.

    No certificate required — the page is publicly accessible.
    """
    cpf_cnpj = _digits(cpf_cnpj_pes)
    return f"{_BOLETO_BASE_URL}?numDua={n_dua}&codCpfCnpjPessoa={cpf_cnpj}"


def download_boleto_html_dua_es(n_dua: str, cpf_cnpj_pes: str, timeout: int = 15) -> str:
    """Download the DUA-e boleto HTML from the SEFAZ-ES public portal.

    Returns the raw HTML string. No certificate required.
    """
    url = get_boleto_url_dua_es(n_dua, cpf_cnpj_pes)
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def consult_municipio_dua_es(
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Consult DUA-e municipality codes via duaConsultaMunicipio webservice.

    Returns a list of dicts with keys: cMun (DUA-e code), xMun (name), codIBGE.
    """
    xml_payload = _build_cons_municipio_xml(ambiente)
    envelope = build_soap_envelope_dua_es("duaConsultaMunicipio", xml_payload)
    url = get_dua_es_endpoints(ambiente)
    resp = post_soap_dua_es(url, envelope, pfx_bytes, pfx_password, timeout=timeout)
    return _parse_cons_municipio_response(resp)


def download_boleto_dua_es(
    n_dua: str,
    cnpj: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    xml_payload = _build_boleto_xml(n_dua, cnpj, ambiente)
    envelope = build_soap_envelope_dua_es("duaObterPdf", xml_payload)
    url = get_dua_es_endpoints(ambiente)
    resp = post_soap_dua_es(url, envelope, pfx_bytes, pfx_password, timeout=timeout)
    return _parse_boleto_response(resp)


def emit_dua_es(
    dados_nfe: Dict[str, Optional[str]],
    receita: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    data_vencimento: str,
    data_pagamento: Optional[str] = None,
    xide: Optional[str] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {"receita": receita, "recibo": None}
    try:
        cserv = RECEITA_TO_CSERV.get(receita)
        if not cserv:
            raise GNREError(f"Receita '{receita}' não mapeada para DUA-e ES", details={"receita": receita})

        # Determine value
        if receita == "100102":
            valor = _dec(dados_nfe.get("valor_vICMSUFDest"))
        elif receita == "100099":
            valor = _dec(dados_nfe.get("valor_vST"))
        elif receita == "100129":
            valor = _dec(dados_nfe.get("valor_vFCPUFDest")) + _dec(dados_nfe.get("valor_vFCPST"))
        else:
            valor = Decimal("0")

        if valor <= Decimal("0"):
            raise GNREError(
                f"Valor zero para receita {receita} — DUA-e não emitida",
                details={"receita": receita, "valor": str(valor)},
            )

        carea = _get_carea_for_cserv(cserv, ambiente, pfx_bytes, pfx_password)

        # cnpjPes: CNPJ da empresa emitente (quem recolhe o imposto)
        cnpj_pes_raw = dados_nfe.get("emitente_cnpj")

        # cMun: resolve destinatário's municipality to DUA-e internal code (by name)
        dest_ibge = dados_nfe.get("destinatario_cod_mun") or ""
        dest_nome_mun = dados_nfe.get("destinatario_nome_mun")
        cmun = _get_cmun_dua_es(dest_ibge, ambiente, pfx_bytes, pfx_password, nome_mun=dest_nome_mun)

        xml_payload = build_dua_es_emissao_xml(
            dados_nfe, cserv, carea, ambiente, data_vencimento, valor,
            data_pagamento=data_pagamento, xide=xide,
            cmun=cmun, cnpj_pes=cnpj_pes_raw,
        )
        envelope = build_soap_envelope_dua_es("duaEmissao", xml_payload)
        url = get_dua_es_endpoints(ambiente)
        resp = post_soap_dua_es(url, envelope, pfx_bytes, pfx_password, timeout=timeout)
        emissao = parse_dua_es_emissao_response(resp)

        n_dua = emissao["nDua"]
        boleto_cnpj = _digits(cnpj_pes_raw or "")
        boleto_url = get_boleto_url_dua_es(n_dua, boleto_cnpj)

        pdf_base64: Optional[str] = None
        try:
            boleto = download_boleto_dua_es(n_dua, boleto_cnpj, ambiente, pfx_bytes, pfx_password, timeout=timeout)
            pdf_base64 = boleto.get("pdf")
        except Exception:
            pass

        item.update({
            "recibo": n_dua,
            "status": {
                "numeroRecibo": n_dua,
                "codigo": emissao["cStat"],
                "descricao": emissao["xMotivo"],
            },
            "linhaDigitavel": emissao["nBar"],
            "valor": emissao["vTot"],
            "dataVencimento": data_vencimento,
            "boletoUrl": boleto_url,
            "pdfBase64": pdf_base64,
            "cServ": cserv,
        })
    except GNREError as e:
        item["error"] = str(e)
        item["details"] = getattr(e, "details", None)
    return item


def consult_dua_es(
    n_dua: str,
    cnpj: str,
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    timeout: int = 30,
) -> Dict[str, Any]:
    xml_payload = build_dua_es_consulta_xml(n_dua, cnpj, ambiente)
    envelope = build_soap_envelope_dua_es("duaConsulta", xml_payload)
    url = get_dua_es_endpoints(ambiente)
    resp = post_soap_dua_es(url, envelope, pfx_bytes, pfx_password, timeout=timeout)
    return parse_dua_es_consulta_response(resp)


def generate_dua_es_receipts(
    dados_nfe: Dict[str, Optional[str]],
    ambiente: str,
    pfx_bytes: bytes,
    pfx_password: str,
    data_vencimento: str,
    data_pagamento: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    from .gnre_xml import _dec as dec
    vICMSUF = dec(dados_nfe.get("valor_vICMSUFDest"))
    vST = dec(dados_nfe.get("valor_vST"))
    vFCPUF = dec(dados_nfe.get("valor_vFCPUFDest"))
    vFCPST = dec(dados_nfe.get("valor_vFCPST"))
    vFCP = vFCPUF + vFCPST

    receitas = []
    if vICMSUF > Decimal("0"):
        receitas.append("100102")
    if vFCP > Decimal("0"):
        receitas.append("100129")
    if vST > Decimal("0"):
        receitas.append("100099")

    results = []
    for receita in receitas:
        result = emit_dua_es(
            dados_nfe, receita, ambiente, pfx_bytes, pfx_password,
            data_vencimento, data_pagamento=data_pagamento, timeout=timeout,
        )
        results.append(result)
    return results
