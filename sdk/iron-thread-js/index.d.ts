export interface AttestationBody {
  v: string;
  chain_id: string;
  seq: number;
  prev_hash: string;
  run_id: string;
  status: "passed" | "failed" | "corrected";
  input_sha256: string;
  output_sha256: string | null;
  schema_sha256: string | null;
  key_id: string;
  created_at: string;
}

/** A signed receipt for one validation. */
export interface Attestation {
  body: AttestationBody;
  entry_hash: string;
  signature: string;
}

export interface ValidationResult {
  run_id: string;
  status: "passed" | "failed" | "corrected";
  passed: boolean;
  reason: string;
  data: any;
  auto_corrected: boolean;
  attempts: number;
  latency_ms: number | null;
  confidence_score: number | null;
  confidence_flags: string[];
  /** The signed receipt, or null if the server could not sign (see attestation_error). */
  attestation: Attestation | null;
  attestation_error?: string;
}

export interface BatchValidationResult {
  total: number;
  passed: number;
  corrected: number;
  failed: number;
  success_rate: number;
  results: ValidationResult[];
}

export interface Schema {
  id: string;
  name: string;
  description: string | null;
  schema_definition: object;
  created_at: string;
}

export interface PublicKey {
  key_id: string;
  public_key: string;
}

export interface VerifyOutcome {
  ok: boolean;
  message: string;
}

export interface VerifyOptions {
  /** The head hash you recorded or published earlier. Catches a truncated or rewritten chain. */
  expectHead?: string;
  /** The number of entries you expect. */
  expectLength?: number;
}

export interface AttestationCheck {
  valid: boolean;
  reason: string;
  input_matches?: boolean;
  output_matches?: boolean;
  schema_matches?: boolean;
}

export interface ReconcileFinding {
  run_id: string;
  problem:
    | "unattested_run"
    | "orphan_attestation"
    | "status_mismatch"
    | "input_mismatch"
    | "output_mismatch"
    | "timestamp_mismatch"
    | "schema_mismatch";
  detail: string;
}

export interface ReconcileReport {
  chain_id: string;
  ok: boolean;
  chain_valid: boolean;
  chain_reason: string;
  schema_checked: boolean;
  runs_checked: number;
  attestations_checked: number;
  findings_total: number;
  findings: ReconcileFinding[];
}

export interface DashboardStats {
  [key: string]: any;
}

export interface Webhook {
  id: string;
  name: string;
  url: string;
  on_failure: boolean;
  on_success: boolean;
  schema_id: string | null;
  active: boolean;
  created_at: string;
}

export interface IronThreadOptions {
  baseUrl?: string;
  /** Defaults to $IRONTHREAD_API_KEY. */
  apiKey?: string;
  /** Default 30000. 0 disables the timeout. */
  timeoutMs?: number;
  /** Supply your own fetch (tests, proxies). */
  fetch?: typeof fetch;
}

/** The server answered with an error. status is 0 when it could not be reached at all. */
export class IronThreadError extends Error {
  status: number;
  detail: string;
  url: string;
}

export class IronThread {
  readonly baseUrl: string;
  constructor(baseUrl?: string, options?: Omit<IronThreadOptions, "baseUrl">);
  constructor(options: IronThreadOptions);

  createSchema(name: string, schemaDefinition: object, description?: string | null): Promise<Schema>;
  listSchemas(): Promise<Schema[]>;

  validate(
    aiOutput: string | object,
    schemaId: string,
    modelUsed?: string | null,
    autoCorrect?: boolean
  ): Promise<ValidationResult>;
  validateBatch(
    aiOutputs: Array<string | object>,
    schemaId: string,
    modelUsed?: string | null
  ): Promise<BatchValidationResult>;

  runs(): Promise<any[]>;
  exportRuns(): Promise<string>;

  publicKeys(): Promise<PublicKey[]>;
  getAttestation(runId: string): Promise<Attestation>;
  getChain(schemaId: string): Promise<Attestation[]>;
  verifyChainRemote(schemaId: string): Promise<{
    chain_id: string;
    valid: boolean;
    reason: string;
    length: number;
    head_hash: string;
  }>;
  verifyChainOffline(schemaId: string, publicKey: string, options?: VerifyOptions): Promise<VerifyOutcome>;
  verifyAttestation(
    entry: Attestation,
    options?: { input?: string; output?: any; schemaDefinition?: object }
  ): Promise<AttestationCheck>;
  reconcile(schemaId: string): Promise<ReconcileReport>;

  verifyRun(runId: string): Promise<any>;
  getSchemaChain(schemaId: string): Promise<any>;

  stats(): Promise<DashboardStats>;
  analyticsErrors(): Promise<any>;
  analyticsTrends(): Promise<any>;
  analyticsModels(): Promise<any>;
  analyticsSchemas(): Promise<any>;

  createWebhook(
    name: string,
    url: string,
    onFailure?: boolean,
    onSuccess?: boolean,
    schemaId?: string | null
  ): Promise<Webhook>;
  listWebhooks(): Promise<Webhook[]>;
  deleteWebhook(webhookId: string): Promise<{ deleted: boolean; webhook_id: string }>;
  health(): Promise<any>;
}

/** Check a chain of receipts offline, with a public key you trust. No network. */
export function verifyChain(entries: Attestation[], publicKey: string, options?: VerifyOptions): VerifyOutcome;

/** Deterministic JSON used for hashing: sorted keys, no whitespace. */
export function canonical(value: unknown): string;
