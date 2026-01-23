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

Exemplo de fluxo completo: gerar XML do lote, enviar, consultar resultado e salvar o PDF.

```python
from pathlib import Path
import base64
from gnre_automacao import (
    parse_nfe_xml_bytes, evaluate_gnre_need, build_lote_xml, build_soap_envelope_tlote,
    post_soap, get_endpoints, parse_tr_ret_lote,
    build_consulta_resultado_xml, build_soap_envelope,
    parse_result_status, extract_linha_digitavel_and_pdf, GNREError
)
from datetime import datetime, timedelta

pfx_bytes = Path("certificado.pfx").read_bytes()
pfx_password = "SENHA_DO_CERTIFICADO"
nfe_bytes = Path("nfe.xml").read_bytes()

dados = parse_nfe_xml_bytes(nfe_bytes)
need = evaluate_gnre_need(dados, receita=None)
if need.get("necessario") == "N":
    print("GNRE não necessária")
elif need.get("necessario") == "M":
    print("GNRE manual necessária")
else:
    venc = (datetime.now().date() + timedelta(days=7)).isoformat()
    xml_lote = build_lote_xml(
        dados,
        uf_favorecida=dados.get("uf_destinatario"),
        receita=None,
        data_vencimento=venc,
        data_pagamento=venc,
    )
    envelope = build_soap_envelope_tlote(xml_lote)
    resp_recepcao = post_soap(get_endpoints("producao")["recepcao_lote"], envelope, pfx_bytes=pfx_bytes, pfx_password=pfx_password)
    recibo = parse_tr_ret_lote(resp_recepcao)

    cons_xml = build_consulta_resultado_xml("1", recibo, incluir_pdf=True, incluir_arquivo_pagamento=True)
    env_consulta = build_soap_envelope("GnreResultadoLote", cons_xml)
    resp_resultado = post_soap(get_endpoints("producao")["resultado_lote"], env_consulta, pfx_bytes=pfx_bytes, pfx_password=pfx_password)

    status = parse_result_status(resp_resultado)
    print(status["numeroRecibo"], status["codigo"], status["descricao"])

    # se a guia ainda estiver sendo processada, ou houver algum problema, uma exceção é lançada
    # try/except pode ser usado para consultar se a guia já foi processada a cada x tempo
    try:
        out = extract_linha_digitavel_and_pdf(resp_resultado)
        print("Linha digitável:", out.get("linhaDigitavel"))
        print("Valor:", out.get("valor"))
        print("Vencimento:", out.get("dataVencimento"))
        pdf_b64 = out.get("pdfBase64")
        if pdf_b64:
            Path("gnre_guia.pdf").write_bytes(base64.b64decode(pdf_b64))
    except GNREError:
        # tentar de novo em alguns segundos
        # tentativas terminadas:
        raise
```

## Principais funções
- `parse_nfe_xml_bytes(bytes)` — extrai dados relevantes da NF-e
- `evaluate_gnre_need(dados, receita=None)` — avalia necessidade de GNRE; quando a UF do emitente for diferente da UF do destinatário e a UF de destino for SP ou ES, retorna `necessario = "M"` (manual) somente se houver valor > 0; caso valor seja zero, retorna `necessario = "N"`
- `build_lote_xml(...)` — monta o XML do lote GNRE
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
- É obrigatório cadastrar o CNPJ no portal GNRE antes de utilizar os serviços: https://www.gnre.pe.gov.br:444/gnre/portal/GNRE_Principal.jsp
