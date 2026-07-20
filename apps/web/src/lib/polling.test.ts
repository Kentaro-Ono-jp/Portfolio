import { describe, expect, it } from "vitest";

import {
  STATUS_POLL_INTERVAL_MILLISECONDS,
  statusPollInterval,
} from "@/lib/polling";
import {
  completedStatus,
  failedStatus,
  processingStatus,
} from "@/test/fixtures";

describe("statusPollInterval", () => {
  it("polls before a status exists and during processing", () => {
    expect(statusPollInterval(undefined, false)).toBe(
      STATUS_POLL_INTERVAL_MILLISECONDS,
    );
    expect(statusPollInterval(processingStatus, false)).toBe(
      STATUS_POLL_INTERVAL_MILLISECONDS,
    );
  });

  it("stops on request error or either terminal state", () => {
    expect(statusPollInterval(processingStatus, true)).toBe(false);
    expect(statusPollInterval(completedStatus, false)).toBe(false);
    expect(statusPollInterval(failedStatus, false)).toBe(false);
  });
});
