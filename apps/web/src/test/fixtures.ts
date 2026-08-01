import type {
  AuditHistory,
  DocumentAccepted,
  DocumentStatus,
  Problem,
  Review,
  TerminalReview,
} from "@/lib/contracts";

export const DOCUMENT_ID = "11111111-1111-4111-8111-111111111111";
export const JOB_ID = "22222222-2222-4222-8222-222222222222";
export const CORRELATION_ID = "33333333-3333-4333-8333-333333333333";
export const CREATED_AT = "2026-07-20T00:00:00Z";
export const STARTED_AT = "2026-07-20T00:00:01Z";
export const COMPLETED_AT = "2026-07-20T00:00:02Z";
export const DECIDED_AT = "2026-07-20T00:00:03Z";
export const REVIEWER_PRINCIPAL_ID = "44444444-4444-4444-8444-444444444444";
export const REVIEW_ID = "55555555-5555-4555-8555-555555555555";
export const REVIEW_ENTITY_TAG = `"${"a".repeat(64)}"`;

export const acceptedDocument: DocumentAccepted = {
  documentId: DOCUMENT_ID,
  jobId: JOB_ID,
  status: "accepted",
};

export const acceptedStatus: DocumentStatus = {
  ...acceptedDocument,
  createdAt: CREATED_AT,
};

export const queuedStatus: DocumentStatus = {
  ...acceptedDocument,
  status: "queued",
  createdAt: CREATED_AT,
};

export const processingStatus: DocumentStatus = {
  ...acceptedDocument,
  status: "processing",
  createdAt: CREATED_AT,
  startedAt: STARTED_AT,
};

export const completedStatus: DocumentStatus = {
  ...processingStatus,
  status: "completed",
  classification: "invoice",
  confidence: 0.987,
  modelVersion: "document-type-v1",
  completedAt: COMPLETED_AT,
};

export const failedStatus: DocumentStatus = {
  ...acceptedDocument,
  status: "failed",
  failureCode: "SOURCE_DIGEST_MISMATCH",
  createdAt: CREATED_AT,
  completedAt: COMPLETED_AT,
};

export const canonicalProblem: Problem = {
  type: "/problems/unsupported-media-type",
  title: "Unsupported media type",
  status: 415,
  detail: "Only application/pdf is supported.",
  code: "UNSUPPORTED_MEDIA_TYPE",
  correlationId: CORRELATION_ID,
};

export const unreviewedReview: Review = {
  documentId: DOCUMENT_ID,
  jobId: JOB_ID,
  status: "unreviewed",
  machineClassification: "invoice",
  machineConfidence: 0.987,
  modelVersion: "document-type-v1",
  reviewVersion: 0,
};

export const approvedReview: TerminalReview = {
  documentId: DOCUMENT_ID,
  jobId: JOB_ID,
  status: "approved",
  machineClassification: "invoice",
  machineConfidence: 0.987,
  modelVersion: "document-type-v1",
  reviewVersion: 1,
  finalClassification: "invoice",
  reviewerPrincipalId: REVIEWER_PRINCIPAL_ID,
  decidedAt: DECIDED_AT,
};

export const correctedReview: TerminalReview = {
  documentId: DOCUMENT_ID,
  jobId: JOB_ID,
  status: "corrected",
  machineClassification: "invoice",
  machineConfidence: 0.987,
  modelVersion: "document-type-v1",
  reviewVersion: 1,
  finalClassification: "report",
  reviewerPrincipalId: REVIEWER_PRINCIPAL_ID,
  decidedAt: DECIDED_AT,
};

export const auditHistory: AuditHistory = {
  documentId: DOCUMENT_ID,
  events: [
    {
      eventId: "66666666-6666-4666-8666-666666666666",
      action: "document.submitted",
      occurredAt: CREATED_AT,
      actorPrincipalId: REVIEWER_PRINCIPAL_ID,
      documentId: DOCUMENT_ID,
      jobId: JOB_ID,
      correlationId: CORRELATION_ID,
      detailsVersion: 1,
      details: {},
    },
    {
      eventId: "77777777-7777-4777-8777-777777777777",
      action: "processing.completed",
      occurredAt: COMPLETED_AT,
      actorPrincipalId: REVIEWER_PRINCIPAL_ID,
      documentId: DOCUMENT_ID,
      jobId: JOB_ID,
      correlationId: "88888888-8888-4888-8888-888888888888",
      detailsVersion: 1,
      details: {},
    },
    {
      eventId: "99999999-9999-4999-8999-999999999999",
      action: "review.approved",
      occurredAt: DECIDED_AT,
      actorPrincipalId: REVIEWER_PRINCIPAL_ID,
      documentId: DOCUMENT_ID,
      jobId: JOB_ID,
      reviewId: REVIEW_ID,
      correlationId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      detailsVersion: 1,
      details: {},
    },
  ],
};
