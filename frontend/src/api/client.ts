import type { ApiState, NetworkIdentity, ObserverStatus, ActivityRecord, EvaluationRecord, FindingRecord } from './types'

// Read-only boundary for the future same-origin ORBIS API. No browser database or RPC access.
export interface OrbisReadApi {
  network(): Promise<ApiState<NetworkIdentity>>
  observer(): Promise<ApiState<ObserverStatus>>
  activity(): Promise<ApiState<ActivityRecord[]>>
  evaluations(): Promise<ApiState<EvaluationRecord[]>>
  findings(): Promise<ApiState<FindingRecord[]>>
}

export const api: OrbisReadApi = {
  async network() { return { state: 'unavailable', reason: 'Read-only API integration is not available yet.' } },
  async observer() { return { state: 'unavailable', reason: 'Read-only API integration is not available yet.' } },
  async activity() { return { state: 'unavailable', reason: 'Read-only API integration is not available yet.' } },
  async evaluations() { return { state: 'unavailable', reason: 'Read-only API integration is not available yet.' } },
  async findings() { return { state: 'unavailable', reason: 'Read-only API integration is not available yet.' } },
}
