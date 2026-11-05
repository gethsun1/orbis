export type ApiState<T> = { state: 'available'; data: T } | { state: 'loading' } | { state: 'unavailable'; reason: string } | { state: 'error'; message: string }
export interface NetworkIdentity { profile: string; chainId: number; genesisHash: string; fingerprint: string; verified: boolean }
export interface ObserverStatus { lastBlock: number; lastBlockHash: string; requestedRange: [number, number]; coverage: 'complete' | 'partial' | 'unknown' }
export interface ActivityRecord { block: number; transactionHash: string; summary: string; timestamp: string }
export interface EvaluationRecord { rule: string; version: string; outcome: 'matched' | 'not_matched' | 'insufficient_coverage'; coverage: string; at: string }
export interface FindingRecord { id: string; classification: string; emitter: string; block: number; transactionHash: string; logIndex: number; canonical: boolean }
