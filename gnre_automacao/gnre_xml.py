from __future__ import annotations
from typing import Optional, Dict, Any
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from datetime import datetime
import json
from pathlib import Path
from .gnre_ws import GNREError
from decimal import Decimal

GNRE_NS = "http://www.gnre.pe.gov.br"

def _digits(s: Optional[str]) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())

def _dec(value: Optional[str]) -> Decimal:
    if not value:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")

def _date_only(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except Exception:
        return None

def _require(cond: bool, msg: str, details: Optional[Dict[str, any]] = None) -> None:
    if not cond:
        raise GNREError(msg, details=details)

def _mun5(cmun: Optional[str]) -> Optional[str]:
    if not cmun:
        return None
    s = _digits(cmun)
    if len(s) == 7:
        return s[2:7]
    if len(s) == 5:
        return s
    if len(s) > 5:
        return s[-5:]
    return None
_UF_ADDITIONAL = None
def _load_additional_fields() -> Dict[str, Any]:
    global _UF_ADDITIONAL
    if _UF_ADDITIONAL is None:
        p = Path(__file__).with_name("uf_additional_fields.json")
        try:
            _UF_ADDITIONAL = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _UF_ADDITIONAL = {}
    return _UF_ADDITIONAL
def _extra_value(titulo: str, dados_nfe: Dict[str, Optional[str]]) -> Optional[str]:
    if "Chave de Acesso" in titulo:
        s = (dados_nfe.get("chave_nfe") or "")
        return _digits(s) if s else None
    if "Data de Emissão" in titulo:
        return _date_only(dados_nfe.get("data_emissao"))
    return None
_UF_DETALHAMENTO = None
def _load_detalhamento_map() -> Dict[str, Any]:
    global _UF_DETALHAMENTO
    if _UF_DETALHAMENTO is None:
        p = Path(__file__).with_name("uf_detalhamento.json")
        try:
            _UF_DETALHAMENTO = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            _UF_DETALHAMENTO = {}
    return _UF_DETALHAMENTO
def evaluate_gnre_need(
    dados_nfe: Dict[str, Optional[str]],
    receita: Optional[str],
    valor_principal: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    uf_dest = (dados_nfe.get("uf_destinatario") or "").strip().upper()
    uf_emit = (dados_nfe.get("uf_emitente") or "").strip().upper()
    id_dest = (dados_nfe.get("id_dest") or "").strip()
    ind_final = (dados_nfe.get("ind_final") or "").strip()
    ind_ie_dest = (dados_nfe.get("ind_ie_dest") or "").strip()
    vST_nfe = _dec(dados_nfe.get("valor_vST"))
    vICMSUF_nfe = _dec(dados_nfe.get("valor_vICMSUFDest"))
    vFCPUF_nfe = _dec(dados_nfe.get("valor_vFCPUFDest"))
    vFCPST_nfe = _dec(dados_nfe.get("valor_vFCPST"))
    vICMS_int = _dec(dados_nfe.get("valor_vICMS"))
    vIPI = _dec(dados_nfe.get("valor_vIPI"))
    vPIS = _dec(dados_nfe.get("valor_vPIS"))
    vCOFINS = _dec(dados_nfe.get("valor_vCOFINS"))
    vIBS = _dec(dados_nfe.get("valor_vIBS"))
    vCBS = _dec(dados_nfe.get("valor_vCBS"))
    vTotTrib = _dec(dados_nfe.get("valor_vTotTrib"))
    r = receita or ""
    is_inter = (id_dest == "2")
    is_final = (ind_final == "1")
    is_nao_contrib = (ind_ie_dest == "9")
    difal_ok = is_inter and is_final and is_nao_contrib and vICMSUF_nfe > Decimal("0")
    fcp_ok = is_inter and is_final and is_nao_contrib and vFCPUF_nfe > Decimal("0")
    st_ok = is_inter and vST_nfe > Decimal("0")
    guides = []
    if difal_ok:
        guides.append({"receita": "100102", "valor": f"{vICMSUF_nfe:.2f}"})
    if fcp_ok:
        guides.append({"receita": "100129", "valor": f"{(vFCPUF_nfe + vFCPST_nfe):.2f}"})
    if st_ok:
        guides.append({"receita": "100099", "valor": f"{vST_nfe:.2f}"})
    if not (r.isdigit() and len(r) == 6) and guides:
        r = guides[0]["receita"]
    if valor_principal is not None:
        vprincipal = _dec(valor_principal)
    else:
        if r == "100102":
            vprincipal = vICMSUF_nfe
        elif r in {"100099", "100048"}:
            vprincipal = vST_nfe
        elif r == "100129":
            vprincipal = vFCPUF_nfe + vFCPST_nfe
        else:
            vprincipal = vST_nfe + vICMSUF_nfe
    vFCP_total = vFCPUF_nfe + vFCPST_nfe
    v_total_item = vprincipal + vFCP_total
    manual = (uf_dest in {"SP", "ES"} and uf_emit and uf_emit != uf_dest and bool(guides))
    return {
        "receita": None if manual else (r if r else None),
        "valor_principal": f"{vprincipal:.2f}",
        "valor_fcp": f"{vFCP_total:.2f}",
        "valor_total_item": f"{v_total_item:.2f}",
        "necessario": "M" if manual else ("S" if bool(guides) else "N"),
        "guias": guides,
        "taxes": {
            "icms": f"{vICMS_int:.2f}",
            "icms_difal": f"{vICMSUF_nfe:.2f}",
            "icms_st": f"{vST_nfe:.2f}",
            "fcp": f"{(vFCPUF_nfe + vFCPST_nfe):.2f}",
            "ipi": f"{vIPI:.2f}",
            "pis": f"{vPIS:.2f}",
            "cofins": f"{vCOFINS:.2f}",
            "ibs": f"{vIBS:.2f}",
            "cbs": f"{vCBS:.2f}",
            "total_taxes_estimation": f"{(vTotTrib if vTotTrib > Decimal('0') else (vICMS_int + vICMSUF_nfe + vST_nfe + vFCPUF_nfe + vFCPST_nfe + vIPI + vPIS + vCOFINS + vIBS + vCBS)):.2f}",
        },
    }
def build_lote_xml(
    dados_nfe: Dict[str, Optional[str]],
    uf_favorecida: Optional[str],
    receita: str,
    detalhamento_receita: Optional[str] = None,
    produto: Optional[str] = None,
    doc_origem_tipo: Optional[str] = None,
    incluir_campo_107: bool = True,
    valor_principal: Optional[str] = None,
    data_vencimento: Optional[str] = None,
    razao_social_emitente: Optional[str] = None,
    data_pagamento: Optional[str] = None,
) -> str:
    uf = (uf_favorecida or dados_nfe.get("uf_destinatario") or "").strip()
    _require(bool(uf), "ufFavorecida é obrigatória", {"uf_favorecida": uf, "dados_nfe_uf_destinatario": dados_nfe.get("uf_destinatario")})
    # mapeamento automático de receita quando solicitado
    vST_nfe = _dec(dados_nfe.get("valor_vST"))
    vICMSUF_nfe = _dec(dados_nfe.get("valor_vICMSUFDest"))
    if not (receita and receita.isdigit() and len(receita) == 6):
        if vICMSUF_nfe > Decimal("0"):
            receita = "100102"  # DIFAL Operação
        elif vST_nfe > Decimal("0"):
            receita = "100099"  # ST Operação
        else:
            _require(False, "receita deve ter 6 dígitos ou ser dedutível pelos valores da NF-e", {"valor_vICMSUFDest": str(vICMSUF_nfe), "valor_vST": str(vST_nfe)})
    _require(bool(receita) and len(receita) == 6 and receita.isdigit(), "receita deve ter 6 dígitos", {"receita": receita})
    ident_ok = bool(dados_nfe.get("emitente_cnpj")) or bool(dados_nfe.get("emitente_cpf"))
    _require(ident_ok, "Emitente deve possuir CNPJ ou CPF", {"emitente_cnpj": dados_nfe.get("emitente_cnpj"), "emitente_cpf": dados_nfe.get("emitente_cpf")})
    chave = (dados_nfe.get("chave_nfe") or "").strip()
    _require(bool(chave) and chave.isdigit() and 1 <= len(chave) <= 44, "documentoOrigem inválido", {"chave_nfe": chave})

    vFCPUF_nfe = _dec(dados_nfe.get("valor_vFCPUFDest"))
    vFCPST_nfe = _dec(dados_nfe.get("valor_vFCPST"))
    vFCP_total = vFCPUF_nfe + vFCPST_nfe
    total_default = vST_nfe + vICMSUF_nfe  # por padrão não somar FCP sem regra explícita
    # valor principal selecionado por receita
    if valor_principal is not None:
        vprincipal = _dec(valor_principal)
    else:
        if receita == "100102":
            vprincipal = vICMSUF_nfe
        elif receita == "100099":
            vprincipal = vST_nfe
        elif receita == "100048":
            vprincipal = vST_nfe
        elif receita == "100129":
            vprincipal = vFCP_total
        else:
            vprincipal = total_default
    # FCP: opção de somar ao principal quando aplicável (parâmetro futuro pode ajustar)
    # Aqui optamos por somar FCP ao valorGNRE apenas quando principal está zerado e há FCP
    _require(vprincipal >= Decimal("0.00"), "valor principal inválido", {"valor_principal": f"{vprincipal:.2f}", "receita": receita})
    dtven = data_vencimento or _date_only(dados_nfe.get("data_emissao")) or datetime.now().date().isoformat()
    mes = dtven[5:7]
    ano = dtven[0:4]

    ET.register_namespace("", GNRE_NS)
    lote = ET.Element(f"{{{GNRE_NS}}}TLote_GNRE", {"versao": "2.00"})
    guias = ET.SubElement(lote, f"{{{GNRE_NS}}}guias")
    guia = ET.SubElement(guias, f"{{{GNRE_NS}}}TDadosGNRE", {"versao": "2.00"})

    ufFav = ET.SubElement(guia, f"{{{GNRE_NS}}}ufFavorecida")
    ufFav.text = uf

    tipo = ET.SubElement(guia, f"{{{GNRE_NS}}}tipoGnre")
    tipo.text = "0"

    contrib_emit = ET.SubElement(guia, f"{{{GNRE_NS}}}contribuinteEmitente")
    identificacao = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}identificacao")
    if dados_nfe.get("emitente_cnpj"):
        cnpj = ET.SubElement(identificacao, f"{{{GNRE_NS}}}CNPJ")
        cnpj.text = dados_nfe.get("emitente_cnpj")
    elif dados_nfe.get("emitente_cpf"):
        cpf = ET.SubElement(identificacao, f"{{{GNRE_NS}}}CPF")
        cpf.text = dados_nfe.get("emitente_cpf")
    # IE: inclui quando a UF do emitente é igual à UF favorecida, ou se for substituto tributário (param futuro)
    # aqui incluímos IE quando UF coincide; ajuste pode ser feito via param 'include_ie_substituto' (não exposto)
    if dados_nfe.get("emitente_ie") and (dados_nfe.get("uf_emitente") == uf):
        ie = ET.SubElement(identificacao, f"{{{GNRE_NS}}}IE")
        ie.text = dados_nfe.get("emitente_ie")
    if razao_social_emitente:
        razao = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}razaoSocial")
        razao.text = razao_social_emitente
    elif dados_nfe.get("emitente_nome"):
        razao = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}razaoSocial")
        razao.text = dados_nfe.get("emitente_nome")
    if dados_nfe.get("emitente_endereco"):
        end = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}endereco")
        end.text = dados_nfe.get("emitente_endereco")
    if dados_nfe.get("emitente_cod_mun"):
        mun = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}municipio")
        mun.text = _mun5(dados_nfe.get("emitente_cod_mun"))
    if dados_nfe.get("uf_emitente"):
        uf_emit = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}uf")
        uf_emit.text = dados_nfe.get("uf_emitente")
    if dados_nfe.get("emitente_cep"):
        cep = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}cep")
        cep.text = dados_nfe.get("emitente_cep")
    if dados_nfe.get("emitente_telefone"):
        tel = ET.SubElement(contrib_emit, f"{{{GNRE_NS}}}telefone")
        tel.text = dados_nfe.get("emitente_telefone")

    itens = ET.SubElement(guia, f"{{{GNRE_NS}}}itensGNRE")
    item = ET.SubElement(itens, f"{{{GNRE_NS}}}item")
    rec = ET.SubElement(item, f"{{{GNRE_NS}}}receita")
    rec.text = receita
    if detalhamento_receita:
        det = ET.SubElement(item, f"{{{GNRE_NS}}}detalhamentoReceita")
        det.text = detalhamento_receita
    if produto:
        prod = ET.SubElement(item, f"{{{GNRE_NS}}}produto")
        prod.text = produto

    doc_tipo = (doc_origem_tipo or "22").strip()
    doc = ET.SubElement(item, f"{{{GNRE_NS}}}documentoOrigem", {"tipo": doc_tipo})
    doc.text = _digits(chave) if doc_tipo in {"22", "24"} else _digits(dados_nfe.get("numero_nf") or chave)

    ref = ET.SubElement(item, f"{{{GNRE_NS}}}referencia")
    periodo = ET.SubElement(ref, f"{{{GNRE_NS}}}periodo")
    periodo.text = "0"
    mes_el = ET.SubElement(ref, f"{{{GNRE_NS}}}mes")
    mes_el.text = mes
    ano_el = ET.SubElement(ref, f"{{{GNRE_NS}}}ano")
    ano_el.text = ano

    dv = ET.SubElement(item, f"{{{GNRE_NS}}}dataVencimento")
    dv.text = dtven

    valor_princ = ET.SubElement(item, f"{{{GNRE_NS}}}valor", {"tipo": "11"})
    valor_princ.text = f"{vprincipal:.2f}"
    v_total_item = (vprincipal)
    valor_total = ET.SubElement(item, f"{{{GNRE_NS}}}valor", {"tipo": "21"})
    valor_total.text = f"{v_total_item:.2f}"

    if dados_nfe.get("destinatario_cnpj") or dados_nfe.get("destinatario_cpf"):
        dest = ET.SubElement(item, f"{{{GNRE_NS}}}contribuinteDestinatario")
        dest_id = ET.SubElement(dest, f"{{{GNRE_NS}}}identificacao")
        if dados_nfe.get("destinatario_cnpj"):
            d_cnpj = ET.SubElement(dest_id, f"{{{GNRE_NS}}}CNPJ")
            d_cnpj.text = dados_nfe.get("destinatario_cnpj")
        elif dados_nfe.get("destinatario_cpf"):
            d_cpf = ET.SubElement(dest_id, f"{{{GNRE_NS}}}CPF")
            d_cpf.text = dados_nfe.get("destinatario_cpf")
        if dados_nfe.get("destinatario_nome"):
            d_rs = ET.SubElement(dest, f"{{{GNRE_NS}}}razaoSocial")
            d_rs.text = dados_nfe.get("destinatario_nome")
        if dados_nfe.get("destinatario_cod_mun"):
            d_mun = ET.SubElement(dest, f"{{{GNRE_NS}}}municipio")
            d_mun.text = _mun5(dados_nfe.get("destinatario_cod_mun"))

    valor_gnre = ET.SubElement(guia, f"{{{GNRE_NS}}}valorGNRE")
    valor_gnre.text = f"{v_total_item:.2f}"
    if data_pagamento:
        dp = ET.SubElement(guia, f"{{{GNRE_NS}}}dataPagamento")
        dp.text = data_pagamento
    extras_map = _load_additional_fields()
    extras = []
    for e in extras_map.get(uf, []):
        if e.get("receita") == receita:
            v = _extra_value(e.get("titulo") or "", dados_nfe)
            if v:
                extras.append({"codigo": e.get("codigo"), "valor": v})
    if extras:
        campos = ET.SubElement(item, f"{{{GNRE_NS}}}camposExtras")
        for ex in extras:
            ce = ET.SubElement(campos, f"{{{GNRE_NS}}}campoExtra")
            c = ET.SubElement(ce, f"{{{GNRE_NS}}}codigo")
            c.text = str(ex["codigo"])
            vv = ET.SubElement(ce, f"{{{GNRE_NS}}}valor")
            vv.text = ex["valor"]

    xml_str = ET.tostring(lote, encoding="utf-8", xml_declaration=False)
    return xml_str.decode("utf-8")

def build_lote_consulta_xml(
    uf: str,
    tipo_consulta: str,
    doc_origem: Optional[str] = None,
    doc_tipo: Optional[str] = None,
    cod_barras: Optional[str] = None,
    num_controle: Optional[str] = None,
    emitente_cnpj: Optional[str] = None,
    emitente_cpf: Optional[str] = None,
    emitente_ie: Optional[str] = None,
) -> str:
    _require(bool(uf), "uf obrigatória")
    _require(tipo_consulta in {"C", "N", "D", "CD", "ND", "CR", "NR"}, "tipoConsulta inválido")
    ET.register_namespace("", GNRE_NS)
    lote = ET.Element(f"{{{GNRE_NS}}}TLote_ConsultaGNRE", {"versao": "2.00"})
    consulta = ET.SubElement(lote, f"{{{GNRE_NS}}}consulta")
    uf_el = ET.SubElement(consulta, f"{{{GNRE_NS}}}uf")
    uf_el.text = uf
    if emitente_cnpj or emitente_cpf or emitente_ie:
        emit = ET.SubElement(consulta, f"{{{GNRE_NS}}}emitenteId")
        if emitente_cnpj:
            cnpj = ET.SubElement(emit, f"{{{GNRE_NS}}}CNPJ")
            cnpj.text = emitente_cnpj
        if emitente_cpf:
            cpf = ET.SubElement(emit, f"{{{GNRE_NS}}}CPF")
            cpf.text = emitente_cpf
        if emitente_ie:
            ie = ET.SubElement(emit, f"{{{GNRE_NS}}}IE")
            ie.text = emitente_ie
    if cod_barras:
        cb = ET.SubElement(consulta, f"{{{GNRE_NS}}}codBarras")
        cb.text = cod_barras
    if num_controle:
        nc = ET.SubElement(consulta, f"{{{GNRE_NS}}}numControle")
        nc.text = num_controle
    if doc_origem and doc_tipo:
        do = ET.SubElement(consulta, f"{{{GNRE_NS}}}docOrigem", {"tipo": doc_tipo})
        do.text = doc_origem
    tc = ET.SubElement(consulta, f"{{{GNRE_NS}}}tipoConsulta")
    tc.text = tipo_consulta
    xml_str = ET.tostring(lote, encoding="utf-8", xml_declaration=False)
    return xml_str.decode("utf-8")

def build_consulta_resultado_xml(
    ambiente: str,
    numero_recibo: str,
    incluir_pdf: bool = True,
    incluir_arquivo_pagamento: bool = False,
    incluir_noticias: bool = False,
) -> str:
    ET.register_namespace("", GNRE_NS)
    cons = ET.Element(f"{{{GNRE_NS}}}TConsLote_GNRE")
    amb = ET.SubElement(cons, f"{{{GNRE_NS}}}ambiente")
    amb.text = ambiente
    nr = ET.SubElement(cons, f"{{{GNRE_NS}}}numeroRecibo")
    nr.text = numero_recibo
    if incluir_pdf:
        pdf = ET.SubElement(cons, f"{{{GNRE_NS}}}incluirPDFGuias")
        pdf.text = "S"
    if incluir_arquivo_pagamento:
        ap = ET.SubElement(cons, f"{{{GNRE_NS}}}incluirArquivoPagamento")
        ap.text = "S"
    if incluir_noticias:
        nt = ET.SubElement(cons, f"{{{GNRE_NS}}}incluirNoticias")
        nt.text = "S"
    xml_str = ET.tostring(cons, encoding="utf-8", xml_declaration=False)
    return xml_str.decode("utf-8")

def build_consulta_config_uf_xml(
    ambiente: str,
    uf: str,
    receita: Optional[str] = None,
    tipos_gnre: Optional[str] = None,
) -> str:
    ET.register_namespace("", GNRE_NS)
    cons = ET.Element(f"{{{GNRE_NS}}}TConsultaConfigUf")
    amb = ET.SubElement(cons, f"{{{GNRE_NS}}}ambiente")
    amb.text = ambiente
    uf_el = ET.SubElement(cons, f"{{{GNRE_NS}}}uf")
    uf_el.text = uf
    if receita:
        rec = ET.SubElement(cons, f"{{{GNRE_NS}}}receita")
        rec.text = receita
    if tipos_gnre in {"S", "N"}:
        tg = ET.SubElement(cons, f"{{{GNRE_NS}}}tiposGnre")
        tg.text = tipos_gnre
    xml_str = ET.tostring(cons, encoding="utf-8", xml_declaration=False)
    return xml_str.decode("utf-8")

def _choose_receita_with_config(dados_nfe: Dict[str, Optional[str]], config: Dict[str, Any], preferida: Optional[str]) -> Optional[str]:
    vST = _dec(dados_nfe.get("valor_vST"))
    vICMSUF = _dec(dados_nfe.get("valor_vICMSUFDest"))
    if preferida and preferida in (config.get("receitas") or {}):
        return preferida
    if vICMSUF > Decimal("0") and "100102" in (config.get("receitas") or {}):
        return "100102"
    if vST > Decimal("0") and "100099" in (config.get("receitas") or {}):
        return "100099"
    keys = list((config.get("receitas") or {}).keys())
    return keys[0] if keys else None

def _choose_doc_tipo(receita_cfg: Dict[str, Any]) -> Optional[str]:
    tipos = receita_cfg.get("tiposDocumentosOrigem") or []
    for pref in ["22", "10", "01"]:
        if pref in tipos:
            return pref
    return tipos[0] if tipos else None

def _endpoint_key(ambiente: str) -> str:
    a = (ambiente or "").strip().lower()
    if a in {"1", "producao"}:
        return "producao"
    if a in {"2", "teste"}:
        return "teste"
    raise GNREError("Ambiente inválido", details={"ambiente": ambiente})

def fetch_config_uf(ambiente: str, uf: str, pfx_bytes: Optional[bytes] = None, pfx_password: Optional[str] = None, certfile: Optional[str] = None, keyfile: Optional[str] = None) -> Dict[str, Any]:
    from .gnre_ws import build_soap_envelope, post_soap, get_endpoints, parse_config_uf
    xml = build_consulta_config_uf_xml(ambiente, uf)
    env = build_soap_envelope("GnreConfigUF", xml)
    ek = _endpoint_key(ambiente)
    return parse_config_uf(post_soap(get_endpoints(ek)["config_uf"], env, certfile=certfile, keyfile=keyfile, pfx_bytes=pfx_bytes, pfx_password=pfx_password))

def build_lote_xml_with_config(
    dados_nfe: Dict[str, Optional[str]],
    ambiente: str,
    uf_favorecida: Optional[str],
    receita: Optional[str] = None,
    detalhamento_receita: Optional[str] = None,
    produto: Optional[str] = None,
    incluir_campo_107: bool = True,
    valor_principal: Optional[str] = None,
    data_vencimento: Optional[str] = None,
    razao_social_emitente: Optional[str] = None,
    data_pagamento: Optional[str] = None,
    pfx_bytes: Optional[bytes] = None,
    pfx_password: Optional[str] = None,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> str:
    uf = (uf_favorecida or dados_nfe.get("uf_destinatario") or "").strip()
    _require(bool(uf), "ufFavorecida é obrigatória", {"uf_favorecida": uf, "dados_nfe_uf_destinatario": dados_nfe.get("uf_destinatario")})
    config = fetch_config_uf(ambiente, uf, pfx_bytes=pfx_bytes, pfx_password=pfx_password, certfile=certfile, keyfile=keyfile)
    recs = config.get("receitas") or {}
    rec_code = _choose_receita_with_config(dados_nfe, config, receita)
    _require(bool(rec_code), "receita não disponível na UF", {"uf": uf, "preferida": receita, "receitas_disponiveis": list(recs.keys())})
    rcfg = recs.get(rec_code) or {}
    doc_tipo = _choose_doc_tipo(rcfg)
    if not doc_tipo:
        doc_tipo = "24"
    exige_dest = bool(rcfg.get("exigeContribuinteDestinatario"))
    if exige_dest:
        _require(bool(dados_nfe.get("destinatario_cnpj") or dados_nfe.get("destinatario_cpf")), "Destinatário obrigatório para a receita", {"uf": uf, "receita": rec_code})
    exige_dv = bool(rcfg.get("exigeDataVencimento"))
    exige_dp = bool(rcfg.get("exigeDataPagamento"))
    dv = data_vencimento
    dp = data_pagamento
    _require(not exige_dv or bool(dv), "Data de vencimento obrigatória para a receita", {"uf": uf, "receita": rec_code})
    if exige_dp and not dp:
        dp = dv
    # Resolve detalhamento automático
    auto_det = detalhamento_receita or next((e.get("codigo") for e in (_load_detalhamento_map().get(uf) or []) if e.get("receita") == rec_code), None)
    xml = build_lote_xml(
        dados_nfe,
        uf_favorecida=uf,
        receita=rec_code,
        detalhamento_receita=auto_det,
        produto=produto,
        doc_origem_tipo=doc_tipo,
        incluir_campo_107=incluir_campo_107,
        valor_principal=valor_principal,
        data_vencimento=dv,
        razao_social_emitente=razao_social_emitente,
        data_pagamento=dp,
    )
    return xml

def generate_gnre_receipts(
    dados_nfe: Dict[str, Optional[str]],
    ambiente: str,
    data_vencimento: str,
    data_pagamento: str,
    pfx_bytes: bytes,
    pfx_password: str,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> list[Dict[str, Any]]:
    uf = (dados_nfe.get("uf_destinatario") or "").strip()
    _require(bool(uf), "ufFavorecida é obrigatória", {"uf_favorecida": uf})
    fcp_total = Decimal(str(dados_nfe.get("valor_vFCPUFDest") or "0")) + Decimal(str(dados_nfe.get("valor_vFCPST") or "0"))
    charges = [{"tipo": "principal", "receita": None}]
    if fcp_total > Decimal("0"):
        charges.append({"tipo": "fcp", "receita": "100129"})
    from .gnre_ws import build_soap_envelope_tlote, post_soap, get_endpoints, parse_tr_ret_lote, parse_result_status
    from .gnre_xml import build_consulta_resultado_xml
    from .gnre_ws import build_soap_envelope
    out = []
    ek = _endpoint_key(ambiente)
    for c in charges:
        item: Dict[str, Any] = {"tipo": c["tipo"], "recibo": None}
        try:
            xml = build_lote_xml_with_config(
                dados_nfe,
                ambiente,
                uf,
                receita=c["receita"],
                data_vencimento=data_vencimento,
                data_pagamento=data_pagamento,
                pfx_bytes=pfx_bytes,
                pfx_password=pfx_password,
                certfile=certfile,
                keyfile=keyfile,
            )
            env = build_soap_envelope_tlote(xml)
            resp = post_soap(get_endpoints(ek)["recepcao_lote"], env, pfx_bytes=pfx_bytes, pfx_password=pfx_password, certfile=certfile, keyfile=keyfile)
            recibo = parse_tr_ret_lote(resp)
            if not recibo:
                item["error"] = "Falha ao obter recibo de recepção"
                item["recepcao_xml"] = resp
            else:
                item["recibo"] = recibo
                cons_xml = build_consulta_resultado_xml(ambiente, recibo, incluir_pdf=True, incluir_arquivo_pagamento=True)
                envc = build_soap_envelope("GnreResultadoLote", cons_xml)
                res = post_soap(get_endpoints(ek)["resultado_lote"], envc, pfx_bytes=pfx_bytes, pfx_password=pfx_password, certfile=certfile, keyfile=keyfile)
                try:
                    status = parse_result_status(res)
                    item["status"] = status
                    from .gnre_ws import extract_linha_digitavel_and_pdf
                    out_extra = extract_linha_digitavel_and_pdf(res)
                    item["linhaDigitavel"] = out_extra.get("linhaDigitavel")
                    item["valor"] = out_extra.get("valor")
                    item["dataVencimento"] = out_extra.get("dataVencimento")
                    item["pdfBase64"] = out_extra.get("pdfBase64")
                except GNREError as e:
                    item["status_error"] = str(e)
                    item["resultado_xml"] = res
        except GNREError as e:
            item["error"] = str(e)
            item["details"] = getattr(e, "details", None)
        out.append(item)
    return out

def emit_gnre_receipt(
    dados_nfe: Dict[str, Optional[str]],
    ambiente: str,
    receita: str,
    data_vencimento: str,
    data_pagamento: str,
    pfx_bytes: bytes,
    pfx_password: str,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> Dict[str, Any]:
    uf = (dados_nfe.get("uf_destinatario") or "").strip()
    _require(bool(uf), "ufFavorecida é obrigatória", {"uf_favorecida": uf})
    ek = _endpoint_key(ambiente)
    item: Dict[str, Any] = {"receita": receita, "recibo": None}
    try:
        xml = build_lote_xml_with_config(
            dados_nfe,
            ambiente,
            uf,
            receita=receita,
            data_vencimento=data_vencimento,
            data_pagamento=data_pagamento,
            pfx_bytes=pfx_bytes,
            pfx_password=pfx_password,
            certfile=certfile,
            keyfile=keyfile,
        )
        from .gnre_ws import build_soap_envelope_tlote, post_soap, get_endpoints, parse_tr_ret_lote
        env = build_soap_envelope_tlote(xml)
        resp = post_soap(get_endpoints(ek)["recepcao_lote"], env, pfx_bytes=pfx_bytes, pfx_password=pfx_password, certfile=certfile, keyfile=keyfile)
        recibo = parse_tr_ret_lote(resp)
        if not recibo:
            item["error"] = "Falha ao obter recibo de recepção"
            item["recepcao_xml"] = resp
        else:
            item["recibo"] = recibo
    except GNREError as e:
        item["error"] = str(e)
        item["details"] = getattr(e, "details", None)
    return item

def consult_gnre_receipt(
    ambiente: str,
    recibo: str,
    pfx_bytes: bytes,
    pfx_password: str,
    incluir_pdf: bool = True,
    incluir_arquivo_pagamento: bool = True,
    certfile: Optional[str] = None,
    keyfile: Optional[str] = None,
) -> Dict[str, Any]:
    ek = _endpoint_key(ambiente)
    xml = build_consulta_resultado_xml(ambiente, recibo, incluir_pdf=incluir_pdf, incluir_arquivo_pagamento=incluir_arquivo_pagamento)
    from .gnre_ws import build_soap_envelope, post_soap, get_endpoints, parse_result_status, extract_linha_digitavel_and_pdf, parse_tresult_lote
    env = build_soap_envelope("GnreResultadoLote", xml)
    res = post_soap(get_endpoints(ek)["resultado_lote"], env, pfx_bytes=pfx_bytes, pfx_password=pfx_password, certfile=certfile, keyfile=keyfile)
    out: Dict[str, Any] = {"recibo": recibo}
    try:
        status = parse_result_status(res)
        out["status"] = status
        extra = extract_linha_digitavel_and_pdf(res)
        out["linhaDigitavel"] = extra.get("linhaDigitavel")
        out["valor"] = extra.get("valor")
        out["dataVencimento"] = extra.get("dataVencimento")
        out["pdfBase64"] = extra.get("pdfBase64")
    except GNREError as e:
        out["status_error"] = str(e)
        out["resultado"] = parse_tresult_lote(res)
    return out
