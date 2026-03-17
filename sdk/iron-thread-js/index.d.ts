export interface ValidationResult {
  passed: boolean;
  status: 'passed' | 'failed' | 'corrected';
  reason: string;
  data: any;
  latencyMs: number;
  runId: string | null;
}

export interface Schema {
  id: string;
  name: string;
  description: string;
  schema_definition: object;
  created_at: string;
}

export interface DashboardStats {
  total_runs: number;
  passed: number;
  failed: number;
  corrected: number;
  success_rate: number;
  avg_latency_ms: number;
}

export class IronThread {
  constructor(host?: string);
  createSchema(name: string, schemaDefinition: object, description?: string): Promise<Schema>;
  listSchemas(): Promise<Schema[]>;
  validate(aiOutput: string | object, schemaId: string, modelUsed?: string): Promise<ValidationResult>;
  stats(): Promise<DashboardStats>;
  runs(): Promise<any[]>;
}

export function validate(aiOutput: string | object, schemaId: string, modelUsed?: string): Promise<ValidationResult>;