"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import {
  createDocument,
  DocumentRequestError,
  getDocument,
  problemGuidance,
  terminalFailureGuidance,
} from "@/lib/browser-api";
import {
  isTerminalStatus,
  type DocumentAccepted,
  type DocumentStatus,
} from "@/lib/contracts";
import { validatePdfFile } from "@/lib/file-validation";
import { statusPollInterval } from "@/lib/polling";

const PROGRESS_STATES = [
  "accepted",
  "queued",
  "processing",
  "completed",
] as const;

function statusLabel(
  status: DocumentAccepted["status"] | DocumentStatus["status"],
): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function progressIndex(
  status: DocumentAccepted["status"] | DocumentStatus["status"],
): number {
  if (status === "failed") {
    return 2;
  }
  return PROGRESS_STATES.indexOf(status);
}

export function DocumentWorkflow() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<DocumentAccepted | null>(null);

  const submission = useMutation({
    mutationFn: createDocument,
    onSuccess: (result) => {
      setAccepted(result);
      setLocalError(null);
    },
  });

  const statusQuery = useQuery({
    queryKey: ["document-status", accepted?.documentId],
    queryFn: () => getDocument(accepted!.documentId),
    enabled: accepted !== null,
    refetchInterval: (query) =>
      statusPollInterval(query.state.data, query.state.status === "error"),
    refetchOnReconnect: (query) =>
      statusPollInterval(query.state.data, query.state.status === "error") !==
      false,
  });

  const currentStatus = statusQuery.data?.status ?? accepted?.status;
  const terminal =
    statusQuery.data !== undefined && isTerminalStatus(statusQuery.data);
  const requestError =
    submission.error instanceof DocumentRequestError
      ? submission.error
      : statusQuery.error instanceof DocumentRequestError
        ? statusQuery.error
        : null;
  const isLocked = submission.isPending || accepted !== null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isLocked) {
      return;
    }
    const validationError = validatePdfFile(file);
    if (validationError !== null) {
      setLocalError(validationError);
      return;
    }
    setLocalError(null);
    submission.mutate(file!);
  }

  function reset() {
    if (accepted !== null) {
      queryClient.removeQueries({
        queryKey: ["document-status", accepted.documentId],
      });
    }
    submission.reset();
    setAccepted(null);
    setFile(null);
    setLocalError(null);
    if (inputRef.current !== null) {
      inputRef.current.value = "";
      queueMicrotask(() => inputRef.current?.focus());
    }
  }

  return (
    <section className="workflow-shell" aria-labelledby="workflow-title">
      <div className="flex items-start justify-between gap-4 border-b border-slate-200/80 px-6 py-5 sm:px-8">
        <div>
          <p className="font-mono text-xs uppercase tracking-[0.18em] text-teal-700">
            Live workflow
          </p>
          <h2
            id="workflow-title"
            className="mt-2 text-2xl font-semibold tracking-tight text-slate-950"
          >
            Classify a document
          </h2>
        </div>
        <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
          CPU inference
        </span>
      </div>

      <div className="px-6 py-6 sm:px-8 sm:py-8">
        <form onSubmit={submit} aria-busy={submission.isPending} noValidate>
          <label
            htmlFor="document-file"
            className="text-sm font-semibold text-slate-900"
          >
            Source PDF
          </label>
          <div className="mt-3 rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 p-5 transition focus-within:border-teal-600 focus-within:ring-4 focus-within:ring-teal-100">
            <input
              ref={inputRef}
              id="document-file"
              name="file"
              type="file"
              accept="application/pdf,.pdf"
              disabled={isLocked}
              className="block w-full cursor-pointer text-sm text-slate-600 file:mr-4 file:rounded-full file:border-0 file:bg-slate-900 file:px-4 file:py-2.5 file:text-sm file:font-semibold file:text-white hover:file:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
              onChange={(event) => {
                setFile(event.currentTarget.files?.item(0) ?? null);
                setLocalError(null);
                submission.reset();
              }}
            />
            <p className="mt-3 text-xs leading-5 text-slate-500">
              One extractable-text PDF, maximum 5 MiB. The API performs the
              authoritative validation.
            </p>
          </div>

          {file !== null && !isLocked ? (
            <p className="mt-3 truncate text-sm text-slate-600">
              Selected:{" "}
              <span className="font-medium text-slate-900">{file.name}</span>
            </p>
          ) : null}

          <button
            type="submit"
            disabled={isLocked}
            className="mt-5 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-teal-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
          >
            {submission.isPending
              ? "Submitting…"
              : accepted === null
                ? "Start classification"
                : "Submission accepted"}
          </button>
        </form>

        {localError !== null ? (
          <div role="alert" className="message-error mt-5">
            {localError}
          </div>
        ) : null}

        {requestError !== null ? (
          <div role="alert" className="message-error mt-5">
            <p>{problemGuidance(requestError.problem)}</p>
            <p className="mt-2 font-mono text-xs opacity-75">
              Correlation: {requestError.problem.correlationId}
            </p>
          </div>
        ) : null}

        {currentStatus !== undefined ? (
          <div
            className="mt-8 border-t border-slate-200 pt-7"
            aria-live="polite"
          >
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                  Processing state
                </p>
                <p className="mt-1 text-2xl font-semibold text-slate-950">
                  {statusLabel(currentStatus)}
                </p>
              </div>
              {!terminal && !statusQuery.isError ? (
                <span
                  className="processing-indicator"
                  aria-label="Polling for status"
                >
                  <span />
                  Live
                </span>
              ) : null}
            </div>

            <ol
              className="mt-6 grid grid-cols-4 gap-2"
              aria-label="Document progress"
            >
              {PROGRESS_STATES.map((state, index) => {
                const reached = index <= progressIndex(currentStatus);
                const active = state === currentStatus;
                return (
                  <li key={state} aria-current={active ? "step" : undefined}>
                    <span
                      className={`block h-1.5 rounded-full ${reached ? "bg-teal-600" : "bg-slate-200"}`}
                    />
                    <span
                      className={`mt-2 block text-[0.68rem] font-medium uppercase tracking-wide ${active ? "text-teal-800" : "text-slate-400"}`}
                    >
                      {state}
                    </span>
                  </li>
                );
              })}
            </ol>

            {statusQuery.data?.status === "completed" ? (
              <div className="result-card mt-7">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-teal-800">
                    Classification
                  </p>
                  <p className="mt-2 text-4xl font-semibold capitalize tracking-tight text-slate-950">
                    {statusQuery.data.classification}
                  </p>
                </div>
                <dl className="grid grid-cols-2 gap-4 border-t border-teal-200/70 pt-5 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
                  <div>
                    <dt className="text-xs text-slate-500">Confidence</dt>
                    <dd className="mt-1 font-mono text-lg font-semibold text-slate-900">
                      {(statusQuery.data.confidence * 100).toFixed(1)}%
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Model</dt>
                    <dd className="mt-1 break-all font-mono text-sm font-semibold text-slate-900">
                      {statusQuery.data.modelVersion}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}

            {statusQuery.data?.status === "failed" ? (
              <div role="alert" className="message-error mt-7">
                {terminalFailureGuidance(statusQuery.data.failureCode)}
              </div>
            ) : null}

            {statusQuery.isError ? (
              <button
                type="button"
                className="mt-5 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:border-teal-600 hover:text-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
                onClick={() => void statusQuery.refetch()}
              >
                Retry status
              </button>
            ) : null}

            {terminal || statusQuery.isError ? (
              <button
                type="button"
                className="mt-5 ml-3 rounded-lg px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
                onClick={reset}
              >
                Classify another PDF
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
