/** Exemplo de integração, não um app completo. Instale expo-secure-store no app. */
import * as SecureStore from 'expo-secure-store';

export type Tokens = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
};
export type IncidentMetadata = {
  client_request_id: string; // UUID persistido ANTES do primeiro envio
  property_id: string;
  description?: string;
  latitude?: number;
  longitude?: number;
  location_source: 'gps' | 'manual' | 'unavailable';
  location_authorized: boolean;
};

export class ApiClient {
  private readonly key = 'guardioes.session.v2';
  private sessionEpoch = 0;
  private refreshing: Promise<Tokens> | null = null;
  constructor(private readonly baseUrl: string) {}

  private async readTokens(): Promise<Tokens | null> {
    const value = await SecureStore.getItemAsync(this.key);
    return value ? JSON.parse(value) as Tokens : null;
  }

  private async fetchWithTimeout(path: string, init: RequestInit): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      return await fetch(this.baseUrl + path, { ...init, signal: controller.signal });
    } finally { clearTimeout(timer); }
  }

  async login(username: string, password: string): Promise<Tokens & { must_change_password: boolean }> {
    const epoch = ++this.sessionEpoch;
    const response = await this.fetchWithTimeout('/v1/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) throw new Error(`Login recusado: ${response.status}`);
    const tokens = await response.json();
    if (epoch !== this.sessionEpoch) throw new Error('Login cancelado');
    await SecureStore.setItemAsync(this.key, JSON.stringify(tokens));
    return tokens;
  }

  private renew(): Promise<Tokens> {
    // Apenas uma renovação por instância: evita reuso concorrente do refresh.
    if (this.refreshing) return this.refreshing;
    const epoch = this.sessionEpoch;
    this.refreshing = (async () => {
      const old = await this.readTokens();
      if (!old) throw new Error('Faça login');
      const response = await this.fetchWithTimeout('/v1/auth/refresh', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: old.refresh_token }),
      });
      if (!response.ok) {
        if (response.status === 401) await SecureStore.deleteItemAsync(this.key);
        throw new Error(`Renovação indisponível: ${response.status}`);
      }
      const fresh = await response.json() as Tokens;
      if (epoch !== this.sessionEpoch) throw new Error('Sessão alterada durante renovação');
      await SecureStore.setItemAsync(this.key, JSON.stringify(fresh));
      return fresh;
    })().finally(() => { this.refreshing = null; });
    return this.refreshing;
  }

  async request(path: string, makeInit: () => RequestInit = () => ({})): Promise<Response> {
    let tokens = await this.readTokens();
    if (!tokens) throw new Error('Faça login');
    const send = (access: string) => {
      const init = makeInit();
      const headers = new Headers(init.headers);
      headers.set('Authorization', `Bearer ${access}`);
      return this.fetchWithTimeout(path, { ...init, headers });
    };
    let response = await send(tokens.access_token);
    if (response.status === 401) {
      // Outra requisição pode já ter concluído a renovação.
      const saved = await this.readTokens();
      tokens = saved && saved.access_token !== tokens.access_token ? saved : await this.renew();
      response = await send(tokens.access_token); // no máximo uma repetição
    }
    return response;
  }

  async sendIncident(metadata: IncidentMetadata, photoUri: string): Promise<{id: string; replayed: boolean}> {
    const response = await this.request('/v1/incidents', () => {
      const body = new FormData();
      body.append('metadata', JSON.stringify(metadata));
      // URI deve apontar para cópia persistente do JPEG comprimido no aparelho.
      body.append('photo', { uri: photoUri, name: 'photo.jpg', type: 'image/jpeg' } as unknown as Blob);
      return { method: 'POST', body }; // Não definir Content-Type: o runtime inclui o boundary.
    });
    if (!response.ok) throw new Error(`Envio recusado: ${response.status}`);
    return response.json();
  }

  async logout(): Promise<void> {
    // Se falhar a rede, a revogação remota não é garantida; os tokens locais são removidos.
    ++this.sessionEpoch;
    try {
      const tokens = await this.readTokens();
      if (tokens) await this.fetchWithTimeout('/v1/auth/logout', {
        method: 'POST', headers: { Authorization: `Bearer ${tokens.access_token}` },
      });
    }
    finally { await SecureStore.deleteItemAsync(this.key); }
  }
}
