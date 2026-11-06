# Guardiões do Fogo — versão 2, backend para mobile

Stack aprovada: **React Native + Expo + TypeScript no aplicativo; Python/FastAPI nas APIs; PostgreSQL + PostGIS no servidor**.

Esta entrega atualiza os dois projetos existentes. Sua responsabilidade principal continua em `dados-api`. O `backend-reserva` continua independente e opcional. Não foi criado um aplicativo completo: foi incluído um cliente TypeScript de referência e o contrato para a equipe mobile.

| Componente | Responsabilidade |
|---|---|
| dados-api | clima e focos, normalização e respostas parciais; funciona sem o backend reserva |
| backend-reserva | usuários, propriedades, ocorrências, fotos, revisão e relatórios |
| PostgreSQL/PostGIS | dados persistentes, sessões e consultas geográficas |
| volume privado de fotos | arquivos de imagens; banco guarda a referência |
| cliente mobile da equipe | câmera, permissões, telas, armazenamento local e fila offline |

## Mudanças em relação à primeira entrega

- Removido SQLite do backend; PostgreSQL obrigatório, sem fallback silencioso.
- Migrações SQL versionadas com checksum e execução transacional.
- Coordenadas das propriedades com `geography(Point,4326)` e índice GiST.
- Consulta de proximidade usando PostGIS, com distância em metros.
- Fotos em multipart, reencodificadas e salvas em volume privado.
- UUID por relato para impedir duplicação em reenvios, inclusive simultâneos.
- Token de acesso de 15 minutos e renovação com rotação, limitada a 30 dias por sessão.
- Compose com banco, migração, serviço de dados e backend.
- Exemplo de cliente Expo em `backend-reserva/examples/expo-client.ts`.

## Etapas de IA real e testes

O plano aprovado está em [docs/PLANO-IA-E-TESTES.md](docs/PLANO-IA-E-TESTES.md). Ele organiza seleção do modelo, processamento real, testes de banco/IA/mobile e atualização documental, com entregáveis e critérios de conclusão. Esta atualização inclui o plano; a IA continua simulada até implementar e validar a integração.

## Iniciar com Docker Compose

1. Copie `.env.example` para `.env`.
2. Execute duas vezes `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use valores diferentes para `POSTGRES_PASSWORD` e `DATA_API_KEY`.
3. Mantenha `DATA_MODE=demo` para a demonstração inicial.
4. Execute:

```bash
docker compose up --build -d
docker compose logs migrate
docker compose exec backend python -m backend.bootstrap --username coop.admin --name "Representante" --cooperative "Cooperativa Demo"
```

O migrador deve terminar com sucesso antes do backend iniciar. O bootstrap solicita a senha inicial e exige troca no primeiro acesso. Não existe usuário/senha padrão. Esse Compose é para desenvolvimento: em produção, separe o papel de migração do usuário de banco da aplicação, use HTTPS, controle de acesso de rede e backup.

- Swagger backend: http://127.0.0.1:8000/docs
- Swagger dados: http://127.0.0.1:8001/docs
- Saúde backend e PostGIS: http://127.0.0.1:8000/health

`postgres_data` e `private_photos` preservam dados. **Não execute `docker compose down -v` se precisar mantê-los**. PostgreSQL não é exposto na rede do host. O Compose assume senha URL-safe; a geração sugerida evita problemas de encoding na URL.

## Testar no celular

No `.env`, defina `BACKEND_BIND=0.0.0.0` somente em rede de desenvolvimento confiável e recrie o backend com `docker compose up -d backend`. No aplicativo use `http://IP_DO_COMPUTADOR:8000`, com aparelho e computador na mesma rede. Não use `localhost` no celular. O serviço de dados e o banco continuam privados. Para builds/rede pública, use HTTPS; a aceitação de HTTP local depende da configuração nativa do app.

## Ler nesta ordem

1. `docs/INPUTS-E-CONTRATOS.md` — contrato atualizado, especialmente multipart e renovação.
2. `docs/MOBILE.md` — integração Expo e responsabilidades do aplicativo.
3. `docs/EXPLICACAO-TECNICA.md` — como o código funciona.
4. `docs/ROTEIRO-DEMO.md` — fluxo de demonstração.
5. `docs/VALIDACAO.md` — o que foi e o que não foi executado.
6. `docs/ESCOPO-E-EVOLUCAO.md` — pendências e cobertura do PRD.
7. `docs/PLANO-IA-E-TESTES.md` — etapas, responsabilidades e critérios para sair da simulação.

## Testes completos com PostgreSQL/PostGIS

```bash
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
# Depois de verificar o resultado:
docker compose -f compose.test.yaml down
```

Esse ambiente cria banco exclusivo e temporário. Não usa o banco do aplicativo. Aqui, 11 testes locais passaram; 13 cenários que dependem de PostgreSQL ficaram não executados. O ambiente não permitiu iniciar PostgreSQL/PostGIS e não disponibilizou Docker; não se deve considerar o banco validado antes de executar essa suíte.

## Compatibilidade

O contrato do serviço de dados permanece em 1.0. O backend passa para 2.0. Login continua aceitando o mesmo JSON, mas retorna refresh token. `POST /v1/incidents` mudou de JSON/base64 para multipart e exige `client_request_id`: o consumidor deve ser atualizado. Bancos SQLite anteriores não são importados automaticamente; a migração entregue cria o novo esquema PostgreSQL. Não apagar uma base antiga antes de planejar/exportar seus registros.
