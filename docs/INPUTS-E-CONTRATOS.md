# Inputs, outputs e integração — dados 1.0 / backend 2.0

## 1. Entrada principal do projeto de dados

`POST /v1/context`, JSON, header `X-API-Key` obrigatório (mínimo de 24 caracteres configurado no servidor).

| Campo | Tipo | Obrigatório | Regra |
|---|---|---|---|
| latitude | número | sim | -90 a 90; graus decimais WGS84 |
| longitude | número | sim | -180 a 180; graus decimais WGS84 |
| radius_km | número | não | padrão 10; intervalo 1 a 50 |
| days | inteiro | não | padrão 1; intervalo 1 a 5; janela NASA |

Campos desconhecidos, NaN, infinito e coordenadas fora do intervalo são rejeitados. Não enviar nome, CPF, senha, telefone ou ID de agricultor ao provedor. A geolocalização do agricultor precisa de autorização no frontend; o serviço recebe coordenadas já autorizadas pelo backend.

## 2. Envelope de cada fonte

| Campo | Significado |
|---|---|
| schema_version | versão do envelope: 1.0 |
| source | provedor/sensor ou identificação DEMO |
| simulated | true somente no modo demo |
| status | ok, stale ou unavailable |
| observed_at | horário UTC da referência meteorológica ou foco mais recente; null quando não há referência |
| fetched_at | horário UTC em que a resposta foi coletada/gerada; permanece original ao ler cache |
| data | objeto meteorológico, lista de focos ou null em falha |
| warnings | limitações legíveis que devem acompanhar a visualização |

`status=ok` significa consulta válida; não certifica segurança da região nem atualidade de cada foco. Em meteorologia, referência com mais de três horas recebe `stale`. Focos preservam a data de aquisição de cada item e devem ser exibidos com a janela consultada. Lista vazia `[]` é diferente de `null` indisponível. Não converter indisponibilidade em zero focos ou risco baixo.

### Mapeamento meteorológico

| Open-Meteo current | Campo normalizado | Unidade |
|---|---|---|
| temperature_2m | temperature_c | °C |
| relative_humidity_2m | humidity_pct | % |
| wind_speed_10m | wind_kmh | km/h |
| wind_direction_10m | wind_direction_deg | graus |
| precipitation | precipitation_mm | mm, no intervalo da referência do provedor |
| time | observed_at | UTC; consulta em GMT |

Open-Meteo fornece saída de modelo meteorológico, não uma estação instalada no imóvel.

### Mapeamento NASA FIRMS

| CSV NASA | Campo normalizado | Observação |
|---|---|---|
| latitude / longitude | latitude / longitude | graus decimais |
| acq_date + acq_time | observed_at | UTC; hora HHMM |
| confidence | confidence | l → low; n → nominal; h → high |
| frp | frp_mw | potência radiativa em MW, não hectares |
| calculado | id | hash do sensor, coordenadas e aquisição |
| calculado | distance_km | Haversine, distância ao ponto consultado |

Não é uma interseção com o polígono da propriedade. A caixa inicial é conservadora; o filtro final usa raio esférico. Duplicatas exatas de sensor/coordenadas/tempo são removidas. Confiança VIIRS não é convertida em porcentagem inventada. Consulta que cruza o antimeridiano retorna indisponibilidade explícita nesta versão.

### Risco

`risk.level=null`, `method=null`, `validated=false`. Um indicador não foi inventado a partir da temperatura ou contagem de focos. Adotar uma fonte oficial ou método validado é uma etapa separada.

## 3. Inputs do backend mobile — versão 2.0

### Login e sessão

`POST /v1/auth/login`, JSON:

```json
{"username":"coop.admin","password":"SENHA_ESCOLHIDA_POR_VOCE"}
```

Resposta: `access_token`, `refresh_token`, `token_type=bearer`, `expires_in=900`, `refresh_expires_in=2592000`, `role`, `must_change_password`. Guardar tokens no armazenamento seguro do aparelho. Não enviar `role` no login.

`POST /v1/auth/refresh`, sem access token obrigatório:

```json
{"refresh_token":"TOKEN_RECEBIDO_NO_LOGIN_OU_NA_ULTIMA_RENOVACAO"}
```

Retorna um novo par e invalida o anterior. Refresh tem validade absoluta de 30 dias a partir do login; a resposta informa os segundos restantes. Fazer somente uma renovação por vez. Reutilizar refresh antigo revoga a sessão. Após perda da resposta de renovação, pode ser necessário novo login.

`POST /v1/auth/password`, Bearer e JSON:

```json
{"old_password":"SENHA_ATUAL","new_password":"NOVA_SENHA_COM_12_OU_MAIS_CARACTERES"}
```

A nova senha deve ter 12–128 caracteres e ser diferente. Essa operação revoga todas as sessões. Fazer novo login. `POST /v1/auth/logout` com access token válido revoga a sessão atual, incluindo refresh.

### Cadastro de agricultor

`POST /v1/farmers`, Bearer de cooperativa:

```json
{"name":"Ana Silva","username":"ana.silva"}
```

Nome 2–120 caracteres. Username 3–80, letras ASCII/números/ponto/hífen/sublinhado, case-sensitive. Cooperativa determinada no servidor. Não coleta CPF. Retorna ID, senha temporária e troca obrigatória.

### Propriedade

`POST /v1/properties`, Bearer de cooperativa:

```json
{"farmer_id":"ID_DO_AGRICULTOR","name":"Sítio Esperança","municipality":"Campinas","state":"SP","latitude":-22.9,"longitude":-47.06,"area_ha":12.5}
```

Farmer, município, UF e coordenadas obrigatórios. Nome/área opcionais; área não negativa. PostgreSQL deriva o ponto PostGIS das coordenadas. O ponto não representa um polígono territorial verificado.

`GET /v1/properties/nearby?latitude=-22.9&longitude=-47.06&radius_m=10000` exige cooperativa. Raio entre 1 e 50.000 metros. Retorna até 200 propriedades dessa cooperativa, ordenadas por `distance_m`, com `id`, `name`, latitude e longitude. Não retorna propriedades de outras cooperativas.

### Ocorrência — multipart/form-data

`POST /v1/incidents`, Bearer de agricultor. Dois campos:

| Campo multipart | Tipo | Conteúdo |
|---|---|---|
| metadata | texto JSON | dados abaixo, até 10.000 caracteres |
| photo | arquivo binário | JPEG ou PNG, até 3 MB e 12 milhões de pixels |

Exemplo de `metadata`:

```json
{
  "client_request_id":"86a0de74-5b4b-4263-98a1-b1b77d415d16",
  "property_id":"ID_DA_PROPRIEDADE",
  "description":"Fumaça observada ao longe",
  "latitude":-22.9,
  "longitude":-47.06,
  "location_source":"gps",
  "location_authorized":true
}
```

| Campo metadata | Regra |
|---|---|
| client_request_id | UUID obrigatório, criado e persistido pelo app antes do primeiro envio |
| property_id | propriedade do agricultor autenticado |
| description | opcional, até 2.000 caracteres |
| latitude/longitude | ambas presentes ou ambas ausentes |
| location_source | gps, manual ou unavailable |
| location_authorized | true quando houver coordenadas GPS/manuais |

Sem localização, omitir latitude/longitude e usar `unavailable`/`false`. A ausência não impede o relato. O backend determina usuário/horário, valida o arquivo real e remove EXIF. `photo_base64` não é mais aceito nesta versão.

Resposta de criação ou reenvio aceito, HTTP 201:

```json
{"id":"ID_DA_OCORRENCIA","replayed":false}
```

No reenvio idêntico, devolve o mesmo ID com `replayed=true`. Mesmo UUID com outro metadata ou outros bytes de foto retorna 409. A chave é por agricultor, portanto não há conflito entre usuários diferentes. Guardar metadata e arquivo comprimido de forma estável na fila offline; não recomprimir nem recriar o UUID a cada tentativa.

A deduplicação usa transação, lock consultivo e restrição única no PostgreSQL, inclusive para requisições concorrentes. Não existe worker offline no servidor: o aplicativo decide quando reenviar. O GET da ocorrência mostra `location_verified=false`, análise simulada e URL de foto autenticada.

### Revisão

`PATCH /v1/incidents/{id}/review`, Bearer da cooperativa:

```json
{"status":"under_review","notes":"Registro recebido para avaliação humana."}
```

Notas 5–2.000 caracteres. Transições: submitted → under_review; under_review → verified ou rejected; verified → escalated. Os dois últimos estados rejected/escalated são finais. Mudanças concorrentes bloqueiam a linha da ocorrência durante a transação. `verified` é avaliação humana interna; `escalated` não envia comunicação.

## 4. Erros

| HTTP | Significado |
|---|---|
| 401 | chave/credencial/access/refresh inválido, expirado ou refresh reutilizado |
| 403 | perfil insuficiente ou senha temporária pendente |
| 404 | recurso inexistente ou não autorizado |
| 409 | username duplicado, transição inválida ou UUID reutilizado com outro conteúdo |
| 413 | corpo excede 4,1 MB |
| 422 | entrada/foto/metadata inválidos |
| 429 | limite de tentativas de login |
| 503 | serviço de dados ou arquivo privado indisponível |

Falhas de provedor no serviço de dados continuam como HTTP 200 com envelope `unavailable`, permitindo resultado parcial. Não converter falha em zero focos. Retry externo: até duas tentativas para transporte/429/5xx, timeout de 10s por operação; backend consulta dados com timeout de 25s.

## 5. Contratos OpenAPI

Ambos os projetos incluem `openapi.json`; também disponíveis em `/openapi.json` e `/docs`. O multipart documenta `metadata` como string JSON; seu schema separado está em `backend-reserva/incident-metadata.schema.json`. Algumas saídas de dicionários livres do backend são descritas neste guia.
