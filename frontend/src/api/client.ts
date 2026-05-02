import axios from 'axios';

export const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface Signal {
  component_id: string;
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  payload: Record<string, any>;
  timestamp?: string;
}

export interface WorkItem {
  id: string;
  component_id: string;
  severity: 'P0' | 'P1' | 'P2' | 'P3';
  status: 'OPEN' | 'INVESTIGATING' | 'RESOLVED' | 'CLOSED';
  created_at: string;
  resolved_at?: string;
  mttr_seconds?: number;
  rca: RCA | null;
}

export interface RCA {
  start_time: string;
  end_time: string;
  root_cause_category: 'infra' | 'code' | 'config' | 'dependency';
  fix_applied: string;
  prevention_steps: string;
}

export interface IncidentDetail {
  work_item: WorkItem;
  signals: any[];
  signal_count: number;
}