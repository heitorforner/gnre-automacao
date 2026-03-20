# gnre-automacao

Biblioteca em Python para geração e envio de GNRE a partir de dados de NF-e, incluindo:
- construção de XML do lote
- montagem de envelopes SOAP
- comunicação com os webservices oficiais (produção e teste)
- parsing das respostas com extração de recibo, situação, linha digitável, valor, data de vencimento e PDF (base64)
- suporte a certificados em formato PFX

## Instalação

```bash
pip install gnre-automacao
```

## Requisitos
- Python >= 3.10
- `cryptography >= 41.0.0`

## Uso rápido

Para as UFs **PE, RJ, RO e SC**, quando há mais de um tributo a recolher (ex.: DIFAL + FCP), `emit_gnre_receipt` envia automaticamente todos os tributos em uma única guia de múltiplas receitas. Para as demais UFs, cada tributo é enviado em uma guia separada. Use `needs_multiplas_receitas` para adaptar o fluxo:

```python
from pathlib import Path
import base64
from datetime import date
from gnre_automacao import (
    parse_nfe_xml_bytes, evaluate_gnre_need,
    needs_multiplas_receitas, emit_gnre_receipt, consult_gnre_receipt,
    GNREError,
)

pfx_bytes = Path("certificado.pfx").read_bytes()
pfx_password = "SENHA_DO_CERTIFICADO"
nfe_bytes = Path("nfe.xml").read_bytes()
AMBIENTE = "1"  # "1" = produção, "2" = teste

dados = parse_nfe_xml_bytes(nfe_bytes)
need = evaluate_gnre_need(dados, receita=None)

if need.get("necessario") == "N":
    print("GNRE não necessária")
elif need.get("necessario") == "M":
    print("GNRE manual necessária (SP/ES)")
else:
    venc = date.today().isoformat()
    guias = need.get("guias") or []
    recibos = []

    if needs_multiplas_receitas(dados):
        # PE, RJ, RO, SC com 2+ tributos: um único envio com todas as receitas
        r = emit_gnre_receipt(dados, AMBIENTE, guias[0]["receita"], venc, venc, pfx_bytes, pfx_password)
        print("múltiplas receitas:", r.get("multiplas_receitas"), "| recibo:", r.get("recibo") or r.get("error"))
        recibos.append(r)
    else:
        # Demais UFs: uma guia por receita
        for guia in guias:
            r = emit_gnre_receipt(dados, AMBIENTE, guia["receita"], venc, venc, pfx_bytes, pfx_password)
            print("receita:", guia["receita"], "| recibo:", r.get("recibo") or r.get("error"))
            recibos.append(r)

    for r in recibos:
        if not r.get("recibo"):
            continue
        result = consult_gnre_receipt(AMBIENTE, r["recibo"], pfx_bytes, pfx_password, incluir_pdf=True, incluir_arquivo_pagamento=True)
        status = result.get("status") or {}
        print(status.get("numeroRecibo"), status.get("codigo"), status.get("descricao"))
        print("Linha digitável:", result.get("linhaDigitavel"))
        print("Valor:", result.get("valor"), "| Vencimento:", result.get("dataVencimento"))
        if result.get("pdfBase64"):
            Path(f"gnre_{r['recibo']}.pdf").write_bytes(base64.b64decode(result["pdfBase64"]))
```

## Retornos e cenários

### evaluate_gnre_need
- Sucesso (quando há guias necessárias):

```json
{
  "receita": "100102",
  "valor_principal": "27.62",
  "valor_fcp": "1.92",
  "valor_total_item": "29.54",
  "necessario": "S",
  "guias": [
    { "receita": "100102", "valor": "27.62" },
    { "receita": "100129", "valor": "1.92" }
  ]
  "taxes": {
    "icms": "0.00",
    "icms_difal": "27.62",
    "icms_st": "0.00",
    "fcp": "1.92",
    "ipi": "0.00",
    "pis": "0.00",
    "cofins": "0.00",
    "ibs": "0.00",
    "cbs": "0.00",
    "total_taxes_estimation": "29.54"
  }
}
```
- Sem necessidade:

```json
{
  "receita": null,
  "valor_principal": "0.00",
  "valor_fcp": "0.00",
  "valor_total_item": "0.00",
  "necessario": "N",
  "guias": [],
  "taxes": {
    "icms": "0.00",
    "icms_difal": "0.00",
    "icms_st": "0.00",
    "fcp": "0.00",
    "ipi": "0.00",
    "pis": "0.00",
    "cofins": "0.00",
    "ibs": "0.00",
    "cbs": "0.00",
    "total_taxes_estimation": "0.00"
  }
}
```
- Necessário mas manual (SP/ES com operação interestadual):

```json
{
  "receita": null,
  "valor_principal": "27.62",
  "valor_fcp": "1.92",
  "valor_total_item": "29.54",
  "necessario": "M",
  "guias": [
    { "receita": "100102", "valor": "27.62" },
    { "receita": "100129", "valor": "1.92" }
  ],
  "taxes": {
    "icms": "0.00",
    "icms_difal": "27.62",
    "icms_st": "0.00",
    "fcp": "1.92",
    "ipi": "0.00",
    "pis": "0.00",
    "cofins": "0.00",
    "ibs": "0.00",
    "cbs": "0.00",
    "total_taxes_estimation": "29.54"
  }
}
```

### emit_gnre_receipt
- Sucesso (guia única):

```json
{ "receita": "100102", "recibo": "26000045455789", "multiplas_receitas": false }
```
- Sucesso (múltiplas receitas — PE/RJ/RO/SC com 2+ tributos):

```json
{ "receita": "100102", "recibo": "26000045455790", "multiplas_receitas": true }
```
- Falha de recepção (ex.: conteúdo inválido):

```json
{
  "receita": "100129",
  "recibo": null,
  "multiplas_receitas": false,
  "error": "Falha ao obter recibo de recepção",
  "recepcao_xml": "<soapenv:Envelope>...</soapenv:Envelope>"
}
```
- Exceção de validação (GNREError) com detalhes:

```json
{
  "receita": "100129",
  "multiplas_receitas": false,
  "error": "ufFavorecida é obrigatória",
  "details": { "uf_favorecida": "" }
}
```

### consult_gnre_receipt
- Sucesso (processado):

```json
{
  "recibo": "26000045455789",
  "status": { "numeroRecibo": "26000045455789", "codigo": "402", "descricao": "Lote Processado com sucesso" },
  "linhaDigitavel": "8587...4007",
  "valor": "1.92",
  "dataVencimento": "2026-02-02",
  "pdfBase64": "JVBERi0xLjQKJeLjz9MK..."
}
```
- Em processamento:

```json
{
  "recibo": "26000045455789",
  "status_error": "Guia não processada com sucesso | codigo=401 | descricao=Lote em Processamento | recibo=26000045455789 | ...",
  "resultado": {
    "numeroRecibo": "26000045455789",
    "situacao": { "codigo": "401", "descricao": "Lote em Processamento" },
    "guias": [],
    "pdfGuias": null,
    "arquivoPagamento": null
  }
}
```
- Processado com pendências (ex.: requer detalhamento):

```json
{
  "recibo": "260000...",
  "status_error": "Guia não processada com sucesso | codigo=403 | descricao=Lote Processado com pendências | ...",
  "resultado": {
    "numeroRecibo": "260000...",
    "situacao": { "codigo": "403", "descricao": "Lote Processado com pendências" },
    "guias": [ /* motivos e detalhes da pendência */ ]
  }
}
```
```

## Principais funções
- `parse_nfe_xml_bytes(bytes)` — extrai dados relevantes da NF-e
- `evaluate_gnre_need(dados, receita=None)` — avalia necessidade de GNRE; quando a UF do emitente for diferente da UF do destinatário e a UF de destino for SP ou ES, retorna `necessario = "M"` (manual) somente se houver valor > 0; caso valor seja zero, retorna `necessario = "N"`
- `needs_multiplas_receitas(dados)` — retorna `True` se a NF-e deve usar o formato de múltiplas receitas (destinatário em PE/RJ/RO/SC com 2 ou mais tributos a recolher)
- `emit_gnre_receipt(dados, ambiente, receita, data_vencimento, data_pagamento, pfx_bytes, pfx_password, ...)` — emite a guia; para PE/RJ/RO/SC com 2+ tributos, combina automaticamente todas as receitas em uma única guia e retorna `"multiplas_receitas": true`
- `consult_gnre_receipt(ambiente, recibo, pfx_bytes, pfx_password, ...)` — consulta o resultado de um recibo
- `build_lote_xml_with_config(...)` — monta o XML do lote GNRE consultando regras da UF e aplicando campos extras automaticamente
- `build_lote_xml(...)` — versão manual para montar o XML do lote GNRE (guia única)
- `build_lote_xml_multiplas_receitas(dados, uf_favorecida, guias, data_vencimento, data_pagamento, ...)` — monta o XML com múltiplas receitas num único `TDadosGNRE`; `guias` é uma lista de `{"receita": "100102", "valor": "27.62"}`
- `MULTIPLAS_RECEITAS_UFS` — `frozenset` com as UFs que usam múltiplas receitas: `{"PE", "RJ", "RO", "SC"}`
- `build_soap_envelope_tlote(xml)` — envelope SOAP para recepção de lote
- `post_soap(url, envelope_xml, ...)` — envia requisição SOAP com certificado
- `parse_tr_ret_lote(soap_xml)` — extrai número de recibo do retorno da recepção
- `build_consulta_resultado_xml(ambiente, recibo, incluir_pdf=True, incluir_arquivo_pagamento=True)` — XML de consulta de resultado
- `parse_result_status(soap_xml)` — valida situação do processamento do lote
- `extract_linha_digitavel_and_pdf(soap_xml)` — retorna `linhaDigitavel`, `valor`, `dataVencimento`, `pdfBase64`, `numeroRecibo`
- `get_endpoints(ambiente)` — URLs dos webservices para `producao` ou `teste`
- `GNREError` — exceção com `codigo`, `descricao` e `recibo` quando aplicável

## Endpoints e ambientes
Use `get_endpoints("producao")` ou `get_endpoints("teste")` para obter as URLs corretas dos serviços.

## Certificados PFX
Você pode informar `pfx_bytes` e `pfx_password` diretamente para as chamadas de webservice. O certificado e a chave são temporariamente materializados em PEM durante a sessão e limpos em seguida.

## Licença
MIT. Veja o arquivo `LICENSE`.

## Avisos
- Não comite senhas ou certificados no repositório.
- Os serviços GNRE podem ter regras específicas por UF e receita; sempre valide no ambiente de teste antes de ir para produção.
- Não funciona para as UFs SP e ES via webservice desta biblioteca.
- Para as UFs PE, RJ, RO e SC com múltiplos tributos, `emit_gnre_receipt` envia uma única guia com todas as receitas combinadas. Chame-a **uma única vez** (não em loop por guia), pois internamente já inclui todos os tributos detectados.
- É obrigatório cadastrar o CNPJ no portal GNRE antes de utilizar os serviços: https://www.gnre.pe.gov.br:444/gnre/portal/GNRE_Principal.jsp
