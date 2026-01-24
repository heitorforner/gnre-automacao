from __future__ import annotations
import ssl
import http.client
from urllib.parse import urlparse
from typing import Optional, Dict, Tuple
import tempfile
import os


class GNREError(Exception):
    def __init__(self, message: str, codigo: Optional[str] = None, descricao: Optional[str] = None, recibo: Optional[str] = None, raw_xml: Optional[str] = None, details: Optional[Dict[str, any]] = None):
        super().__init__(message)
        self.codigo = codigo
        self.descricao = descricao
        self.recibo = recibo
        self.raw_xml = raw_xml
        self.details = details
    def __str__(self) -> str:
        base = self.args[0] if self.args else ""
        parts = [base]
        if self.codigo:
            parts.append(f"codigo={self.codigo}")
        if self.descricao:
            parts.append(f"descricao={self.descricao}")
        if self.recibo:
            parts.append(f"recibo={self.recibo}")
        if self.details:
            parts.append(f"detalhes={self.details}")
        if self.raw_xml:
            s = self.raw_xml.strip()
            if len(s) > 500:
                s = s[:500] + "..."
            parts.append(f"xml={s}")
        return " | ".join(parts)

def _dados_ns(service: str) -> str:
    return f"http://www.gnre.pe.gov.br/webservice/{service}"

def build_soap_envelope(service: str, xml_payload: str, versao_dados: str = "2.00") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Header>"
        '<gnreCabecMsg xmlns="http://www.gnre.pe.gov.br/wsdl/processar">'
        f"<versaoDados>{versao_dados}</versaoDados>"
        "</gnreCabecMsg>"
        "</soapenv:Header>"
        "<soapenv:Body>"
        f'<gnreDadosMsg xmlns="{_dados_ns(service)}">'
        f"{xml_payload}"
        "</gnreDadosMsg>"
        "</soapenv:Body>"
        "</soapenv:Envelope>"
    )

def build_soap_envelope_tlote(xml_tlote: str, versao_dados: str = "2.00") -> str:
    return build_soap_envelope("GnreLoteRecepcao", xml_tlote, versao_dados)

def get_endpoints(ambiente: str = "producao") -> Dict[str, str]:
    base = "https://www.gnre.pe.gov.br"
    if ambiente.lower() == "teste":
        base = "https://www.testegnre.pe.gov.br:444"
    return {
        "recepcao_lote": f"{base}/gnreWS/services/GnreLoteRecepcao",
        "resultado_lote": f"{base}/gnreWS/services/GnreResultadoLote",
        "recepcao_consulta": f"{base}/gnreWS/services/GnreLoteRecepcaoConsulta",
        "resultado_consulta": f"{base}/gnreWS/services/GnreResultadoLoteConsulta",
        "config_uf": f"{base}/gnreWS/services/GnreConfigUF",
    }

def _write_temp_pem(cert_pem: bytes, key_pem: bytes, chain_pem_list: Optional[list[bytes]]) -> Tuple[str, str]:
    cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
    key_fd, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(cert_fd, "wb") as fcert:
        fcert.write(cert_pem)
        if chain_pem_list:
            for c in chain_pem_list:
                fcert.write(c)
    with os.fdopen(key_fd, "wb") as fkey:
        fkey.write(key_pem)
    return cert_path, key_path

def ssl_context_from_pfx_bytes(pfx_bytes: bytes, password: str) -> ssl.SSLContext:
    from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
    from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
    key, cert, add_chain = load_key_and_certificates(pfx_bytes, password.encode("utf-8"))
    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    chain_pem = [c.public_bytes(Encoding.PEM) for c in add_chain] if add_chain else None
    cert_path, key_path = _write_temp_pem(cert_pem, key_pem, chain_pem)
    context = ssl.create_default_context()
    try:
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    finally:
        try:
            os.remove(cert_path)
        except Exception:
            pass
        try:
            os.remove(key_path)
        except Exception:
            pass
    return context

def post_soap(url: str, envelope_xml: str, certfile: Optional[str] = None, keyfile: Optional[str] = None, pfx_bytes: Optional[bytes] = None, pfx_password: Optional[str] = None, timeout: int = 30, verify_ssl: bool = True) -> str:
    parsed = urlparse(url)
    if verify_ssl:
        if pfx_bytes and pfx_password:
            context = ssl_context_from_pfx_bytes(pfx_bytes, pfx_password)
        else:
            context = ssl.create_default_context()
            if certfile and keyfile:
                context.load_cert_chain(certfile=certfile, keyfile=keyfile)
    else:
        context = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, context=context, timeout=timeout)
    path = parsed.path or "/"
    conn.request(
        "POST",
        path,
        body=envelope_xml.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "",
        },
    )
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return data.decode("utf-8")

def extract_xml_from_soap(soap_xml: str) -> str:
    try:
        import xml.etree.ElementTree as ET
        ns_soap = "{http://schemas.xmlsoap.org/soap/envelope/}"
        root = ET.fromstring(soap_xml)
        body = root.find(ns_soap + "Body")
        if body is None:
            return soap_xml
        for child in body:
            for sub in child:
                return ET.tostring(sub, encoding="utf-8").decode("utf-8")
        return ET.tostring(body, encoding="utf-8").decode("utf-8")
    except Exception:
        return soap_xml

def raise_on_soap_fault(soap_xml: str) -> None:
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(soap_xml)
        ns_soap = "{http://schemas.xmlsoap.org/soap/envelope/}"
        body = root.find(ns_soap + "Body")
        if body is not None:
            for fault in body.findall(ns_soap + "Fault"):
                msg = ET.tostring(fault, encoding="utf-8").decode("utf-8")
                raise GNREError("SOAP Fault", descricao=msg)
    except ET.ParseError:
        pass

def parse_tr_ret_lote(soap_xml: str) -> Optional[str]:
    try:
        import xml.etree.ElementTree as ET
        ns = "{http://www.gnre.pe.gov.br}"
        root = ET.fromstring(extract_xml_from_soap(soap_xml))
        if root.tag.endswith("TRetLote_GNRE"):
            rec = root.find(ns + "recibo")
            if rec is not None:
                num = rec.find(ns + "numero")
                if num is not None and num.text:
                    return num.text.strip()
        return None
    except Exception:
        return None

def parse_tresult_lote(soap_xml: str) -> Dict[str, any]:
    import xml.etree.ElementTree as ET
    ns = "{http://www.gnre.pe.gov.br}"
    out = {"numeroRecibo": None, "situacao": None, "guias": [], "pdfGuias": None, "arquivoPagamento": None}
    raise_on_soap_fault(soap_xml)
    xml = extract_xml_from_soap(soap_xml)
    root = ET.fromstring(xml)
    if not root.tag.endswith("TResultLote_GNRE"):
        return out
    nr = root.find(ns + "numeroRecibo")
    if nr is not None and nr.text:
        out["numeroRecibo"] = nr.text.strip()
    sit = root.find(ns + "situacaoProcess")
    if sit is not None:
        cod = sit.find(ns + "codigo")
        desc = sit.find(ns + "descricao")
        out["situacao"] = {"codigo": cod.text.strip() if cod is not None and cod.text else None, "descricao": desc.text.strip() if desc is not None and desc.text else None}
    res = root.find(ns + "resultado")
    if res is not None:
        for guia in res.findall(ns + "guia"):
            item = {}
            linha = guia.find(ns + "linhaDigitavel")
            barras = guia.find(ns + "codigoBarras")
            qrcode = guia.find(ns + "qrcodePayload")
            nn = guia.find(ns + "nossoNumero")
            sg = guia.find(ns + "situacaoGuia")
            item["linhaDigitavel"] = linha.text.strip() if linha is not None and linha.text else None
            item["codigoBarras"] = barras.text.strip() if barras is not None and barras.text else None
            item["qrcodePayload"] = qrcode.text.strip() if qrcode is not None and qrcode.text else None
            item["nossoNumero"] = nn.text.strip() if nn is not None and nn.text else None
            item["situacaoGuia"] = sg.text.strip() if sg is not None and sg.text else None
            item["valor"] = None
            item["dataVencimento"] = None
            vg = guia.find(ns + "valorGNRE")
            if vg is not None and vg.text:
                item["valor"] = vg.text.strip()
            itens = guia.find(ns + "itensGNRE")
            if itens is not None:
                it = itens.find(ns + "item")
                if it is not None:
                    dv = it.find(ns + "dataVencimento")
                    if dv is not None and dv.text:
                        item["dataVencimento"] = dv.text.strip()
            pend = []
            for cand in ["observacao", "motivo", "motivos", "motivoRejeicao", "motivosRejeicao", "erro", "erros", "mensagem", "mensagens", "pendencia", "pendencias"]:
                for el in guia.findall(".//" + ns + cand):
                    if el is not None and el.text:
                        t = el.text.strip()
                        if t:
                            pend.append(t)
            item["pendencias"] = pend if pend else None
            try:
                item["guiaXml"] = ET.tostring(guia, encoding="utf-8").decode("utf-8")
            except Exception:
                item["guiaXml"] = None
            out["guias"].append(item)
        pg = res.find(ns + "pdfGuias")
        if pg is not None and pg.text:
            out["pdfGuias"] = pg.text.strip()
        ap = res.find(ns + "arquivoPagamento")
        if ap is not None and ap.text:
            out["arquivoPagamento"] = ap.text.strip()
    return out

def parse_result_status(soap_xml: str) -> Dict[str, Optional[str]]:
    import xml.etree.ElementTree as ET
    ns = "{http://www.gnre.pe.gov.br}"
    raise_on_soap_fault(soap_xml)
    xml = extract_xml_from_soap(soap_xml)
    root = ET.fromstring(xml)
    if not root.tag.endswith("TResultLote_GNRE"):
        raise GNREError("Resposta inesperada: elemento raiz não é TResultLote_GNRE")
    nr = root.find(ns + "numeroRecibo")
    recibo = nr.text.strip() if nr is not None and nr.text else None
    sit = root.find(ns + "situacaoProcess")
    codigo = sit.find(ns + "codigo").text.strip() if sit is not None and sit.find(ns + "codigo") is not None and sit.find(ns + "codigo").text else None
    descricao = sit.find(ns + "descricao").text.strip() if sit is not None and sit.find(ns + "descricao") is not None and sit.find(ns + "descricao").text else None
    if codigo and codigo not in {"402", "401"}:
        details = parse_tresult_lote(soap_xml)
        raise GNREError("Processamento retornou erro", codigo=codigo, descricao=descricao, recibo=recibo, raw_xml=xml, details=details)
    return {"numeroRecibo": recibo, "codigo": codigo, "descricao": descricao}

def extract_linha_digitavel_and_pdf(soap_xml: str) -> Dict[str, Optional[str]]:
    data = parse_tresult_lote(soap_xml)
    sit = data.get("situacao") or {}
    codigo = (sit.get("codigo") or "").strip() if sit else ""
    if codigo != "402":
        raise GNREError("Guia não processada com sucesso", codigo=codigo, descricao=(sit.get("descricao") if sit else None), recibo=data.get("numeroRecibo"), raw_xml=extract_xml_from_soap(soap_xml), details=data)
    guia = (data.get("guias") or [{}])[0]
    return {
        "linhaDigitavel": guia.get("linhaDigitavel"),
        "pdfBase64": data.get("pdfGuias"),
        "numeroRecibo": data.get("numeroRecibo"),
        "valor": guia.get("valor"),
        "dataVencimento": guia.get("dataVencimento"),
    }
def parse_config_uf(soap_xml: str) -> Dict[str, any]:
    import xml.etree.ElementTree as ET
    ns = "{http://www.gnre.pe.gov.br}"
    xml = extract_xml_from_soap(soap_xml)
    root = ET.fromstring(xml)
    out = {
        "uf": None,
        "receitas": {},
        "exigeUfFavorecida": None,
        "exigeReceita": None,
    }
    def txt(el):
        return el.text.strip() if el is not None and el.text else None
    if not root.tag.endswith("TConfigUf"):
        return out
    uf = root.find(ns + "uf")
    out["uf"] = txt(uf)
    exUf = root.find(ns + "exigeUfFavorecida")
    out["exigeUfFavorecida"] = exUf.get("campo") if exUf is not None else None
    exRec = root.find(ns + "exigeReceita")
    out["exigeReceita"] = exRec.get("campo") if exRec is not None else None
    recs = root.find(ns + "receitas")
    if recs is not None:
        for r in recs.findall(ns + "receita"):
            code = r.get("codigo")
            info = {
                "descricao": r.get("descricao"),
                "exigeDocumentoOrigem": txt(r.find(ns + "exigeDocumentoOrigem")) == "S",
                "tiposDocumentosOrigem": [txt(td.find(ns + "codigo")) for td in (r.find(ns + "tiposDocumentosOrigem") or ET.Element("x")).findall(ns + "tipoDocumentoOrigem")],
                "exigeContribuinteDestinatario": txt(r.find(ns + "exigeContribuinteDestinatario")) == "S",
                "exigeDataVencimento": txt(r.find(ns + "exigeDataVencimento")) == "S",
                "exigeDataPagamento": txt(r.find(ns + "exigeDataPagamento")) == "S",
            }
            out["receitas"][code] = info
    return out
