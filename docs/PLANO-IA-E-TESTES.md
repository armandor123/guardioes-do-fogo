# Plano de integração da IA real e testes

Atualizado em 06/11/2026. Este documento incorpora as etapas aprovadas para evolução do Guardiões do Fogo. É um plano de execução: não declara IA integrada, modelo avaliado ou testes adicionais aprovados.

## Objetivo e ponto de partida

Substituir a resposta simulada por análise real de indícios visuais de fumaça e chama, medir a qualidade com imagens autorizadas e apresentar os resultados à cooperativa para revisão humana.

Estado atual: dois projetos independentes; backend PostgreSQL/PostGIS preparado; IA simulada/inconclusiva; 11 testes locais aprovados na verificação anterior; 13 cenários de banco não executados. Esses números são históricos da versão de código entregue, não resultados novos desta atualização documental.

| Marco | Quando pode ser declarado |
|---|---|
| IA planejada | Etapas, responsabilidades e critérios documentados — estado desta atualização |
| IA integrada | Imagem realmente processada por modelo identificado, com resultado persistido e testes de integração registrados |
| IA avaliada | Avaliação independente concluída, com métricas, distribuição dos casos e limitações documentadas |
| Piloto autorizado pela equipe | Critérios definidos previamente atendidos, fluxo humano e funcionamento mobile verificados |

Executar um modelo não comprova sua precisão. Uma imagem sem indícios também não comprova ausência de incêndio na propriedade.

## Responsabilidades propostas

| Frente | Responsabilidade |
|---|---|
| Sua parte — dados/APIs | Adaptador do fornecedor de IA, contrato normalizado, erros, rastreabilidade e execução das avaliações |
| Responsável pelo backend | Autorização, vínculo com ocorrência, tarefas persistentes, resultados no PostgreSQL e endpoints do aplicativo |
| Responsável mobile | Câmera, compressão, autorização, fila offline, estados de análise e apresentação das limitações |
| Cooperativa/revisores | Rotulagem/revisão de imagens e critérios para uso operacional |
| Equipe do projeto | Escolha de fornecedor, credenciais, orçamento, ambiente de testes e aprovação do piloto |

O backend de reserva deve implementar o mesmo contrato caso seja necessário. O módulo de IA pode pertencer ao projeto dados-api; isso não exige fundir os dois projetos nem entregar chaves externas ao aplicativo.

## Etapa 1 — Selecionar e preparar a IA real

### Trabalho

- [ ] Comparar APIs de visão candidatas usando o mesmo conjunto de desenvolvimento.
- [ ] Verificar suporte a imagem, saída estruturada, disponibilidade, custo, latência e versão do modelo.
- [ ] Verificar condições de envio, retenção e uso das imagens pelo fornecedor.
- [ ] Definir fornecedor/modelo e orçamento máximo de avaliação; não contratar ou ativar cobrança sem decisão da equipe.
- [ ] Configurar credencial exclusivamente no servidor, fora do Git e do aplicativo.
- [ ] Reunir imagens autorizadas e registrar procedência, permissão/licença e limitações.
- [ ] Definir a taxonomia visual e instruções versionadas.

### Taxonomia proposta

Tratar fumaça e chama como sinais que podem coexistir. Separar os campos de evidência visual dos campos de qualidade da imagem:

- Fumaça: presente, ausente ou incerta.
- Chama: presente, ausente ou incerta.
- Qualidade: adequada ou insuficiente para análise.
- Resultado geral: indícios visuais, sem indícios visuais ou inconclusivo.
- Revisão humana: necessária.

Não estimar hectares queimados nem declarar incêndio confirmado a partir da foto. Não publicar porcentagem de confiança como precisão medida sem um método de calibração e avaliação correspondente. Usar valores nulos quando a informação não existir.

### Entregáveis e conclusão

Registro de decisão do fornecedor/modelo; credencial instalada no ambiente autorizado; conjunto de desenvolvimento com permissões registradas; contrato e instruções da análise versionados. Conclusão depende da disponibilidade real de credencial e imagens — ainda não fornecidas.

## Etapa 2 — Implementar processamento e persistência

### Fluxo a implementar

1. Backend recebe e valida a foto, salva ocorrência e registra tarefa de análise durável.
2. Um worker recupera a tarefa e obtém a foto por canal interno autorizado.
3. O adaptador de dados/APIs envia a imagem ao modelo selecionado.
4. Valida a resposta estruturada e normaliza somente os campos permitidos.
5. Backend salva resultado, origem, versão e horários no PostgreSQL.
6. Aplicativo consulta o estado e a cooperativa revisa a ocorrência.

Evitar que a criação do relato dependa de aguardar a resposta da IA. Não usar apenas uma tarefa em memória: o processamento deve sobreviver a reinícios. A escolha da fila/worker será registrada na implementação. Uma tabela de tarefas/outbox permite coordenar gravação da ocorrência e agendamento na mesma transação.

### Mudanças previstas, ainda não implementadas

| Área | Alteração |
|---|---|
| dados-api | Adaptador de visão, autenticação interna e validação do resultado |
| backend | Migração nova para tarefas/resultados, criação de tarefa e leitura do estado |
| worker | Consumo de tarefas, limites de execução, retries limitados e retomada após falha |
| mobile | Exibir aguardando, processando, concluído ou indisponível; consultar resultado |
| configuração | Modo de IA independente do modo meteorologia/satélite, modelo e segredo no servidor |

### Contrato de resultado proposto

| Campo | Finalidade |
|---|---|
| analysis_id / incident_id | Identificação e vínculo autorizado com a ocorrência |
| status | queued, processing, completed ou failed |
| simulated | Origem simulada ou execução real; não significa qualidade validada |
| provider / model_version | Origem exata e versão utilizada |
| prompt_version / schema_version | Instruções e formato usados |
| input_hash | Rastrear a imagem analisada sem colocá-la nos logs |
| started_at / completed_at | Tempos reais do processamento |
| smoke / flame / image_quality | Evidência visual e limitações |
| outcome | indícios, sem indícios ou inconclusivo |
| error_code | Código controlado em falhas, sem segredo ou resposta bruta sensível |
| human_review_required | Revisão humana separada da análise automática |

Esse contrato é proposto; não foi adicionado ao OpenAPI atual como se já existisse. Resultado vazio, inválido, timeout ou indisponibilidade não pode virar “sem indícios”. `completed` com `simulated=false` exige resposta real aceita e persistida. Não alterar retroativamente a origem dos resultados simulados já armazenados.

### Resiliência e acesso

- [ ] Vincular cada tarefa à ocorrência e à versão da análise; repetir a mesma tarefa não duplica resultado.
- [ ] Limitar retries e custo; diferenciar falha temporária de credencial/entrada inválida.
- [ ] Tratar timeout após envio: a requisição pode ter gerado cobrança mesmo sem resposta recebida.
- [ ] Preservar histórico quando houver reanálise; não apagar resultado anterior silenciosamente.
- [ ] Permitir desligar o fornecedor sem impedir relatos, revisão humana e acesso ao SOS.
- [ ] Não permitir leitura de imagens/resultados entre cooperativas.
- [ ] Tratar instruções escritas dentro da foto como conteúdo da imagem, não comandos para o serviço.

### Entregáveis e conclusão

Migração, adaptador, worker, rotas documentadas e testes automatizados. Evidência de pelo menos uma imagem autorizada processada de verdade, resultado persistido e recuperação após falha/reinício. Isso permite declarar IA integrada, ainda sem alegação de precisão.

## Etapa 3 — Executar testes técnicos e avaliar qualidade

### 3A. PostgreSQL/PostGIS e backend

Executar primeiro a suíte já entregue:

```bash
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
```

- [ ] Registrar commit/versão do pacote, ambiente, data e saída dos testes.
- [ ] Confirmar que os 13 cenários de banco foram executados, sem `skipped` por falta de banco.
- [ ] Resolver todas as falhas antes de considerar a base validada.
- [ ] Verificar migração em base vazia e repetição segura da migração.
- [ ] Validar autorização, PostGIS, refresh, fotos, reenvios simultâneos e integração de dados.

### 3B. Integração de IA

Adicionar testes automatizados com respostas controladas para falhas e chamadas reais identificadas separadamente:

| Cenário | Resultado esperado |
|---|---|
| Foto autorizada e resposta válida | Tarefa concluída, resultado e versões persistidos |
| Timeout, 429 ou erro temporário | Retry limitado; erro explícito ao esgotar tentativas |
| Chave inválida ou resposta fora do schema | Sem resultado fabricado; diagnóstico controlado |
| Reinício do worker | Tarefa recuperável, sem duplicar resultado |
| Envio/consumo duplicado de tarefa | Uma análise lógica, custo monitorado |
| Tentativa de acesso de outra cooperativa | Acesso negado |
| Foto de baixa qualidade | Inconclusivo quando não permite avaliação |
| Texto malicioso embutido na imagem | Não altera instruções, acesso ou formato do serviço |
| Fornecedor desligado | Relatos e revisão humana continuam disponíveis |
| Demonstração versus real | Origem preservada e apresentada corretamente |

Chamadas reais geram custo e devem usar ambiente/chave de teste definidos. Respostas mockadas continuam úteis para regressão, mas não comprovam execução nem qualidade do modelo real.

### 3C. Avaliação com imagens rotuladas

- [ ] Definir um guia de rotulagem e registrar casos ambíguos, sem forçar uma resposta binária.
- [ ] Separar desenvolvimento e avaliação final; reservar esta última antes de ajustar modelo/instruções.
- [ ] Separar por evento/local/origem: quadros do mesmo vídeo ou fotos quase idênticas não devem aparecer nos dois conjuntos.
- [ ] Incluir chama, fumaça, cenas sem esses sinais, poeira, neblina, nuvens, pôr do sol, noite e desfoque.
- [ ] Contar imagens/eventos em cada grupo e registrar procedência, autorização e distribuição.
- [ ] Revisar rótulos com outra pessoa nos casos críticos/ambíguos e registrar divergências.
- [ ] Definir metas antes de examinar os resultados finais.
- [ ] Executar avaliação sem ajustar o modelo com base no conjunto final; se houver ajuste, reservar nova avaliação independente.

Métricas: precisão e recall por sinal visual; falsos positivos e negativos com denominadores; matriz de confusão; taxa de inconclusivos; cobertura das respostas conclusivas; falhas técnicas; latência mediana/p95 e custo por imagem. Mostrar resultados por condição, não apenas média geral. Um caso inconclusivo não deve ser contado como acerto nem descartado silenciosamente.

Para conjuntos pequenos, declarar incerteza e evitar afirmações de precisão generalizável. Definir o tamanho da amostra conforme a variabilidade e a precisão estatística desejada; uma demonstração com poucas fotos não valida uso operacional.

### Metas a preencher antes da avaliação final

| Critério | Meta aprovada | Responsável pela aprovação |
|---|---|---|
| Recall mínimo para indícios visuais | A definir | Equipe + revisor do domínio |
| Falsos positivos toleráveis | A definir | Cooperativa/equipe |
| Inconclusivos e cobertura mínima | A definir | Equipe + revisor do domínio |
| Latência p95 aceitável | A definir | Backend/mobile |
| Custo máximo por análise e orçamento total | A definir | Responsável pelo projeto |
| Quantidade/diversidade e independência da amostra | A definir | Responsável pela avaliação |

Metas não preenchidas ou não atendidas impedem declarar o piloto aprovado. Não foram escolhidos números arbitrários para prometer desempenho.

### 3D. Jornada mobile

- [ ] Android/iOS: câmera/galeria, autorização e recusa de GPS.
- [ ] Compressão, arquivo inválido, relato sem conexão e reenvio do mesmo UUID.
- [ ] Refresh de sessão, logout e troca de conta sem enviar pendências de outro usuário.
- [ ] Estados da análise, demora, indisponibilidade e reconsulta após reiniciar o app.
- [ ] Resultado inconclusivo/sem indícios sem mensagem de segurança garantida.
- [ ] Cooperativa recebe e revisa o resultado, preservando histórico.

### Entregáveis e conclusão

Relatório de testes técnicos e avaliação com versão exata do modelo/instruções, composição da amostra, rótulos, métricas, erros e limitações. Os critérios técnicos precisam passar, e as metas de qualidade devem ser satisfeitas para avançar ao piloto.

## Etapa 4 — Atualizar documentação e liberar piloto controlado

- [ ] Atualizar OpenAPI e guia de inputs somente após implementar os endpoints reais.
- [ ] Atualizar README, estado do projeto e roteiro de demonstração com evidências novas.
- [ ] Atualizar o PRD/PDF original em uma revisão específica; o PDF não foi modificado nesta entrega.
- [ ] Registrar fornecedor/modelo, instruções, conjunto de avaliação e data de validação.
- [ ] Usar “análise real por IA, sujeita à revisão humana” após comprovar integração.
- [ ] Publicar métricas somente com contexto da amostra e limitações.
- [ ] Definir responsável pelo piloto, orçamento, monitoração e procedimento de suspensão.
- [ ] Fazer novas avaliações quando mudar modelo, instruções ou condições relevantes de uso.

Manter revisão da cooperativa. A IA não deve acionar autoridades, confirmar área queimada nem substituir os contatos de emergência.

## Ordem prática e dependências

| Ordem | Ação | Pode começar sem credencial de IA? |
|---|---|---|
| 1 | Executar PostgreSQL/PostGIS e a suíte atual | Sim |
| 2 | Preparar rótulos, contratos e imagens autorizadas | Sim |
| 3 | Escolher fornecedor/modelo e orçamento | Sim, decisão da equipe |
| 4 | Implementar adaptador/worker e testes controlados | Sim; validação real depende da credencial |
| 5 | Executar chamadas reais e avaliação independente | Não |
| 6 | Validar mobile, documentar evidências e aprovar piloto | Depende dos resultados anteriores |

## Registro mínimo de cada execução

Registrar: responsável; data/hora; versão do código; ambiente/banco; fornecedor/modelo; versão das instruções; identificador do conjunto de imagens; número de casos; métricas; falhas; custo; decisão e limitações. Não incluir chaves, tokens ou fotos privadas em logs públicos.

## Referências metodológicas

- NIST AI RMF: https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf
- NIST, avaliação e documentação: https://airc.nist.gov/airmf-resources/playbook/measure/
- PyTorch, alternativa de aprendizado por transferência: https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial

Essas referências orientam o plano e não certificam o desempenho do aplicativo.
