# gnre-automacao

Biblioteca em Python para geração e envio de GNRE e DUA-e a partir de dados de NF-e.

- Construção de XML do lote e montagem de envelopes SOAP
- Comunicação com os webservices oficiais (produção e teste)
- Parsing das respostas com extração de recibo, situação, linha digitável, valor, vencimento e PDF (base64)
- Suporte a certificados em formato PFX
- Suporte a DUA-e (Espírito Santo) com emissão, consulta e download de boleto

## Instalação

```bash
pip install gnre-automacao
```

**Requisitos:** Python >= 3.10, `cryptography >= 41.0.0`

---

## Uso rápido — roteamento automático

`generate_receipts` e `consult_receipts` encapsulam toda a lógica de roteamento: ES usa DUA-e, demais UFs usam GNRE.

`generate_receipts` segue a mesma assinatura de `emit_gnre_receipt` — recebe `receita` explicitamente e emite uma guia. Para emitir todas as guias necessárias, avalie com `evaluate_gnre_need` e itere sobre `guias`.

```python
from pathlib import Path
from datetime import date
from gnre_automacao import parse_nfe_xml_bytes, evaluate_gnre_need, generate_receipts, consult_receipts

pfx_bytes = Path("certificado.pfx").read_bytes()
pfx_password = "SENHA_DO_CERTIFICADO"
nfe_bytes = Path("nfe.xml").read_bytes()
AMBIENTE = "producao"  # ou "homologacao" / "teste"

dados = parse_nfe_xml_bytes(nfe_bytes)
need = evaluate_gnre_need(dados)
venc = date.today().isoformat()

# Emite uma guia por receita (roteamento automático: ES → DUA-e, demais → GNRE)
results = []
for guia in need.get("guias") or []:
    r = generate_receipts(dados, AMBIENTE, guia["receita"], venc, venc, pfx_bytes, pfx_password)
    results.append(r)

receipt_numbers = [r["recibo"] for r in results if r.get("recibo")]

# Consulta (roteamento determinado automaticamente pela NF-e)
consultas = consult_receipts(nfe_bytes, receipt_numbers, AMBIENTE, pfx_bytes, pfx_password)
for c in consultas:
    print(c["source"], c["receipt_number"], c["status"], c["linhaDigitavel"])
```

Cada item retornado por `consult_receipts` contém:

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `receipt_number` | `str` | Recibo consultado |
| `source` | `str` | `"gnre"` ou `"dua_es"` |
| `status` | `dict\|None` | Dict com `codigo` e `descricao` |
| `linhaDigitavel` | `str\|None` | Código de barras para pagamento |
| `valor` | `str\|None` | Valor da guia |
| `dataVencimento` | `str\|None` | Data de vencimento |
| `pdfBase64` | `str\|None` | PDF em base64 (GNRE e DUA-e) |
| `raw` | `dict` | Resposta completa do serviço |
| `error` | `str` | Presente apenas em caso de falha na consulta |
| `pdfError` | `str` | Presente apenas se o download do PDF falhar (DUA-e) |

---

## Uso direto — GNRE (todas as UFs exceto SP e ES)

`evaluate_gnre_need` determina se a guia é necessária. O campo `necessario` retorna:

- `"N"` — nenhuma guia necessária
- `"S"` — GNRE via webservice nacional
- `"M"` — GNRE manual (SP não suporta webservice)
- `"D"` — DUA-e (ES usa webservice próprio)

Para as UFs **PE, RJ, RO e SC** com 2+ tributos, `emit_gnre_receipt` envia todos em uma única guia de múltiplas receitas. Para as demais, cada tributo vai em uma guia separada.

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

if need["necessario"] == "N":
    print("GNRE não necessária")
elif need["necessario"] == "M":
    print("GNRE manual necessária (SP)")
elif need["necessario"] == "D":
    print("ES: usar DUA-e (ver seção abaixo)")
else:
    venc = date.today().isoformat()
    guias = need.get("guias") or []
    recibos = []

    if needs_multiplas_receitas(dados):
        # PE, RJ, RO, SC com 2+ tributos: um único envio com todas as receitas
        r = emit_gnre_receipt(dados, AMBIENTE, guias[0]["receita"], venc, venc, pfx_bytes, pfx_password)
        recibos.append(r)
    else:
        for guia in guias:
            r = emit_gnre_receipt(dados, AMBIENTE, guia["receita"], venc, venc, pfx_bytes, pfx_password)
            recibos.append(r)

    for r in recibos:
        if not r.get("recibo"):
            continue
        result = consult_gnre_receipt(AMBIENTE, r["recibo"], pfx_bytes, pfx_password, incluir_pdf=True)
        status = result.get("status") or {}
        print(status.get("codigo"), status.get("descricao"))
        print("Linha digitável:", result.get("linhaDigitavel"))
        print("Valor:", result.get("valor"), "| Vencimento:", result.get("dataVencimento"))
        if result.get("pdfBase64"):
            Path(f"gnre_{r['recibo']}.pdf").write_bytes(base64.b64decode(result["pdfBase64"]))
```

---

## Uso direto — DUA-e (Espírito Santo)

O ES usa um webservice próprio. `emit_dua_es` já retorna o resultado completo (linha digitável, URL do boleto e PDF) sem consulta separada.

```python
from pathlib import Path
import base64
from datetime import date
from gnre_automacao import parse_nfe_xml_bytes, evaluate_gnre_need, emit_dua_es, consult_dua_es

pfx_bytes = Path("certificado.pfx").read_bytes()
pfx_password = "SENHA_DO_CERTIFICADO"
AMBIENTE = "producao"  # ou "homologacao"

dados = parse_nfe_xml_bytes(Path("nfe.xml").read_bytes())
need = evaluate_gnre_need(dados)

if need["necessario"] == "D":
    venc = date.today().isoformat()
    for guia in need.get("guias") or []:
        result = emit_dua_es(dados, guia["receita"], AMBIENTE, pfx_bytes, pfx_password, data_vencimento=venc)
        print("nDua:", result["recibo"])
        print("Linha digitável:", result["linhaDigitavel"])
        print("Boleto URL:", result["boletoUrl"])
        if result.get("pdfBase64"):
            Path(f"dua_{result['recibo']}.pdf").write_bytes(base64.b64decode(result["pdfBase64"]))
```

#### Consulta de DUA-e emitida

```python
result = consult_dua_es(n_dua, cnpj_emitente, AMBIENTE, pfx_bytes, pfx_password)
inf = result.get("dua", {}).get("infDUAe", {})
print("Situação pagamento:", inf.get("pgto", {}).get("cPgto"))  # "0" = pendente
print("Valor total:", inf.get("valor", {}).get("vTot"))
```

---

## Retornos de referência

### evaluate_gnre_need

```json
{
  "necessario": "S",
  "receita": "100102",
  "valor_principal": "27.62",
  "valor_fcp": "1.92",
  "valor_total_item": "29.54",
  "guias": [
    { "receita": "100102", "valor": "27.62" },
    { "receita": "100129", "valor": "1.92" }
  ],
  "taxes": {
    "icms": "0.00", "icms_difal": "27.62", "icms_st": "0.00",
    "fcp": "1.92", "ipi": "0.00", "pis": "0.00", "cofins": "0.00",
    "ibs": "0.00", "cbs": "0.00", "total_taxes_estimation": "29.54"
  }
}
```

### emit_gnre_receipt

```json
{ "receita": "100102", "recibo": "26000045455789", "multiplas_receitas": false }
```

### consult_gnre_receipt

```json
{
  "recibo": "26000045455789",
  "status": { "numeroRecibo": "26000045455789", "codigo": "402", "descricao": "Lote Processado com sucesso" },
  "linhaDigitavel": "8587...4007",
  "valor": "1.92",
  "dataVencimento": "2026-02-02",
  "pdfBase64": "JVBERi0xLjQK..."
}
```

### emit_dua_es

```json
{
  "recibo": "4024341561",
  "status": { "codigo": "105", "descricao": "Dua emitido com sucesso" },
  "linhaDigitavel": "xxxxxxxxx",
  "valor": "45.00",
  "dataVencimento": "2026-03-31",
  "boletoUrl": "https://internet.sefaz.es.gov.br/agenciavirtual/area_publica/e-dua/views/imprimir-dua.php?numDua=xxxxxxx&codCpfCnpjPessoa=xxxxx",
  "pdfBase64": "JVBERi0x...",
  "receita": "100102",
  "cServ": "3867"
}
```

---

## Principais funções

### Roteamento automático
- `generate_receipts(dados, ambiente, receita, data_vencimento, data_pagamento, pfx_bytes, pfx_password, ...)` — emite uma guia: ES → DUA-e, demais → GNRE
- `consult_receipts(nfe_bytes, receipt_numbers, ambiente, pfx_bytes, pfx_password)` — consulta com roteamento automático

### GNRE
- `parse_nfe_xml(path)` / `parse_nfe_xml_bytes(bytes)` — extrai dados relevantes da NF-e
- `evaluate_gnre_need(dados, receita=None)` — avalia necessidade de guia
- `needs_multiplas_receitas(dados)` — `True` se UF destino em PE/RJ/RO/SC com 2+ tributos
- `emit_gnre_receipt(dados, ambiente, receita, data_vencimento, data_pagamento, pfx_bytes, pfx_password)` — emite a guia
- `consult_gnre_receipt(ambiente, recibo, pfx_bytes, pfx_password, incluir_pdf=True, ...)` — consulta resultado
- `generate_gnre_receipts(dados, ambiente, data_vencimento, data_pagamento, pfx_bytes, pfx_password)` — emite todas as guias GNRE

### DUA-e (ES)
- `emit_dua_es(dados, receita, ambiente, pfx_bytes, pfx_password, data_vencimento, ...)` — emite um DUA-e
- `consult_dua_es(n_dua, cnpj, ambiente, pfx_bytes, pfx_password)` — consulta DUA emitido
- `generate_dua_es_receipts(dados, ambiente, pfx_bytes, pfx_password, data_vencimento, ...)` — emite todos os DUAs necessários
- `download_boleto_html_dua_es(n_dua, cpf_cnpj_pes, timeout=15)` — baixa HTML do boleto público (sem certificado)
- `get_boleto_url_dua_es(n_dua, cpf_cnpj_pes)` — retorna URL pública do boleto
- `consult_area_servico_dua_es(cnpj_org, ambiente, pfx_bytes, pfx_password)` — consulta áreas/serviços disponíveis
- `consult_municipio_dua_es(ambiente, pfx_bytes, pfx_password)` — consulta códigos de município

### Baixo nível
- `build_lote_xml_with_config(...)` — XML do lote com regras da UF
- `build_lote_xml(...)` — XML do lote (guia única)
- `build_lote_xml_multiplas_receitas(...)` — XML com múltiplas receitas (PE/RJ/RO/SC)
- `MULTIPLAS_RECEITAS_UFS` — `frozenset{"PE", "RJ", "RO", "SC"}`
- `build_soap_envelope_tlote(xml)` — envelope SOAP para recepção de lote
- `post_soap(url, envelope_xml, ...)` — requisição SOAP com certificado
- `parse_tr_ret_lote(soap_xml)` — extrai número de recibo do retorno
- `build_consulta_resultado_xml(ambiente, recibo, incluir_pdf=True, ...)` — XML de consulta de resultado
- `get_endpoints(ambiente)` — URLs dos webservices GNRE (`producao` ou `teste`)
- `GNREError` — exceção com `codigo`, `descricao` e `recibo` quando aplicável

---

## Endpoints e ambientes

| Serviço | Parâmetro `ambiente` |
|---------|----------------------|
| GNRE nacional | `"producao"` / `"teste"` → `get_endpoints(ambiente)` |
| DUA-e ES | `"producao"` / `"homologacao"` → `get_dua_es_endpoints(ambiente)` |

O roteamento automático (`generate_receipts` / `consult_receipts`) aceita qualquer um dos valores acima e repassa ao serviço correto.

## Certificados PFX

Informe `pfx_bytes` e `pfx_password` diretamente. O certificado é temporariamente materializado em PEM durante a requisição e removido em seguida. Nunca persista ou logue os bytes do certificado.

## Avisos

- SP não suporta webservice nacional — requer GNRE manual (`necessario="M"`).
- ES usa o webservice DUA-e próprio — não usa o webservice GNRE nacional (`necessario="D"`).
- Para RJ e RO com múltiplos tributos, chame `emit_gnre_receipt` **uma única vez** — ela já inclui todos os tributos detectados internamente.
- O CNPJ deve estar cadastrado no portal GNRE antes de usar os serviços GNRE.
- Para DUA-e ES, não é necessário cadastro prévio.
- Não comite senhas ou certificados no repositório.
- Sempre valide no ambiente de teste antes de ir para produção.

### Erros transientes de webservice estadual (código 703)

O erro 703 com `situacaoGuia=3` indica que o portal GNRE nacional recebeu o lote mas não conseguiu concluir a validação com o serviço da UF no momento. Pode ocorrer por:

- **Falha de comunicação** entre o portal nacional e o webservice da UF (`"Falha na comunicacao com o serviço da UF"`)
- **Resposta inválida** do webservice estadual (`"Falha na validacao do retorno da UF: ..."`)

Nesses casos, **não gere uma nova guia** — o recibo já existe no sistema e uma nova emissão geraria duplicata. A ação correta é retentar `consult_gnre_receipt` com o mesmo recibo até receber uma resposta definitiva:

- `situacaoGuia=1` — aprovada (guia disponível para pagamento)
- `situacaoGuia=2` — rejeitada definitivamente (gere nova guia corrigindo os erros apontados)
- `situacaoGuia=3` — ainda pendente (retente a consulta mais tarde)

## Dicas de depuração

Para inspecionar a estrutura de XML esperada por uma UF/receita específica, use o gerador oficial do portal GNRE, gere a guia manualmente e compare o XML resultante com o produzido pela biblioteca:

https://www.gnre.pe.gov.br:444/gnre/v/lote/gerar#

## Licença

MIT. Veja o arquivo `LICENSE`.
