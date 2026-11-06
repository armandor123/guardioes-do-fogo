# Explicação técnica — versão 2

## Decisões

Mantidos os dois projetos separados: `dados-api` é sua entrega principal e pode ser consumido pelo backend de outra pessoa. `backend-reserva` é a contingência. O aplicativo foi definido como React Native/Expo/TypeScript; ambos os servidores continuam em Python/FastAPI.

O backend agora exige PostgreSQL, conforme o PRD. Foi removido o código SQLite de runtime. O acesso é feito com psycopg 3 e SQL parametrizado. Essa implementação não utiliza ORM; as alterações de esquema são arquivos SQL versionados e revisáveis.

## Banco e migrações

`backend/migrations/001_initial.sql` cria cooperativas, usuários, propriedades, sessões, histórico de refresh, ocorrências e revisões. `backend/migrate.py` registra nome/checksum/aplicação de cada versão, bloqueia execução concorrente e aplica tudo em transação. Reexecutar uma migração intacta não duplica tabelas. Editar arquivo já aplicado é erro; criar outro arquivo para próximas mudanças.

O Compose espera o banco ficar saudável, executa o migrador e só inicia o backend se ele terminar com sucesso. Não há downgrade nem importação automática do antigo arquivo SQLite. Se houver dados anteriores, exportá-los e planejar transformação antes de descontinuar a base.

## PostGIS

Cada propriedade mantém latitude/longitude e um campo gerado `geography(Point,4326)`. O banco constrói o ponto na ordem longitude, latitude e mantém um índice GiST. A rota `/v1/properties/nearby` usa distância geodésica em metros, limita o raio e retorna somente propriedades da cooperativa autenticada. Não trabalha com polígonos nem estima área queimada.

## Fotos fora do banco

O endpoint aceita dois campos multipart: metadata JSON e arquivo photo. A imagem é validada, reencodificada em JPEG e salva em diretório privado; EXIF é removido. O PostgreSQL guarda a chave do arquivo e seu tipo. Escrita usa arquivo temporário e substituição atômica. A leitura passa pela mesma autorização da ocorrência.

Isso permite migrar posteriormente para object storage privado sem transformar o banco em depósito de imagens. A versão atual usa volume local privado, não S3/serviço externo. É necessário backup do banco e das fotos. Arquivos órfãos após falhas antes do commit podem exigir coleta futura.

## Reenvios sem duplicação

O app gera `client_request_id` antes do primeiro envio. O banco aplica unicidade por agricultor/UUID. Durante a criação, um lock consultivo serializa requisições dessa chave. Um hash de metadata normalizado e dos bytes originais diferencia repetição legítima de alteração de conteúdo. Uma repetição legítima retorna o mesmo ID; alteração retorna 409.

A fila offline precisa preservar UUID e foto original comprimida. Recomprimir a cada tentativa muda os bytes e causa conflito. O backend oferece deduplicação, mas não implementa a fila no aparelho.

## Sessões mobile

Login gera token de acesso curto e refresh mais longo. São valores aleatórios, armazenados no banco apenas por hash. Refresh troca ambos, invalida o access anterior e grava o hash do refresh utilizado. Se o antigo reaparecer, a família/sessão é revogada. A validade máxima da sessão é fixa em 30 dias.

Transações bloqueiam usuário e sessão na mesma ordem para coordenar rotação e troca de senha. Troca de senha revoga todas as sessões; logout apenas a sessão atual. O aplicativo precisa serializar refresh e persistir o par novo junto. Perder a resposta de renovação pode exigir novo login, pois não há janela de tolerância.

## Serviço de dados

Permanece independente do banco: valida coordenadas, consulta Open-Meteo e NASA FIRMS, normaliza as respostas, deduplica focos e aplica raio. Cache limitado e fontes com horários/status preservados. No modo live, falha não vira simulação. Modo demo é identificado. IA segue simulada; risco sem método validado continua nulo.

## Arquivos importantes

| Arquivo | Responsabilidade |
|---|---|
| dados-api/dados/models.py | entradas e envelopes ambientais |
| dados-api/dados/providers.py | conectores e parsing |
| dados-api/dados/main.py | API independente de dados |
| backend-reserva/backend/db.py | conexão PostgreSQL transacional |
| backend-reserva/backend/migrate.py | migrações e checksums |
| backend-reserva/backend/migrations/001_initial.sql | esquema PostgreSQL/PostGIS |
| backend-reserva/backend/storage.py | arquivos privados |
| backend-reserva/backend/schemas.py | validação de inputs |
| backend-reserva/backend/main.py | regras de acesso e rotas |
| backend-reserva/examples/expo-client.ts | referência para o aplicativo |
| compose.test.yaml | ambiente de testes isolado com PostGIS |

## Validação e próximos passos

Os testes locais passaram; os testes com PostgreSQL não foram executados neste ambiente. Antes de integrar à equipe, rodar a suíte Docker documentada, confirmar comportamento real do banco, depois conectar o frontend e validar em Android/iOS. Leia `VALIDACAO.md` para os números e limites atuais.

## Evolução planejada de IA

A integração real será conduzida pelas quatro etapas de [PLANO-IA-E-TESTES.md](PLANO-IA-E-TESTES.md). O adaptador ficará na frente de dados/APIs, enquanto o backend cuidará das tarefas e resultados vinculados às ocorrências. Essa arquitetura futura preserva a separação dos dois projetos; ainda não há worker nem fornecedor real de visão implementado.
