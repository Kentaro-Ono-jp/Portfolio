import type {
  DocumentAccepted,
  DocumentStatus,
  Problem,
} from "@/lib/contracts";

export const DOCUMENT_ID = "11111111-1111-4111-8111-111111111111";
export const JOB_ID = "22222222-2222-4222-8222-222222222222";
export const CORRELATION_ID = "33333333-3333-4333-8333-333333333333";
export const CREATED_AT = "2026-07-20T00:00:00Z";
export const STARTED_AT = "2026-07-20T00:00:01Z";
export const COMPLETED_AT = "2026-07-20T00:00:02Z";

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
