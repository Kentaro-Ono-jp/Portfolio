import { describe, expect, it } from "vitest";

import {
  documentAcceptedSchema,
  documentStatusSchema,
  isTerminalStatus,
  problemSchema,
} from "@/lib/contracts";
import {
  acceptedDocument,
  acceptedStatus,
  canonicalProblem,
  STARTED_AT,
  completedStatus,
  failedStatus,
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

  it("identifies only terminal states", () => {
    expect(isTerminalStatus(completedStatus)).toBe(true);
    expect(isTerminalStatus(failedStatus)).toBe(true);
    expect(isTerminalStatus(processingStatus)).toBe(false);
  });
});
