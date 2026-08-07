import { describe, expect, it } from "vitest";

import {
  auditHistorySchema,
  documentAcceptedSchema,
  documentStatusSchema,
  isTerminalStatus,
  problemSchema,
} from "@/lib/contracts";
import {
  acceptedDocument,
  acceptedStatus,
  auditHistoryWithTimestamps,
  canonicalProblem,
  STARTED_AT,
  completedStatus,
  failedStatus,
  legacyCompletedStatus,
  measuredModelEvidence,
  processingStatus,
  queuedStatus,
} from "@/test/fixtures";

describe("generated contract runtime schemas", () => {
  it("accepts the submission and all five status variants", () => {
    expect(documentAcceptedSchema.parse(acceptedDocument)).toEqual(
      acceptedDocument,
    );
    for (const status of [
      acceptedStatus,
      queuedStatus,
      processingStatus,
      completedStatus,
      legacyCompletedStatus,
      failedStatus,
      { ...failedStatus, startedAt: STARTED_AT },
    ]) {
      expect(documentStatusSchema.parse(status)).toEqual(status);
    }
  });

  it("accepts problems with or without detail", () => {
    expect(problemSchema.parse(canonicalProblem)).toEqual(canonicalProblem);
    const withoutDetail = {
      type: canonicalProblem.type,
      title: canonicalProblem.title,
      status: canonicalProblem.status,
      code: canonicalProblem.code,
      correlationId: canonicalProblem.correlationId,
    };
    expect(problemSchema.parse(withoutDetail)).toEqual(withoutDetail);
  });

  it("rejects impossible or extended payloads", () => {
    expect(
      documentAcceptedSchema.safeParse({
        ...acceptedDocument,
        unexpected: true,
      }).success,
    ).toBe(false);
    expect(
      documentStatusSchema.safeParse({ ...completedStatus, confidence: 1.1 })
        .success,
    ).toBe(false);
    expect(
      documentStatusSchema.safeParse({
        ...failedStatus,
        failureCode: "raw failure",
      }).success,
    ).toBe(false);
    expect(
      problemSchema.safeParse({ ...canonicalProblem, status: 200 }).success,
    ).toBe(false);
  });

  it("rejects partial, mixed, or malformed measured evidence", () => {
    const partialEvidence: Record<string, unknown> = {
      ...measuredModelEvidence,
    };
    delete partialEvidence.datasetSha256;
    for (const modelEvidence of [
      partialEvidence,
      {
        status: "legacy-unmeasured",
        datasetVersion: measuredModelEvidence.datasetVersion,
      },
      { ...measuredModelEvidence, artifactSha256: "g".repeat(64) },
      { ...measuredModelEvidence, unexpected: true },
    ]) {
      expect(
        documentStatusSchema.safeParse({ ...completedStatus, modelEvidence })
          .success,
      ).toBe(false);
    }
  });

  it("orders offset audit timestamps by instant and event identity", () => {
    const chronological = auditHistoryWithTimestamps(
      "2026-01-01T00:00:00Z",
      "2025-12-31T19:00:00.100000-05:00",
      "2026-01-01T01:00:01+01:00",
    );
    expect(auditHistorySchema.safeParse(chronological).success).toBe(true);
    expect(
      auditHistorySchema.safeParse({
        ...chronological,
        events: [
          chronological.events[1]!,
          chronological.events[0]!,
          chronological.events[2]!,
        ],
      }).success,
    ).toBe(false);

    const tiedInstants = auditHistoryWithTimestamps(
      "2026-01-01T00:00:00Z",
      "2025-12-31T19:00:00.000000-05:00",
      "2026-01-01T00:00:01Z",
    );
    expect(auditHistorySchema.safeParse(tiedInstants).success).toBe(true);
    expect(
      auditHistorySchema.safeParse({
        ...tiedInstants,
        events: [
          tiedInstants.events[1]!,
          tiedInstants.events[0]!,
          tiedInstants.events[2]!,
        ],
      }).success,
    ).toBe(false);
  });

  it("identifies only terminal states", () => {
    expect(isTerminalStatus(completedStatus)).toBe(true);
    expect(isTerminalStatus(failedStatus)).toBe(true);
    expect(isTerminalStatus(processingStatus)).toBe(false);
  });
});
