import type { components } from "@reactorfront/contracts";
import { z } from "zod";

export type DocumentAccepted = components["schemas"]["DocumentAccepted"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type ReviewDecisionRequest =
  components["schemas"]["ReviewDecisionRequest"];
export type Review = components["schemas"]["Review"];
export type TerminalReview = components["schemas"]["TerminalReview"];
export type AuditHistory = components["schemas"]["AuditHistory"];
export type Problem = components["schemas"]["Problem"];

const identifierSchema = z.string().uuid();
const timestampSchema = z.string().datetime({ offset: true });
const timestampPartsPattern =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|([+-])(\d{2}):(\d{2}))$/u;

interface AuditOrderPosition {
  epochSecond: number;
  fraction: string;
  eventId: string;
}

function auditOrderPosition(
  occurredAt: string,
  eventId: string,
): AuditOrderPosition | null {
  const parts = timestampPartsPattern.exec(occurredAt);
  if (parts === null) {
    return null;
  }
  const [
    ,
    year,
    month,
    day,
    hour,
    minute,
    second,
    fraction = "",
    zone,
    sign,
    offsetHour = "00",
    offsetMinute = "00",
  ] = parts;
  const utc = new Date(0);
  utc.setUTCFullYear(Number(year), Number(month) - 1, Number(day));
  utc.setUTCHours(Number(hour), Number(minute), Number(second), 0);
  const offsetSeconds =
    zone === "Z"
      ? 0
      : (sign === "+" ? 1 : -1) *
        (Number(offsetHour) * 60 + Number(offsetMinute)) *
        60;
  return {
    epochSecond: utc.getTime() / 1000 - offsetSeconds,
    fraction,
    eventId: eventId.toLowerCase(),
  };
}

function compareAuditOrder(
  left: AuditOrderPosition,
  right: AuditOrderPosition,
): number {
  if (left.epochSecond !== right.epochSecond) {
    return left.epochSecond < right.epochSecond ? -1 : 1;
  }
  const fractionWidth = Math.max(left.fraction.length, right.fraction.length);
  const leftFraction = left.fraction.padEnd(fractionWidth, "0");
  const rightFraction = right.fraction.padEnd(fractionWidth, "0");
  if (leftFraction !== rightFraction) {
    return leftFraction < rightFraction ? -1 : 1;
  }
  if (left.eventId === right.eventId) {
    return 0;
  }
  return left.eventId < right.eventId ? -1 : 1;
}

export const documentIdSchema = identifierSchema;
export const correlationIdSchema = identifierSchema;
export const reviewEntityTagSchema = z.string().regex(/^"[a-f0-9]{64}"$/);

export const documentAcceptedSchema: z.ZodType<DocumentAccepted> =
  z.strictObject({
    documentId: identifierSchema,
    jobId: identifierSchema,
    status: z.literal("accepted"),
  });

const acceptedStatusSchema = z.strictObject({
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("accepted"),
  createdAt: timestampSchema,
});

const queuedStatusSchema = z.strictObject({
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("queued"),
  createdAt: timestampSchema,
});

const processingStatusSchema = z.strictObject({
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("processing"),
  createdAt: timestampSchema,
  startedAt: timestampSchema,
});

const sha256Schema = z.string().regex(/^[a-f0-9]{64}$/);
const legacyModelEvidenceSchema = z.strictObject({
  status: z.literal("legacy-unmeasured"),
});
const measuredModelEvidenceSchema = z.strictObject({
  status: z.literal("measured"),
  datasetVersion: z.string().min(1).max(128),
  datasetSha256: sha256Schema,
  preprocessingVersion: z.string().min(1).max(128),
  pipelineVersion: z.string().min(1).max(128),
  artifactSha256: sha256Schema,
  evaluationPolicyVersion: z.string().min(1).max(128),
  evaluationPolicySha256: sha256Schema,
  evaluationReportSha256: sha256Schema,
});
const modelEvidenceSchema = z.discriminatedUnion("status", [
  legacyModelEvidenceSchema,
  measuredModelEvidenceSchema,
]);

const completedStatusSchema = z.strictObject({
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("completed"),
  classification: z.enum(["invoice", "report"]),
  confidence: z.number().min(0).max(1),
  modelVersion: z.string().min(1).max(128),
  modelEvidence: modelEvidenceSchema,
  createdAt: timestampSchema,
  startedAt: timestampSchema,
  completedAt: timestampSchema,
});

const failedStatusFields = {
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("failed"),
  failureCode: z
    .string()
    .regex(/^[A-Z][A-Z0-9_]*$/)
    .max(128),
  createdAt: timestampSchema,
  completedAt: timestampSchema,
};

const failedStatusSchema = z.union([
  z.strictObject(failedStatusFields),
  z.strictObject({ ...failedStatusFields, startedAt: timestampSchema }),
]);

export const documentStatusSchema: z.ZodType<DocumentStatus> = z.union([
  acceptedStatusSchema,
  queuedStatusSchema,
  processingStatusSchema,
  completedStatusSchema,
  failedStatusSchema,
]);

const classificationSchema = z.enum(["invoice", "report"]);
const reviewMachineFields = {
  documentId: identifierSchema,
  jobId: identifierSchema,
  machineConfidence: z.number().min(0).max(1),
  modelVersion: z.string().min(1).max(128),
  modelEvidence: modelEvidenceSchema,
};

const unreviewedReviewSchema = z.strictObject({
  ...reviewMachineFields,
  status: z.literal("unreviewed"),
  machineClassification: classificationSchema,
  reviewVersion: z.literal(0),
});

const approvedReviewSchema = z.union([
  z.strictObject({
    ...reviewMachineFields,
    status: z.literal("approved"),
    machineClassification: z.literal("invoice"),
    reviewVersion: z.literal(1),
    finalClassification: z.literal("invoice"),
    reviewerPrincipalId: identifierSchema,
    decidedAt: timestampSchema,
  }),
  z.strictObject({
    ...reviewMachineFields,
    status: z.literal("approved"),
    machineClassification: z.literal("report"),
    reviewVersion: z.literal(1),
    finalClassification: z.literal("report"),
    reviewerPrincipalId: identifierSchema,
    decidedAt: timestampSchema,
  }),
]);

const correctedReviewSchema = z.union([
  z.strictObject({
    ...reviewMachineFields,
    status: z.literal("corrected"),
    machineClassification: z.literal("invoice"),
    reviewVersion: z.literal(1),
    finalClassification: z.literal("report"),
    reviewerPrincipalId: identifierSchema,
    decidedAt: timestampSchema,
  }),
  z.strictObject({
    ...reviewMachineFields,
    status: z.literal("corrected"),
    machineClassification: z.literal("report"),
    reviewVersion: z.literal(1),
    finalClassification: z.literal("invoice"),
    reviewerPrincipalId: identifierSchema,
    decidedAt: timestampSchema,
  }),
]);

export const reviewDecisionRequestSchema: z.ZodType<ReviewDecisionRequest> =
  z.strictObject({ finalClassification: classificationSchema });

export const reviewSchema: z.ZodType<Review> = z.union([
  unreviewedReviewSchema,
  approvedReviewSchema,
  correctedReviewSchema,
]);

export const terminalReviewSchema: z.ZodType<TerminalReview> = z.union([
  approvedReviewSchema,
  correctedReviewSchema,
]);

const auditIdentityFields = {
  eventId: identifierSchema,
  action: z.enum([
    "document.submitted",
    "processing.completed",
    "processing.failed",
    "review.approved",
    "review.corrected",
  ]),
  occurredAt: timestampSchema,
  actorPrincipalId: identifierSchema,
  documentId: identifierSchema,
  jobId: identifierSchema,
  correlationId: identifierSchema,
};

const auditEventSchema = z.union([
  z.strictObject({
    ...auditIdentityFields,
    detailsVersion: z.literal(1),
    details: z.strictObject({}),
  }),
  z.strictObject({
    ...auditIdentityFields,
    reviewId: identifierSchema,
    detailsVersion: z.literal(1),
    details: z.strictObject({}),
  }),
  z.strictObject({
    ...auditIdentityFields,
    action: z.literal("processing.completed"),
    detailsVersion: z.literal(2),
    details: z.strictObject({
      modelEvidenceStatus: z.literal("measured"),
      modelVersion: z.string().min(1).max(128),
      datasetVersion: z.string().min(1).max(128),
      datasetSha256: sha256Schema,
      preprocessingVersion: z.string().min(1).max(128),
      pipelineVersion: z.string().min(1).max(128),
      artifactSha256: sha256Schema,
      evaluationPolicyVersion: z.string().min(1).max(128),
      evaluationPolicySha256: sha256Schema,
      evaluationReportSha256: sha256Schema,
    }),
  }),
]);

export const auditHistorySchema: z.ZodType<AuditHistory> = z
  .strictObject({
    documentId: identifierSchema,
    events: z.array(auditEventSchema),
  })
  .superRefine((history, context) => {
    let previous: AuditOrderPosition | null = null;
    const eventIds = new Set<string>();
    history.events.forEach((event, index) => {
      const canonicalEventId = event.eventId.toLowerCase();
      if (event.documentId !== history.documentId) {
        context.addIssue({
          code: "custom",
          message: "Audit event document identity does not match its history.",
          path: ["events", index, "documentId"],
        });
      }
      const orderPosition = auditOrderPosition(event.occurredAt, event.eventId);
      if (
        previous !== null &&
        orderPosition !== null &&
        compareAuditOrder(orderPosition, previous) <= 0
      ) {
        context.addIssue({
          code: "custom",
          message: "Audit events are not in deterministic append order.",
          path: ["events", index],
        });
      }
      if (eventIds.has(canonicalEventId)) {
        context.addIssue({
          code: "custom",
          message: "Audit event identity is duplicated.",
          path: ["events", index, "eventId"],
        });
      }
      previous = orderPosition;
      eventIds.add(canonicalEventId);
    });
  });

const problemFields = {
  type: z.string().min(1),
  title: z.string().min(1),
  status: z.number().int().min(400).max(599),
  code: z.string().regex(/^[A-Z][A-Z0-9_]*$/),
  correlationId: correlationIdSchema,
};

export const problemSchema: z.ZodType<Problem> = z.union([
  z.strictObject(problemFields),
  z.strictObject({ ...problemFields, detail: z.string() }),
]);

export function isTerminalStatus(status: DocumentStatus): boolean {
  return status.status === "completed" || status.status === "failed";
}
