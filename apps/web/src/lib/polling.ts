import type { DocumentStatus } from "@/lib/contracts";
import { isTerminalStatus } from "@/lib/contracts";

export const STATUS_POLL_INTERVAL_MILLISECONDS = 1_000;

export function statusPollInterval(
  status: DocumentStatus | undefined,
  hasError: boolean,
): number | false {
  if (hasError || (status !== undefined && isTerminalStatus(status))) {
    return false;
  }
  return STATUS_POLL_INTERVAL_MILLISECONDS;
}
