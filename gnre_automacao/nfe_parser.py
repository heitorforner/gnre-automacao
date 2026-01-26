from __future__ import annotations
from typing import Dict, Optional
import xml.etree.ElementTree as ET
from datetime import datetime

NFE_NS = "{http://www.portalfiscal.inf.br/nfe}"

def _find(root: ET.Element, path: str) -> Optional[ET.Element]:
    parts = path.split("/")
    node = root
    for p in parts:
        node = node.find(NFE_NS + p)
        if node is None:
            return None
    return node

def _text(root: ET.Element, path: str) -> Optional[str]:
    el = _find(root, path)
    return el.text.strip() if el is not None and el.text is not None else None

def _parse_datetime(dt_text: Optional[str]) -> Optional[datetime]:
    if not dt_text:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_text, fmt)
        except Exception:
            continue
    return None

def _get_infNFe(root: ET.Element) -> ET.Element:
    if root.tag.endswith("nfeProc"):
        nfe = root.find(".//" + NFE_NS + "NFe")
        if nfe is None:
            raise ValueError("NFe não encontrada em nfeProc")
        inf = nfe.find(NFE_NS + "infNFe")
        if inf is None:
            raise ValueError("infNFe não encontrada")
        return inf
    if root.tag.endswith("NFe"):
        inf = root.find(NFE_NS + "infNFe")
        if inf is None:
            raise ValueError("infNFe não encontrada")
        return inf
    if root.tag.endswith("infNFe"):
        return root
    raise ValueError("Arquivo XML não parece ser uma NF-e válida")

def parse_nfe_xml(path_xml: str) -> Dict[str, Optional[str]]:
    tree = ET.parse(path_xml)
    root = tree.getroot()
    inf = _get_infNFe(root)
    ide = inf.find(NFE_NS + "ide")
    emit = inf.find(NFE_NS + "emit")
    dest = inf.find(NFE_NS + "dest")
    total = inf.find(NFE_NS + "total")

    chNFe = inf.get("Id")
    if chNFe and chNFe.startswith("NFe"):
        chNFe = chNFe[3:]

    dhEmi = _text(ide, "dhEmi") if ide is not None else None
    dEmi = _text(ide, "dEmi") if ide is not None else None
    dtEmi = _parse_datetime(dhEmi) or _parse_datetime(dEmi)
    idDest = _text(ide, "idDest") if ide is not None else None
    indFinal = _text(ide, "indFinal") if ide is not None else None
    end_dest = dest.find(NFE_NS + "enderDest") if dest is not None else None
    uf_dest = _text(dest, "UF") if dest is not None else None
    if not uf_dest and end_dest is not None:
        uf_dest = _text(end_dest, "UF")
    uf_emit = _text(emit, "UF") if emit is not None else None
    nNF = _text(ide, "nNF") if ide is not None else None
    serie = _text(ide, "serie") if ide is not None else None

    emit_cnpj = _text(emit, "CNPJ") if emit is not None else None
    emit_cpf = _text(emit, "CPF") if emit is not None else None
    emit_ie = _text(emit, "IE") if emit is not None else None
    emit_nome = _text(emit, "xNome") if emit is not None else None
    end_emit = emit.find(NFE_NS + "enderEmit") if emit is not None else None
    emit_end_lgr = _text(end_emit, "xLgr") if end_emit is not None else None
    emit_end_nro = _text(end_emit, "nro") if end_emit is not None else None
    emit_end_bairro = _text(end_emit, "xBairro") if end_emit is not None else None
    emit_end_mun = _text(end_emit, "cMun") if end_emit is not None else None
    emit_end_cep = _text(end_emit, "CEP") if end_emit is not None else None
    emit_end_fone = _text(end_emit, "fone") if end_emit is not None else None
    if not uf_emit and end_emit is not None:
        uf_emit = _text(end_emit, "UF")

    dest_cnpj = _text(dest, "CNPJ") if dest is not None else None
    dest_cpf = _text(dest, "CPF") if dest is not None else None
    dest_nome = _text(dest, "xNome") if dest is not None else None
    dest_cmun = _text(end_dest if end_dest is not None else None, "cMun")
    indIEDest = _text(dest, "indIEDest") if dest is not None else None

    icmstot = total.find(NFE_NS + "ICMSTot") if total is not None else None
    vST = _text(icmstot, "vST") if icmstot is not None else None
    vICMSUFDest = _text(icmstot, "vICMSUFDest") if icmstot is not None else None
    vFCPST = _text(icmstot, "vFCPST") if icmstot is not None else None
    vFCPUFDest = _text(icmstot, "vFCPUFDest") if icmstot is not None else None
    vICMS = _text(icmstot, "vICMS") if icmstot is not None else None
    vIPI = _text(icmstot, "vIPI") if icmstot is not None else None
    vPIS = _text(icmstot, "vPIS") if icmstot is not None else None
    vCOFINS = _text(icmstot, "vCOFINS") if icmstot is not None else None
    vIBS = _text(icmstot, "vIBS") if icmstot is not None else None
    vCBS = _text(icmstot, "vCBS") if icmstot is not None else None

    return {
        "chave_nfe": chNFe,
        "data_emissao": dtEmi.isoformat() if dtEmi else None,
        "uf_emitente": uf_emit,
        "uf_destinatario": uf_dest,
        "id_dest": idDest,
        "ind_final": indFinal,
        "ind_ie_dest": indIEDest,
        "numero_nf": nNF,
        "serie_nf": serie,
        "emitente_cnpj": emit_cnpj,
        "emitente_cpf": emit_cpf,
        "emitente_ie": emit_ie,
        "emitente_nome": emit_nome,
        "emitente_endereco": " ".join([p for p in [emit_end_lgr, emit_end_nro, emit_end_bairro] if p]),
        "emitente_cod_mun": emit_end_mun,
        "emitente_cep": emit_end_cep,
        "emitente_telefone": emit_end_fone,
        "destinatario_cnpj": dest_cnpj,
        "destinatario_cpf": dest_cpf,
        "destinatario_nome": dest_nome,
        "destinatario_cod_mun": dest_cmun,
        "valor_vST": vST,
        "valor_vICMSUFDest": vICMSUFDest,
        "valor_vFCPST": vFCPST,
        "valor_vFCPUFDest": vFCPUFDest,
        "valor_vICMS": vICMS,
        "valor_vIPI": vIPI,
        "valor_vPIS": vPIS,
        "valor_vCOFINS": vCOFINS,
        "valor_vIBS": vIBS,
        "valor_vCBS": vCBS,
        "valor_vTotTrib": _text(icmstot, "vTotTrib") if icmstot is not None else None,
    }

def parse_nfe_xml_bytes(xml_bytes: bytes) -> Dict[str, Optional[str]]:
    root = ET.fromstring(xml_bytes)
    inf = _get_infNFe(root)
    ide = inf.find(NFE_NS + "ide")
    emit = inf.find(NFE_NS + "emit")
    dest = inf.find(NFE_NS + "dest")
    total = inf.find(NFE_NS + "total")
    chNFe = inf.get("Id")
    if chNFe and chNFe.startswith("NFe"):
        chNFe = chNFe[3:]
    dhEmi = _text(ide, "dhEmi") if ide is not None else None
    dEmi = _text(ide, "dEmi") if ide is not None else None
    dtEmi = _parse_datetime(dhEmi) or _parse_datetime(dEmi)
    idDest = _text(ide, "idDest") if ide is not None else None
    indFinal = _text(ide, "indFinal") if ide is not None else None
    end_dest = dest.find(NFE_NS + "enderDest") if dest is not None else None
    uf_dest = _text(dest, "UF") if dest is not None else None
    if not uf_dest and end_dest is not None:
        uf_dest = _text(end_dest, "UF")
    uf_emit = _text(emit, "UF") if emit is not None else None
    nNF = _text(ide, "nNF") if ide is not None else None
    serie = _text(ide, "serie") if ide is not None else None
    emit_cnpj = _text(emit, "CNPJ") if emit is not None else None
    emit_cpf = _text(emit, "CPF") if emit is not None else None
    emit_ie = _text(emit, "IE") if emit is not None else None
    emit_nome = _text(emit, "xNome") if emit is not None else None
    end_emit = emit.find(NFE_NS + "enderEmit") if emit is not None else None
    emit_end_lgr = _text(end_emit, "xLgr") if end_emit is not None else None
    emit_end_nro = _text(end_emit, "nro") if end_emit is not None else None
    emit_end_bairro = _text(end_emit, "xBairro") if end_emit is not None else None
    emit_end_mun = _text(end_emit, "cMun") if end_emit is not None else None
    emit_end_cep = _text(end_emit, "CEP") if end_emit is not None else None
    emit_end_fone = _text(end_emit, "fone") if end_emit is not None else None
    if not uf_emit and end_emit is not None:
        uf_emit = _text(end_emit, "UF")
    dest_cnpj = _text(dest, "CNPJ") if dest is not None else None
    dest_cpf = _text(dest, "CPF") if dest is not None else None
    dest_nome = _text(dest, "xNome") if dest is not None else None
    dest_cmun = _text(end_dest if end_dest is not None else None, "cMun")
    indIEDest = _text(dest, "indIEDest") if dest is not None else None
    icmstot = total.find(NFE_NS + "ICMSTot") if total is not None else None
    vST = _text(icmstot, "vST") if icmstot is not None else None
    vICMSUFDest = _text(icmstot, "vICMSUFDest") if icmstot is not None else None
    vFCPST = _text(icmstot, "vFCPST") if icmstot is not None else None
    vFCPUFDest = _text(icmstot, "vFCPUFDest") if icmstot is not None else None
    vICMS = _text(icmstot, "vICMS") if icmstot is not None else None
    vIPI = _text(icmstot, "vIPI") if icmstot is not None else None
    vPIS = _text(icmstot, "vPIS") if icmstot is not None else None
    vCOFINS = _text(icmstot, "vCOFINS") if icmstot is not None else None
    vIBS = _text(icmstot, "vIBS") if icmstot is not None else None
    vCBS = _text(icmstot, "vCBS") if icmstot is not None else None
    return {
        "chave_nfe": chNFe,
        "data_emissao": dtEmi.isoformat() if dtEmi else None,
        "uf_emitente": uf_emit,
        "uf_destinatario": uf_dest,
        "id_dest": idDest,
        "ind_final": indFinal,
        "ind_ie_dest": indIEDest,
        "numero_nf": nNF,
        "serie_nf": serie,
        "emitente_cnpj": emit_cnpj,
        "emitente_cpf": emit_cpf,
        "emitente_ie": emit_ie,
        "emitente_nome": emit_nome,
        "emitente_endereco": " ".join([p for p in [emit_end_lgr, emit_end_nro, emit_end_bairro] if p]),
        "emitente_cod_mun": emit_end_mun,
        "emitente_cep": emit_end_cep,
        "emitente_telefone": emit_end_fone,
        "destinatario_cnpj": dest_cnpj,
        "destinatario_cpf": dest_cpf,
        "destinatario_nome": dest_nome,
        "destinatario_cod_mun": dest_cmun,
        "valor_vST": vST,
        "valor_vICMSUFDest": vICMSUFDest,
        "valor_vFCPST": vFCPST,
        "valor_vFCPUFDest": vFCPUFDest,
        "valor_vICMS": vICMS,
        "valor_vIPI": vIPI,
        "valor_vPIS": vPIS,
        "valor_vCOFINS": vCOFINS,
        "valor_vIBS": vIBS,
        "valor_vCBS": vCBS,
        "valor_vTotTrib": _text(icmstot, "vTotTrib") if icmstot is not None else None,
    }
