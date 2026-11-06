# Projeto principal — dados e inputs de APIs

Este projeto pode ser entregue sozinho. Recebe coordenadas do backend, consulta fontes externas e devolve um contrato estável, sem conhecer usuários, senhas ou propriedades. O backend consumidor verifica se o usuário tem acesso às coordenadas consultadas.

## Instalação local — Python 3.12

Execute dentro desta pasta:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DATA_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DATA_MODE=demo
python -m uvicorn dados.main:create_app --factory --host 127.0.0.1 --port 8001
```

Guarde a chave gerada para configurar o backend. No PowerShell, ative com `.venv\Scripts\Activate.ps1` e use `$env:DATA_API_KEY = "sua-chave-com-pelo-menos-24-caracteres"` e `$env:DATA_MODE = "demo"` em vez de `export`. O app **não carrega `.env` automaticamente**; use variáveis de ambiente ou Compose.

Abra http://127.0.0.1:8001/docs. Em cada rota protegida, preencha `x-api-key`. Exemplo no terminal, enquanto o servidor roda em outro terminal com a mesma chave configurada:

```bash
curl -X POST http://127.0.0.1:8001/v1/context \
  -H "X-API-Key: $DATA_API_KEY" -H 'Content-Type: application/json' \
  -d '{"latitude":-22.9,"longitude":-47.06,"radius_km":10,"days":1}'
```

## Modos

- `DATA_MODE=demo`: respostas fictícias, fixas e identificadas, com data de referência 01/01/2026. Funciona sem internet. Nenhum modelo de IA é executado.
- `DATA_MODE=live`: tenta Open-Meteo e NASA FIRMS. É o padrão do código caso a variável seja omitida. Sem chave NASA, clima pode funcionar e focos ficam indisponíveis. Falha nunca ativa simulação automaticamente.

Para dados reais, reinicie o serviço com `DATA_MODE=live` e `FIRMS_MAP_KEY` obtida por você em https://firms.modaps.eosdis.nasa.gov/api/. A chave interna `DATA_API_KEY` é diferente da chave NASA. Não registrar URLs completas do FIRMS em logs: elas contêm a chave.

## Rotas

| Método | Rota | Entrada | Saída |
|---|---|---|---|
| GET | /health | nenhuma | modo e versão do contrato |
| POST | /v1/context | Location JSON | clima, focos e risco não calculado |
| POST | /v1/weather | Location JSON | envelope de clima |
| POST | /v1/hotspots | Location JSON | envelope de focos |

As rotas específicas reutilizam a consulta de contexto; na versão atual podem consultar ambos os provedores. Cache de até 256 consultas, por 5 minutos, apenas quando ambas as fontes respondem `ok`. Cache em memória, por processo; reiniciar limpa o cache. As coordenadas não são gravadas em banco neste serviço.

## Arquivos

- `dados/models.py`: validações e contrato tipado.
- `dados/providers.py`: HTTP externo, CSV NASA, deduplicação e distância.
- `dados/main.py`: rotas, chave de serviço, modo e cache.
- `tests/test_data.py`: testes sem dependência de internet.
- `openapi.json`: contrato gerado pelo FastAPI, importável no Postman.
- `example-context.json`: exemplo real da saída do modo demo.
- `requirements.txt`: versões diretas fixadas da implementação testada.

## Testar

```bash
python -m pytest tests -q
```

Os testes usam respostas controladas; não consomem sua cota NASA. As dependências transitivas não estão totalmente travadas: para uma entrega de produção gere um lock completo em CI.

## Fontes verificadas na elaboração

- Open-Meteo: https://open-meteo.com/en/docs
- NASA FIRMS Area: https://firms.modaps.eosdis.nasa.gov/api/area
- NASA, uso da API: https://firms.modaps.eosdis.nasa.gov/content/academy/data_api/firms_api_use.html

A implementação usa apenas `VIIRS_SNPP_NRT`, janela de 1 a 5 dias e caixa `west,south,east,north`. A filtragem final usa distância ao ponto da propriedade. Verificar termos, atribuição, cobertura e cotas antes de uso público/comercial. Não foi implementado conector INPE ou MapBiomas.
