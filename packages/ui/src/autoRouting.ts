export type RoutingProfile = "balanced" | "cost" | "quality";
export const routingProfiles: RoutingProfile[] = ["balanced", "cost", "quality"];
export const routingLabels: Record<RoutingProfile, string> = {
  balanced: "Balanced — intent, suitability and cost (default)",
  cost: "Cost — comparable known prices only",
  quality: "Quality — estimated task suitability",
};
export interface AutoRoutingAvailability {
  ready: boolean;
  reason?: string | null;
  profiles: RoutingProfile[];
  config_version?: string | null;
  architecture?: string;
  max_completion_tokens?: number | null;
}
export interface AutoCandidate {
  id: string;
  provider: string;
  model_name: string;
  model_version: string;
  capabilities: string[];
  max_completion_tokens: number;
  price_status: "published" | "provisional" | "unknown";
  price: { input: string; output: string; cached?: string; source_url: string; revision: string } | null;
}
export interface AutoProfileConfig {
  profile: RoutingProfile;
  enabled: boolean;
  candidate_models: string[];
  eligible_models: string[];
  fallback_model: string;
  version: string;
  valid: boolean;
  updated_at: string;
  source?: "platform-default" | "desired-override";
  publication_status?: "platform-snapshot" | "desired-not-published";
}
export interface AutoConfiguration {
  items: AutoProfileConfig[];
  candidates: AutoCandidate[];
  feature_enabled: boolean;
  gateway_ready: boolean;
  contract_verified: boolean;
  publication_verified?: boolean;
  published_version?: string | null;
  descriptor_version: string;
  pricing_revision: string;
}
export interface AutoRoutingMetadata {
  selected_model: string;
  routing_profile: RoutingProfile;
  config_version: string;
  fallback_used: boolean;
  failure?: "decision_unavailable" | null;
  decision_overhead?: {
    latency_ms: number | null;
    usage: { input_tokens: number | null; output_tokens: number | null };
    cost_usd: string | null;
  };
  decision_usage?: { input_tokens: number | null; output_tokens: number | null };
  decision_cost_usd?: string | null;
}