export type Risk = "Low" | "Moderate" | "High";
export interface Metadata {
  demonstrations?: {id:string; type:string; as_of:string}[];
  routes: {
    route_id: string;
    origin: string;
    destination_port: string;
    final_destination: string;
  }[];
  cargo: string[];
  vessels: string[];
  stages: string[];
  start: string;
  end: string;
  default_time: string;
  version: string;
  shipments: string[];
}
export interface Prediction {
  shipment_id: string;
  observation_timestamp: string;
  stage: string;
  scheduled_eta: string;
  predicted_eta: string;
  delay: number;
  risk: Risk;
  version: string;
}
export interface ModelExplanation {
  name: string;
  delay: number;
  predicted_eta: string;
  base_hours: number;
  anchor_hours: number | null;
  contributions: {feature: string; hours: number; available: boolean}[];
  global_importance: {feature: string; value: number}[];
  global_method: string;
  local_method: string;
}
export interface Estimate extends Prediction {
  reported_conditions: Record<string,string>;
  comparisons: Record<string, ModelExplanation>;
  observed: Record<string, number | null>;
  summary: string;
  base_hours: number;
  contributions: { feature: string; hours: number }[];
}
export interface Shipment {
  attention_reasons?: string[];
  shipment_id: string;
  voyage_id: string;
  route_id: string;
  route: string;
  vessel: string;
  cargo: string;
  scheduled_eta: string;
  stage: string;
  status: string;
  prediction: Prediction | null;
}
export interface Page {
  items: Shipment[];
  page: number;
  total: number;
}
export interface Milestone {
  stage: string;
  order: number;
  scheduled: string;
  actual: string | null;
  released: string | null;
  state: string;
  deviation: number | null;
  change: number | null;
  added: number | null;
  recovered: number | null;
  across_gap: boolean;
}
export interface Detail extends Shipment {
  historical: boolean;
  actual_delivery: string | null;
  milestones: Milestone[];
}
export interface Journey {
  milestones: Milestone[];
  updates: (Prediction & { change_from_previous: number | null })[];
}
export interface DashboardData {
  total: number;
  active: number;
  delivered: number;
  average: number | null;
  on_time: number | null;
  risks: Record<Risk, number>;
  stages: Record<string, number>;
  trend: { date: string; predicted: number; observed: number; n: number }[];
  attention: Shipment[];
}
export interface Score {
  n: number;
  shipments: number;
  voyages: number;
  mae: number;
  rmse: number;
  median: number;
  p90: number;
  r2: number | null;
}
export interface Evaluation {
  comparison: Record<string, Score>;
  subgroups: (Score & { category: string; name: string })[];
  points: {
    snapshot_id: string;
    target_final_delay_hours: number;
    predicted: number;
  }[];
}
export interface FrozenComparison {
  selected: string;
  names: Record<string,string>;
  scores: Record<string, Score & {within_4_pct:number; within_6_pct:number; within_8_pct:number;
    severe: {n:number; shipments:number; mean_under:number}}>;
  stages: (Score & {candidate:string;stage:string})[];
  points: Record<string,number>[];
}
export interface Features {
  importance: { feature: string; increase_mae: number; sd: number }[];
  definitions: { column: string; business_meaning: string; unit: string }[];
}
export interface Scenario {
  baseline: Prediction;
  scenario: Prediction;
  change_delay: number;
  change_eta_hours: number;
  stage: string;
  hypothetical: boolean;
}
