# Validação — versão 2, PostgreSQL/mobile

## Resultado atual

**11 testes passaram e 13 testes dependentes de PostgreSQL foram ignorados explicitamente.** Não existe comprovação de execução real do PostgreSQL/PostGIS nesta versão. Não foi possível iniciar esse serviço no ambiente, e Docker não estava disponível.

Os 14 testes aprovados na primeira entrega pertenciam ao backend SQLite anterior e **não comprovam** o backend PostgreSQL atual.

Comando local executado na raiz:

```bash
python -m pytest -q dados-api/tests backend-reserva/tests tests_integration.py
```

### 11 cenários executados

- 7 testes do serviço de dados: autenticação/validação, modo demo, normalização de provedores, deduplicação/distância/UTC, falha parcial sem simulação silenciosa, dado antigo, resultado vazio e retry.
- 4 testes locais do backend: reencodificação/remoção de EXIF e limites de imagem; armazenamento privado e bloqueio de travessia de diretório; UUID e autorização de localização; exigência de URL PostgreSQL e contrato OpenAPI multipart/refresh.

### 13 cenários preparados, não executados

- Registro/revisão de ocorrência e foto autorizada.
- Senha temporária e revogação.
- Criação e isolamento de propriedades.
- Foto/localização inválidas.
- Autenticação e falha do serviço ambiental.
- Persistência/expiração de sessões.
- PostGIS: distância, SRID e isolamento.
- Deduplicação e conflito de conteúdo.
- Refresh, reuso e logout.
- Reexecução de migração.
- Uploads simultâneos do mesmo UUID.
- Refresh após expiração do access token.
- Integração backend ↔ serviço de dados.

Para executá-los com banco real isolado:

```bash
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
```

Alternativamente, configure `TEST_DATABASE_URL` para banco exclusivo de testes e rode pytest. Cada cenário usa schema aleatório, removido ao terminar. Sem essa variável, aparece `skipped`; não interpretar como aprovado.

## Outras verificações

- Código Python compilado sem erros de sintaxe.
- OpenAPI atualizado gerado diretamente dos apps, sem conectar ao banco.
- Schema separado de metadata gerado a partir do modelo Pydantic.
- ZIP verificado e sem bancos, credenciais reais ou caches.
- O aviso de depreciação HTTPX/TestClient da biblioteca permanece; não causou falha dos cenários executados.

## Evidência externa anterior preservada

`live-check.json` é a consulta real ao Open-Meteo feita na primeira versão, com referência 05/11/2026 23:45 UTC (20:45 São Paulo), `simulated=false`, status ok, para coordenadas fictícias de demonstração. Não é uma nova consulta desta atualização nem uma leitura atual para uso operacional.

NASA real continua não validada por ausência de chave. Os conectores de dados não foram alterados nesta versão.

## Não validado

Containers/Compose, migrações em PostgreSQL real, execução do exemplo TypeScript em Expo/aparelho, builds Android/iOS, carga, auditoria completa de segurança, requisitos jurídicos ou integrações de emergência. O pacote é implementação para desenvolvimento, ainda sujeito à validação de banco descrita acima.

## Plano de testes adicionais — incluído em 06/11/2026

Consulte [PLANO-IA-E-TESTES.md](PLANO-IA-E-TESTES.md), etapa 3, para testes de PostgreSQL, adaptador/worker, chamadas reais, qualidade visual e jornada mobile. O plano exige separar testes controlados de chamadas reais e definir metas antes da avaliação final.

Esta atualização é documental: não executou novamente os testes, não forneceu credenciais de IA e não alterou os resultados históricos descritos acima. A aprovação das etapas exige registrar novas evidências.
