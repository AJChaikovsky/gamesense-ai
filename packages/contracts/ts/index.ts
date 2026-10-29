/* Generated from packages/contracts (Pydantic). Do not edit by hand. Run: npm run contracts:gen */

/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage = FeedbackMessage | ControlMessage;
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "EngineEvent".
 */
export type EngineEvent = HeartbeatEvent | TipEvent | StatusEvent;

/**
 * GameSense contracts v0.1.0. Generated; do not edit.
 */
export interface GameSenseContracts {
  CaptureStatus?: CaptureStatus;
  ClientMessage?: ClientMessage;
  CoachingDecision?: CoachingDecision;
  CoachingStatus?: CoachingStatus;
  Condition?: Condition;
  ControlMessage?: ControlMessage;
  EngineEvent?: EngineEvent;
  FeedbackMessage?: FeedbackMessage;
  GameState?: GameState;
  HabitObservation?: HabitObservation;
  HeartbeatEvent?: HeartbeatEvent;
  ModelAnalysis?: ModelAnalysis;
  Observation?: Observation;
  StatusEvent?: StatusEvent;
  TipEvent?: TipEvent;
}
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "CaptureStatus".
 */
export interface CaptureStatus {
  buffered_frames: number;
  /**
   * Measured frames per second entering the buffer.
   */
  fps: number;
  frame_height?: number | null;
  frame_width?: number | null;
  running: boolean;
  source: "none" | "replay" | "windows";
  /**
   * Clip path or window title.
   */
  target?: string | null;
}
/**
 * Sent by the desktop app when the player rates or dismisses a tip.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "FeedbackMessage".
 */
export interface FeedbackMessage {
  rating: "useful" | "not_useful" | "dismissed";
  tip_id: string;
  type?: "feedback";
}
/**
 * Sent by the desktop app to pause or resume coaching.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "ControlMessage".
 */
export interface ControlMessage {
  action: "pause" | "resume";
  type?: "control";
}
/**
 * A proposed tip, its justification and its delivery conditions.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "CoachingDecision".
 */
export interface CoachingDecision {
  /**
   * Machine-readable action, e.g. "heal_before_engaging".
   */
  action: string;
  /**
   * Skill area, e.g. "survivability" or "economy".
   */
  category: string;
  confidence: number;
  delivery: "immediate" | "next_lull" | "post_session";
  detail?: string | null;
  /**
   * Observation ids that justify this tip.
   */
  evidence?: string[];
  expires_in_seconds: number;
  id: string;
  /**
   * Headline shown on the overlay (<= 8 words).
   */
  message: string;
  priority: "info" | "important" | "urgent";
  valid_while?: Condition[];
}
/**
 * A condition that must still hold for a tip to be shown (stale-result validator).
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "Condition".
 */
export interface Condition {
  observation_type: string;
  op: "eq" | "ne" | "lt" | "le" | "gt" | "ge" | "present" | "absent";
  value?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "CoachingStatus".
 */
export interface CoachingStatus {
  /**
   * Model calls this session.
   */
  calls: number;
  game_id?: string | null;
  game_name?: string | null;
  hourly_budget_usd: number;
  /**
   * A model request is currently running.
   */
  in_flight: boolean;
  last_latency_ms?: number | null;
  /**
   * False when the game's policy blocks live coaching.
   */
  live_allowed: boolean;
  model: string;
  paused: boolean;
  policy_reason?: string | null;
  provider: string;
  /**
   * Estimated model spend this session.
   */
  spend_usd: number;
  spend_usd_last_hour: number;
  tips_delivered: number;
}
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "HeartbeatEvent".
 */
export interface HeartbeatEvent {
  capture: CaptureStatus;
  coaching?: CoachingStatus | null;
  engine_version: string;
  timestamp: string;
  type?: "heartbeat";
  uptime_seconds: number;
}
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "TipEvent".
 */
export interface TipEvent {
  decision: CoachingDecision;
  timestamp: string;
  type?: "tip";
}
/**
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "StatusEvent".
 */
export interface StatusEvent {
  level: "ok" | "degraded" | "offline";
  message: string;
  timestamp: string;
  type?: "status";
}
/**
 * Standardized snapshot of the player's current situation.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "GameState".
 */
export interface GameState {
  /**
   * High-level activity, e.g. "exploration" or "combat".
   */
  activity?: string | null;
  /**
   * Ring-buffer frame ids used as evidence.
   */
  frame_refs?: string[];
  game_id: string;
  /**
   * Adapter-defined extension fields.
   */
  game_specific?: {
    [k: string]: unknown;
  };
  genre: string;
  observations?: Observation[];
  session_id: string;
  timestamp: string;
  /**
   * Things that matter but cannot be determined.
   */
  unknowns?: string[];
}
/**
 * One fact or inference about the current game situation.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "Observation".
 */
export interface Observation {
  /**
   * Estimated confidence; not a calibrated probability.
   */
  confidence: number;
  id: string;
  /**
   * Observed facts are visible on screen or in telemetry; inferences are not.
   */
  kind: "observed" | "inferred";
  source: "visual" | "ocr" | "telemetry" | "model" | "rule";
  /**
   * Observation kind, e.g. "health_low" or "enemy_visible".
   */
  type: string;
  value?: {
    [k: string]: unknown;
  };
}
/**
 * Evidence that may contribute to the player's long-term skill profile.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "HabitObservation".
 */
export interface HabitObservation {
  behavior: string;
  confidence: number;
  evidence?: string[];
  evidence_count: number;
  session_id: string;
  skill: string;
}
/**
 * Structured output requested from the live vision model on each trigger.
 *
 * This interface was referenced by `GameSenseContracts`'s JSON-Schema
 * via the `definition` "ModelAnalysis".
 */
export interface ModelAnalysis {
  /**
   * Null when the coach should stay silent.
   */
  decision?: CoachingDecision | null;
  state: GameState;
}
