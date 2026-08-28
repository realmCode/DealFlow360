/**
 * The backend's error vocabulary, treated as product surface rather than
 * failure noise.
 *
 * Every non-2xx response uses one envelope:
 *   { "error": { "code": "STALE_APPROVAL", "message": "...", "details": {} } }
 *
 * Branch on `code`, never on `message`.
 */

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> };
}

export class DealFlowError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "DealFlowError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  is(...codes: string[]) {
    return codes.includes(this.code);
  }

  /** Typed accessors for the details the UI actually branches on. */
  get allowedRoles(): string[] | undefined {
    return this.details.allowed_roles as string[] | undefined;
  }
  get yourRole(): string | undefined {
    return this.details.your_role as string | undefined;
  }
  get editableStatuses(): string[] | undefined {
    return this.details.editable_statuses as string[] | undefined;
  }
  get awaiting(): string[] | undefined {
    return this.details.awaiting as string[] | undefined;
  }
  get retryAfterSeconds(): number | undefined {
    return this.details.retry_after_seconds as number | undefined;
  }
  get validationErrors(): { loc: (string | number)[]; msg: string }[] | undefined {
    return this.details.errors as { loc: (string | number)[]; msg: string }[] | undefined;
  }
}

export const isDealFlowError = (e: unknown): e is DealFlowError => e instanceof DealFlowError;

/** 409s that mean "the effect you wanted already happened" — refetch, don't shout. */
export const SUCCESS_CONFLICTS = ["ALREADY_CONFIRMED", "DUPLICATE_OPERATION"];

/** Codes that get a bespoke full-surface treatment rather than a toast. */
export const NARRATIVE_CODES = [
  "STALE_APPROVAL",
  "APPROVAL_REQUIRED",
  "IMMUTABLE_VERSION",
  "VERSION_NOT_DRAFT",
  "VERSION_TERMINAL",
  "VERSION_NOT_APPROVED",
  "INSUFFICIENT_INVENTORY",
  "SELF_APPROVAL_FORBIDDEN",
];

/**
 * Human copy for the codes a user can actually hit. Falls back to the
 * backend's own message, which the API documentation states is safe to show.
 */
const COPY: Record<string, { title: string; hint?: string }> = {
  STALE_APPROVAL: {
    title: "This quotation changed after approval",
    hint: "The previous approval is no longer valid. Review what changed, then request re-approval.",
  },
  APPROVAL_REQUIRED: {
    title: "Approval is still outstanding",
    hint: "This quotation cannot proceed until every required approver has decided.",
  },
  IMMUTABLE_VERSION: {
    title: "This version is locked",
    hint: "Only a DRAFT version can be edited. Create a revision to make changes.",
  },
  VERSION_NOT_DRAFT: {
    title: "This version is locked",
    hint: "Only a DRAFT version can be edited. Create a revision to make changes.",
  },
  VERSION_TERMINAL: {
    title: "This version is final",
    hint: "Confirmed, rejected and superseded versions cannot be revised.",
  },
  VERSION_NOT_APPROVED: {
    title: "Not approved yet",
    hint: "Only an approved version can be sent to the customer.",
  },
  VERSION_NOT_CONFIRMABLE: { title: "This quotation cannot be confirmed yet" },
  SELF_APPROVAL_FORBIDDEN: {
    title: "You cannot approve your own quotation",
    hint: "Separation of duties requires a different approver.",
  },
  WRONG_APPROVER_ROLE: { title: "This step needs a different approver" },
  NO_PENDING_STEP: {
    title: "Already decided",
    hint: "Someone else decided this step while you had it open.",
  },
  APPROVAL_NOT_PENDING: { title: "This approval is no longer pending" },
  INSUFFICIENT_INVENTORY: {
    title: "Not enough stock to allocate in full",
    hint: "You can allocate what is available and backorder the remainder.",
  },
  IDEMPOTENT_REQUEST_IN_FLIGHT: { title: "Still working on your last request" },
  IDEMPOTENCY_KEY_REUSED: {
    title: "That request was already used with different details",
    hint: "Try the action again to start a fresh request.",
  },
  FORBIDDEN: { title: "You do not have permission for this action" },
  PORTAL_USER_FORBIDDEN: { title: "This area is for internal users" },
  INTERNAL_USER_FORBIDDEN: { title: "This area is for customers" },
  NOT_FOUND: { title: "Not found" },
  RATE_LIMITED: { title: "Too many attempts", hint: "Wait a moment and try again." },
  VALIDATION_ERROR: { title: "Check the highlighted fields" },
  AUTHENTICATION_FAILED: { title: "Your session has expired", hint: "Sign in again to continue." },
  USER_DISABLED: { title: "This account is disabled" },
  ORGANIZATION_DISABLED: { title: "This organisation is disabled" },
  INTERNAL_ERROR: { title: "Something went wrong on the server" },
  NETWORK_ERROR: {
    title: "Cannot reach DealFlow360",
    hint: "Check that the API is running, then retry.",
  },
};

export const errorTitle = (e: unknown): string => {
  if (isDealFlowError(e)) return COPY[e.code]?.title ?? e.message;
  return e instanceof Error ? e.message : "Something went wrong";
};

export const errorHint = (e: unknown): string | undefined => {
  if (!isDealFlowError(e)) return undefined;
  return COPY[e.code]?.hint ?? (COPY[e.code] ? undefined : e.message);
};
