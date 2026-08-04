import type { ScenarioConfig, Snapshot } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const apiUrl = (path: string) => `${API_BASE}${path}`

async function requestError(response: Response, fallback: string): Promise<Error> {
  let detail = ''
  try {
    const payload = await response.json()
    detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? payload)
  } catch {
    detail = await response.text().catch(() => '')
  }
  return new Error(`${fallback} (${response.status}${detail ? `: ${detail}` : ''})`)
}

export interface AIStatus {
  providers: { name: string; configured: boolean; model: string }[]
  fallback: string
  mode: 'ai-enabled' | 'deterministic'
}

export interface AIResponse {
  provider: string
  model: string
  content: string
  used_fallback: boolean
  error?: string | null
}

export async function getAIStatus(): Promise<AIStatus> {
  const response = await fetch(apiUrl('/api/ai/status'))
  if (!response.ok) throw await requestError(response, 'Unable to load AI provider status')
  return response.json()
}

export async function generateAIInsight(prompt: string, provider = 'auto'): Promise<AIResponse> {
  const response = await fetch(apiUrl('/api/ai/generate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt, provider }),
  })
  if (!response.ok) throw await requestError(response, 'Unable to generate AI insight')
  return response.json()
}

export async function getSnapshot(): Promise<Snapshot> {
  const response = await fetch(apiUrl('/api/snapshot'))
  if (!response.ok) throw await requestError(response, 'Unable to load simulation snapshot')
  return response.json()
}

export async function configureScenario(config: ScenarioConfig): Promise<Snapshot> {
  const response = await fetch(apiUrl('/api/scenario'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) throw await requestError(response, 'Unable to configure scenario')
  return response.json()
}

export async function simulationCommand(command: 'start' | 'stop' | 'reset', speed = 10): Promise<Snapshot> {
  const response = await fetch(apiUrl(`/api/simulation/${command}`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  })
  if (!response.ok) throw await requestError(response, `Unable to ${command} simulation`)
  return response.json()
}

export async function changeSimulationSpeed(speed: number): Promise<Snapshot> {
  const response = await fetch(apiUrl('/api/simulation/speed'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  })
  if (!response.ok) throw await requestError(response, 'Unable to change simulation speed')
  return response.json()
}

// No WebSocket — Vercel serverless functions do not support long-lived connections.
// Use polling via getSnapshot() instead.
