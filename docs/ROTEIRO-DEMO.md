# Roteiro de demonstração — versão mobile/PostgreSQL

## 1. Preparação

Configure `.env` na raiz com senhas geradas e `DATA_MODE=demo`. Execute `docker compose up --build -d`, confira `docker compose logs migrate` e crie o representante com o comando do README. Não é necessário app mobile pronto para exercitar as APIs; use Swagger.

## 2. Sua entrega principal

Em `http://127.0.0.1:8001/docs`, consulte `/health`, depois `POST /v1/context` com a chave interna e `{"latitude":-22.9,"longitude":-47.06,"radius_km":10,"days":1}`. Mostre fonte, horário, `simulated=true` e risco não calculado. Teste coordenada inválida (422) e chave ausente (401).

Para clima real, configure live e recrie dados. A NASA exige a chave da equipe. Zero focos é resposta de consulta, não confirmação de ausência de fogo. Não exibir credenciais na apresentação.

## 3. Jornada do backend

1. Abra `http://127.0.0.1:8000/docs` e `/health`; confira storage PostgreSQL e versão PostGIS.
2. Faça login como representante e autorize com access token.
3. Troque a senha inicial, faça novo login e atualize a autorização.
4. Cadastre Ana Silva (`POST /v1/farmers`), guardando ID e senha temporária.
5. Cadastre a propriedade, usando latitude -22.9/longitude -47.06.
6. Consulte `/v1/properties/nearby` no mesmo ponto com raio de 1.000 metros.
7. Faça login como Ana, troque a senha e faça novo login.
8. Consulte sua propriedade e o ambiente.
9. Em `POST /v1/incidents`, cole o JSON abaixo em `metadata` e selecione uma foto real JPEG/PNG no campo `photo`.

```json
{"client_request_id":"86a0de74-5b4b-4263-98a1-b1b77d415d16","property_id":"SUBSTITUIR_PELO_ID","description":"Registro de demonstração","location_source":"unavailable","location_authorized":false}
```

10. Reenvie os mesmos campos e arquivo. Deve retornar o mesmo ID, `replayed=true`.
11. Com o mesmo UUID, altere a descrição. Deve retornar 409, sem duplicar a ocorrência.
12. Teste refresh: copie o refresh atual e use `/v1/auth/refresh`. Atualize o access token na autorização. Não reutilize o refresh antigo, exceto em um teste intencional de revogação.
13. Faça login novamente como representante. Revise a ocorrência: under_review → verified → escalated.
14. Consulte resumo, foto autenticada e minuta. Não há envio externo.
15. Consulte SOS: `automatic_dispatch=false`.

### Exemplo curl multipart

Salve o JSON em `metadata.json`, use o ID correto da propriedade e uma foto de até 3 MB:

```bash
curl -X POST http://127.0.0.1:8000/v1/incidents \
  -H "Authorization: Bearer $TOKEN_AGRICULTOR" \
  --form-string "metadata=$(cat metadata.json)" \
  -F 'photo=@foto.jpg;type=image/jpeg'
```

Não definir manualmente Content-Type multipart no aplicativo: o runtime precisa gerar o boundary.

## 4. Passagem ao responsável mobile

Entregar OpenAPI, schema de metadata e `examples/expo-client.ts`. Confirmar URL de desenvolvimento, permissões de câmera/GPS, compressão, armazenamento seguro de tokens, UUID persistente por relato e fila offline por usuário. Não passar credenciais do banco ou chaves de fornecedores para o app.

Para testes físicos, ler `MOBILE.md`; localhost no celular não é o computador. As telas mobile e a publicação nas lojas não foram implementadas neste pacote.
