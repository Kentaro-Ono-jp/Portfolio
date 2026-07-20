import type { components } from "@reactorfront/contracts";
import { z } from "zod";

export type DocumentAccepted = components["schemas"]["DocumentAccepted"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type Problem = components["schemas"]["Problem"];

const identifierSchema = z.string().uuid();
const timestampSchema = z.string().datetime({ offset: true });

export const documentIdSchema = identifierSchema;
export const correlationIdSchema = identifierSchema;

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

const completedStatusSchema = z.strictObject({
  documentId: identifierSchema,
  jobId: identifierSchema,
  status: z.literal("completed"),
  classification: z.enum(["invoice", "report"]),
  confidence: z.number().min(0).max(1),
  modelVersion: z.string().min(1).max(128),
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
