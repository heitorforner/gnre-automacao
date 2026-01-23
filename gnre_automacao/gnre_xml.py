from __future__ import annotations
from typing import Optional, Dict
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from datetime import datetime

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

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)

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
def evaluate_gnre_need(
    dados_nfe: Dict[str, Optional[str]],
    receita: Optional[str],
    valor_principal: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    uf_dest = (dados_nfe.get("uf_destinatario") or "").strip().upper()
    uf_emit = (dados_nfe.get("uf_emitente") or "").strip().upper()
    vST_nfe = _dec(dados_nfe.get("valor_vST"))
    vICMSUF_nfe = _dec(dados_nfe.get("valor_vICMSUFDest"))
    vFCPUF_nfe = _dec(dados_nfe.get("valor_vFCPUFDest"))
    vFCPST_nfe = _dec(dados_nfe.get("valor_vFCPST"))
    r = receita or ""
    if not (r.isdigit() and len(r) == 6):
        if vICMSUF_nfe > Decimal("0"):
            r = "100102"
        elif vST_nfe > Decimal("0"):
            r = "100099"
    if valor_principal is not None:
        vprincipal = _dec(valor_principal)
    else:
        if r == "100102":
            vprincipal = vICMSUF_nfe
        elif r in {"100099", "100048"}:
            vprincipal = vST_nfe
        else:
            vprincipal = vST_nfe + vICMSUF_nfe
    vFCP_total = vFCPUF_nfe + vFCPST_nfe
    v_total_item = vprincipal + vFCP_total
    manual = (uf_dest in {"SP", "ES"} and uf_emit and uf_emit != uf_dest and v_total_item > Decimal("0"))
    return {
        "receita": None if manual else (r if r else None),
        "valor_principal": f"{vprincipal:.2f}",
        "valor_fcp": f"{vFCP_total:.2f}",
        "valor_total_item": f"{v_total_item:.2f}",
        "necessario": "M" if manual else ("S" if v_total_item > Decimal("0") else "N"),
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
    _require(bool(uf), "ufFavorecida é obrigatória")
    # mapeamento automático de receita quando solicitado
    vST_nfe = _dec(dados_nfe.get("valor_vST"))
    vICMSUF_nfe = _dec(dados_nfe.get("valor_vICMSUFDest"))
    auto_receita = False
    if not (receita and receita.isdigit() and len(receita) == 6):
        if vICMSUF_nfe > Decimal("0"):
            receita = "100102"  # DIFAL Operação
            auto_receita = True
        elif vST_nfe > Decimal("0"):
            receita = "100099"  # ST Operação
            auto_receita = True
        else:
            _require(False, "receita deve ter 6 dígitos ou ser dedutível pelos valores da NF-e")
    _require(bool(receita) and len(receita) == 6 and receita.isdigit(), "receita deve ter 6 dígitos")
    ident_ok = bool(dados_nfe.get("emitente_cnpj")) or bool(dados_nfe.get("emitente_cpf"))
    _require(ident_ok, "Emitente deve possuir CNPJ ou CPF")
    chave = (dados_nfe.get("chave_nfe") or "").strip()
    _require(bool(chave) and chave.isdigit() and 1 <= len(chave) <= 44, "documentoOrigem inválido")

    vFCPUF_nfe = _dec(dados_nfe.get("valor_vFCPUFDest"))
    vFCPST_nfe = _dec(dados_nfe.get("valor_vFCPST"))
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
        else:
            vprincipal = total_default
    # FCP: opção de somar ao principal quando aplicável (parâmetro futuro pode ajustar)
    # Aqui optamos por somar FCP ao valorGNRE apenas quando principal está zerado e há FCP
    vFCP_total = vFCPUF_nfe + vFCPST_nfe
    _require(vprincipal >= Decimal("0.00"), "valor principal inválido")
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

    doc_tipo = (doc_origem_tipo or "10").strip()
    doc = ET.SubElement(item, f"{{{GNRE_NS}}}documentoOrigem", {"tipo": doc_tipo})
    doc.text = _digits(dados_nfe.get("numero_nf") or chave)

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
    v_total_item = (vprincipal + vFCP_total)
    valor_total = ET.SubElement(item, f"{{{GNRE_NS}}}valor", {"tipo": "21"})
    valor_total.text = f"{v_total_item:.2f}"
    if vFCP_total > Decimal("0"):
        valor_fcp = ET.SubElement(item, f"{{{GNRE_NS}}}valor", {"tipo": "27"})
        valor_fcp.text = f"{vFCP_total:.2f}"

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
    if incluir_campo_107 and chave and len(_digits(chave)) == 44:
        campos = ET.SubElement(item, f"{{{GNRE_NS}}}camposExtras")
        campo = ET.SubElement(campos, f"{{{GNRE_NS}}}campoExtra")
        cod = ET.SubElement(campo, f"{{{GNRE_NS}}}codigo")
        cod.text = "107"
        val = ET.SubElement(campo, f"{{{GNRE_NS}}}valor")
        val.text = _digits(chave)

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
