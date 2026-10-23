/**
 * Live-talk ("charla") API types: the TypeScript mirror of planning/charla/CONTRACT.md §5–§6.
 * Owned by team-lead. Don't redefine these elsewhere; ask the lead to change them.
 */

export type StepKind = "quiz" | "open" | "closing";
export type Phase = "idle" | "open" | "closed" | "revealed";
export type PhoneStatus = "none" | "given" | "skipped";
export type SalaView = "wait" | "question" | "answered" | "result" | "open" | "phone" | "end";

export interface PublicQuestion {
  text: string;
  /** Four options for a quiz; [] for the open question. */
  options: string[];
  /** Only for the open question. */
  placeholder: string | null;
}

export interface Reveal {
  /** Correct option index (quiz) or null (open). */
  answer: number | null;
  why: string | null;
  /** Answers per option (quiz) or null (open). */
  distribution: number[] | null;
}

export interface RoomState {
  version: number;
  server_now_ms: number;
  step: number; // 0..8
  kind: StepKind;
  phase: Phase;
  /** 1..7 for quiz steps, null otherwise. */
  number: number | null;
  total_quiz: number;
  /** Only while phase === "open"; count down locally from the moment it arrived. */
  remaining_ms: number | null;
  duration_ms: number | null;
  /** null at the closing step. */
  question: PublicQuestion | null;
  /** Only when phase === "revealed". */
  reveal: Reveal | null;
  phone_prompt: boolean;
  room_count: number;
}

export interface MyAnswer {
  step: number;
  choice: number | null;
  text: string | null;
}

export interface MyResult {
  /** null for the open question. */
  correct: boolean | null;
  points: number;
}

export interface Me {
  attendee_id: string;
  username: string;
  verified: boolean;
  /** Settled steps only (a step counts once revealed or left behind). */
  score: number;
  rank: number | null;
  /** My answer to the current step. */
  answer: MyAnswer | null;
  /** Current step's result, only once revealed. */
  result: MyResult | null;
  phone_status: PhoneStatus;
}

/** Body of GET /api/charla/me and every attendee SSE event. */
export interface AttendeeView {
  state: RoomState;
  me: Me | null;
}

// --- registration -----------------------------------------------------------------------------

export interface UsernameCheck {
  valid: boolean;
  available: boolean;
  message: string | null;
  suggestion: string | null;
}

export type RegisterResponse =
  | {
      status: "link_sent";
      pending: string;
      email: string;
      username: string;
      resend_in_s: number;
      /** Only when the server runs with CHARLA_DEV_LINKS (tests). */
      dev_link_token?: string;
    }
  | { status: "in"; token: string; username: string };

export type StatusResponse = { status: "waiting" } | { status: "in"; token: string; username: string };

export interface VerifyResponse {
  token: string;
  username: string;
}

export type AnswerBody = { step: number; choice: number } | { step: number; text: string };
export type PhoneBody = { phone: string; consent: boolean } | { skip: true };

// --- presenter (admin) ------------------------------------------------------------------------

export interface AdminState extends RoomState {
  verification_on: boolean;
  /** "HH:MM" Bogotá, or null when the automatic prompt is off. */
  phone_prompt_at: string | null;
  deadline_ms: number | null;
  opened_at_ms: number | null;
}

export interface ScriptStep {
  step: number;
  kind: StepKind;
  title: string;
  /** Quiz only. */
  options: string[];
  answer: number | null;
  why: string | null;
}

export interface AdminCounts {
  registered: number;
  active: number;
  verified: number;
  pending: number;
  with_phone: number;
  /** Current step. */
  answered: number;
  correct: number;
}

export interface ThemeCount {
  name: string;
  count: number;
}

export interface Quote {
  answer_id: string;
  attendee_id: string;
  username: string;
  text: string;
  theme: string | null;
  hidden: boolean;
  created_at: string;
}

export interface RankingRow {
  rank: number;
  attendee_id: string;
  username: string;
  score: number;
  correct: number;
  verified: boolean;
  hidden: boolean;
}

export interface EmailStats {
  queued: number;
  sent: number;
  failed: number;
  last_error: string | null;
}

/** Every admin SSE event. */
export interface AdminView {
  version: number;
  server_now_ms: number;
  state: AdminState;
  script: ScriptStep[];
  counts: AdminCounts;
  /** Live answers per option for the current quiz step, else null. */
  distribution: number[] | null;
  themes: ThemeCount[];
  quotes: Quote[];
  ranking: RankingRow[];
  email: EmailStats;
}

export type HideBody = { answer_id: string; hidden: boolean } | { attendee_id: string; hidden: boolean };
