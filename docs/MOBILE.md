# Integração com React Native + Expo + TypeScript

A tecnologia do aplicativo está definida. Esta entrega prepara as APIs e inclui um cliente de referência; telas, builds Android/iOS, câmera, permissões e fila offline ainda precisam ser implementados pelo responsável mobile.

## O que o cliente de exemplo faz

`backend-reserva/examples/expo-client.ts` usa fetch e expo-secure-store para:

- Fazer login e armazenar o par de tokens em uma única entrada segura.
- Renovar a sessão uma vez quando uma chamada retorna 401.
- Compartilhar uma renovação em andamento entre chamadas concorrentes da mesma instância.
- Enviar metadata + foto por FormData sem definir manualmente Content-Type.
- Apagar credenciais locais no logout.

Use uma única instância do cliente no aplicativo. É um exemplo de integração, não um SDK publicado, e não foi executado em um aparelho nesta entrega. Não misturar chamadas independentes de refresh em outros módulos. Serializar login/logout/troca de conta e cancelar chamadas pendentes no ciclo de navegação do aplicativo.

Instale no projeto Expo da equipe:

```bash
npx expo install expo-secure-store
```

Copie o arquivo para o app e configure somente a URL pública do backend:

```typescript
import { ApiClient } from './expo-client';
export const api = new ApiClient('https://SEU_BACKEND');
```

**Não colocar DATA_API_KEY, FIRMS_MAP_KEY ou DATABASE_URL no aplicativo.** Variáveis `EXPO_PUBLIC_*` entram no bundle e não servem para guardar segredos. A URL do backend pode ser pública.

## Fotos

Solicitar autorização de câmera/galeria, selecionar a imagem, corrigir orientação se necessário e comprimir para JPEG abaixo de 3 MB e 12 megapixels. Guardar uma cópia durável em diretório do aplicativo antes de tentar enviar. O servidor ainda verifica o formato real e remove EXIF. A compressão no cliente economiza conexão; não substitui a validação do servidor.

No exemplo, `photoUri` deve apontar para essa cópia local do JPEG. HEIC não é aceito diretamente no backend: converter no aplicativo. Escolher câmera e manipulação de imagem compatíveis com o SDK Expo adotado; não instalar versões nativas arbitrárias fora da matriz do Expo.

## Localização e recusa

Pedir permissão em contexto, no registro da ocorrência. Para GPS: coordenadas + `location_source=gps` + `location_authorized=true`. Para seleção manual autorizada: `manual`. Se negada/indisponível, não bloquear o relato: `unavailable` e omitir coordenadas. O app deve explicar a finalidade; os campos do backend são apenas o registro técnico, não substituem o aviso ao usuário.

## Fila offline — responsabilidade do aplicativo

1. Gerar UUID e montar metadata uma única vez.
2. Guardar metadata, URI persistente da foto, usuário dono e estado pendente.
3. Tentar envio ao recuperar conexão, com espera progressiva entre falhas.
4. Em timeout, reenviar exatamente o mesmo UUID, metadata e arquivo.
5. Em sucesso/replayed, marcar sincronizado; só então remover a cópia temporária conforme a política de retenção.
6. Em 409, sinalizar conflito e não criar outro UUID automaticamente.
7. Em 401, renovar uma vez; se falhar, solicitar login.
8. Ao trocar de conta, nunca enviar relatos pendentes de outro usuário.

É possível usar SQLite **local no aparelho** para a fila, sem substituir o PostgreSQL do servidor. A implementação da fila não está incluída. Armazenamento offline requer proteção de dados, retenção e limpeza próprias.

## Conexão e segurança

Em aparelho físico, localhost é o celular. Use o IP do computador apenas em desenvolvimento confiável, com backend escutando em endereço de rede. No emulador Android, o endereço do host depende do emulador; configure por ambiente. Em produção use HTTPS com certificado válido, sem desabilitar verificação TLS. Push e execução em segundo plano exigem configuração nativa e ainda não foram incluídos.

Fotos privadas precisam de Bearer. Não transformar a URL relativa `/v1/incidents/{id}/photo` em link público. O app pode fazer download autenticado ou usar componente de imagem com headers compatível com sua plataforma; limpar caches privados no logout.

## Documentação oficial consultada

- React Native/Expo: https://reactnative.dev/docs/environment-setup
- SecureStore: https://docs.expo.dev/versions/latest/sdk/securestore/
- Upload FastAPI: https://fastapi.tiangolo.com/tutorial/request-forms-and-files/
