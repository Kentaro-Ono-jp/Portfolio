"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";

import {
  createDocument,
  DocumentRequestError,
  getDocumentAuditHistory,
  getDocumentReview,
  getDocument,
  problemGuidance,
  submitDocumentReview,
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

type Classification = "invoice" | "report";

interface PendingDecision {
  finalClassification: Classification;
  idempotencyKey: string;
}

function statusLabel(status: string): string {
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

export function DocumentWorkflow({ csrfToken }: { csrfToken: string }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<DocumentAccepted | null>(null);
  const [selectedFinalClassification, setSelectedFinalClassification] =
    useState<Classification | null>(null);
  const [pendingDecision, setPendingDecision] =
    useState<PendingDecision | null>(null);

  const submission = useMutation({
    mutationFn: (selectedFile: File) => createDocument(selectedFile, csrfToken),
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

  const completedDocument: Extract<
    DocumentStatus,
    { status: "completed" }
  > | null = statusQuery.data?.status === "completed" ? statusQuery.data : null;
  const reviewQuery = useQuery({
    queryKey: ["document-review", accepted?.documentId],
    queryFn: () => getDocumentReview(accepted!.documentId),
    enabled: completedDocument !== null,
  });
  const auditQuery = useQuery({
    queryKey: ["document-audit", accepted?.documentId],
    queryFn: () => getDocumentAuditHistory(accepted!.documentId),
    enabled: completedDocument !== null,
  });

  const reviewMutation = useMutation({
    mutationFn: (decision: PendingDecision) =>
      submitDocumentReview(
        accepted!.documentId,
        decision.finalClassification,
        reviewQuery.data!.entityTag,
        decision.idempotencyKey,
        csrfToken,
      ),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ["document-review", accepted?.documentId],
        result,
      );
      void queryClient.invalidateQueries({
        queryKey: ["document-audit", accepted?.documentId],
      });
      setPendingDecision(null);
    },
  });

  const currentStatus = statusQuery.data?.status ?? accepted?.status;
  const terminal =
    statusQuery.data !== undefined && isTerminalStatus(statusQuery.data);
  const requestError =
    submission.error instanceof DocumentRequestError
      ? submission.error
      : statusQuery.error instanceof DocumentRequestError
        ? statusQuery.error
        : reviewQuery.error instanceof DocumentRequestError
          ? reviewQuery.error
          : auditQuery.error instanceof DocumentRequestError
            ? auditQuery.error
            : reviewMutation.error instanceof DocumentRequestError
              ? reviewMutation.error
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
      queryClient.removeQueries({
        queryKey: ["document-review", accepted.documentId],
      });
      queryClient.removeQueries({
        queryKey: ["document-audit", accepted.documentId],
      });
    }
    submission.reset();
    reviewMutation.reset();
    setAccepted(null);
    setFile(null);
    setLocalError(null);
    setSelectedFinalClassification(null);
    setPendingDecision(null);
    if (inputRef.current !== null) {
      inputRef.current.value = "";
      queueMicrotask(() => inputRef.current?.focus());
    }
  }

  function commitReview(): void {
    const review = reviewQuery.data?.review;
    if (review === undefined || review.status !== "unreviewed") {
      return;
    }
    const finalClassification =
      selectedFinalClassification ?? review.machineClassification;
    const decision =
      pendingDecision?.finalClassification === finalClassification
        ? pendingDecision
        : { finalClassification, idempotencyKey: crypto.randomUUID() };
    setPendingDecision(decision);
    reviewMutation.mutate(decision);
  }

  const review = reviewQuery.data?.review;
  const selectedClassification =
    selectedFinalClassification ?? review?.machineClassification;
  const reviewIsTerminal =
    review?.status === "approved" || review?.status === "corrected";

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

            {accepted !== null ? (
              <a
                className="mt-5 inline-flex rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 hover:border-teal-600 hover:text-teal-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-700"
                href={`/api/documents/${encodeURIComponent(accepted.documentId)}/source`}
                target="_blank"
                rel="noreferrer"
              >
                View private source PDF
              </a>
            ) : null}

            {completedDocument !== null ? (
              <div className="result-card mt-7" aria-label="Machine result">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-teal-800">
                    Machine classification
                  </p>
                  <p className="mt-2 text-4xl font-semibold capitalize tracking-tight text-slate-950">
                    {completedDocument.classification}
                  </p>
                </div>
                <dl className="grid grid-cols-2 gap-4 border-t border-teal-200/70 pt-5 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
                  <div>
                    <dt className="text-xs text-slate-500">Confidence</dt>
                    <dd className="mt-1 font-mono text-lg font-semibold text-slate-900">
                      {(completedDocument.confidence * 100).toFixed(1)}%
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-slate-500">Model</dt>
                    <dd className="mt-1 break-all font-mono text-sm font-semibold text-slate-900">
                      {completedDocument.modelVersion}
                    </dd>
                  </div>
                </dl>
              </div>
            ) : null}

            {completedDocument !== null ? (
              <section
                className="mt-7 rounded-2xl border border-slate-200 bg-white p-5"
                aria-labelledby="review-title"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.16em] text-slate-500">
                      Human decision
                    </p>
                    <h3
                      id="review-title"
                      className="mt-1 text-xl font-semibold text-slate-950"
                    >
                      Review classification
                    </h3>
                  </div>
                  <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-xs text-slate-700">
                    Review v{review?.reviewVersion ?? 0}
                  </span>
                </div>

                {reviewQuery.isPending ? (
                  <p className="mt-4 text-sm text-slate-600">
                    Loading review state…
                  </p>
                ) : null}

                {review?.status === "unreviewed" ? (
                  <div className="mt-5">
                    <fieldset disabled={reviewMutation.isPending}>
                      <legend className="text-sm font-semibold text-slate-900">
                        Final classification
                      </legend>
                      <div className="mt-3 grid grid-cols-2 gap-3">
                        {(["invoice", "report"] as const).map(
                          (classification) => (
                            <label
                              key={classification}
                              className={`cursor-pointer rounded-xl border p-4 text-sm font-semibold capitalize transition ${selectedClassification === classification ? "border-teal-600 bg-teal-50 text-teal-900" : "border-slate-200 text-slate-700 hover:border-slate-400"}`}
                            >
                              <input
                                className="mr-2 accent-teal-700"
                                type="radio"
                                name="final-classification"
                                value={classification}
                                checked={
                                  selectedClassification === classification
                                }
                                onChange={() => {
                                  setSelectedFinalClassification(
                                    classification,
                                  );
                                  setPendingDecision(null);
                                  reviewMutation.reset();
                                }}
                              />
                              {classification}
                            </label>
                          ),
                        )}
                      </div>
                    </fieldset>
                    <button
                      type="button"
                      disabled={
                        reviewMutation.isPending ||
                        selectedClassification === undefined
                      }
                      className="mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-teal-800 disabled:bg-slate-300"
                      onClick={commitReview}
                    >
                      {reviewMutation.isPending
                        ? "Committing immutable decision…"
                        : selectedClassification ===
                            review.machineClassification
                          ? `Approve ${review.machineClassification} classification`
                          : `Correct classification to ${selectedClassification}`}
                    </button>
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      One terminal decision is committed with an entity-tag
                      precondition and an idempotency key. It cannot be edited.
                    </p>
                  </div>
                ) : null}

                {review !== undefined && review.status !== "unreviewed" ? (
                  <div className="mt-5">
                    <p className="text-lg font-semibold capitalize text-slate-950">
                      {statusLabel(review.status)}
                    </p>
                    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                      <div>
                        <dt className="text-slate-500">Machine result</dt>
                        <dd className="mt-1 font-semibold capitalize text-slate-900">
                          {review.machineClassification}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-slate-500">Final decision</dt>
                        <dd className="mt-1 font-semibold capitalize text-slate-900">
                          {review.finalClassification}
                        </dd>
                      </div>
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">Reviewer principal</dt>
                        <dd className="mt-1 break-all font-mono text-xs text-slate-900">
                          {review.reviewerPrincipalId}
                        </dd>
                      </div>
                      <div className="sm:col-span-2">
                        <dt className="text-slate-500">Decided at</dt>
                        <dd className="mt-1 font-mono text-xs text-slate-900">
                          <time dateTime={review.decidedAt}>
                            {review.decidedAt}
                          </time>
                        </dd>
                      </div>
                    </dl>
                  </div>
                ) : null}

                {reviewQuery.isError ? (
                  <button
                    type="button"
                    className="mt-4 rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800"
                    onClick={() => void reviewQuery.refetch()}
                  >
                    Retry review state
                  </button>
                ) : null}
              </section>
            ) : null}

            {completedDocument !== null ? (
              <section
                className="mt-7 rounded-2xl bg-slate-950 p-5 text-slate-100"
                aria-labelledby="audit-title"
              >
                <p className="text-xs uppercase tracking-[0.16em] text-teal-300">
                  API-owned evidence
                </p>
                <h3 id="audit-title" className="mt-1 text-xl font-semibold">
                  Audit history
                </h3>
                {auditQuery.isPending ? (
                  <p className="mt-4 text-sm text-slate-300">
                    Loading ordered events…
                  </p>
                ) : null}
                {auditQuery.data !== undefined ? (
                  <ol className="mt-5 space-y-3">
                    {auditQuery.data.events.map((event, index) => (
                      <li
                        key={event.eventId}
                        className="grid grid-cols-[2rem_1fr] gap-3 border-t border-slate-700 pt-3"
                      >
                        <span className="font-mono text-xs text-teal-300">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <div>
                          <p className="font-mono text-sm font-semibold">
                            {event.action}
                          </p>
                          <p className="mt-1 font-mono text-[0.68rem] text-slate-400">
                            {event.occurredAt}
                          </p>
                          <dl className="mt-2 grid gap-1 font-mono text-[0.65rem] text-slate-400">
                            <div>
                              <dt className="inline text-slate-500">Actor </dt>
                              <dd className="inline break-all">
                                {event.actorPrincipalId}
                              </dd>
                            </div>
                            <div>
                              <dt className="inline text-slate-500">
                                Correlation{" "}
                              </dt>
                              <dd className="inline break-all">
                                {event.correlationId}
                              </dd>
                            </div>
                          </dl>
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : null}
                {auditQuery.isError ? (
                  <button
                    type="button"
                    className="mt-4 rounded-lg border border-slate-600 px-4 py-2 text-sm font-semibold"
                    onClick={() => void auditQuery.refetch()}
                  >
                    Retry audit history
                  </button>
                ) : null}
              </section>
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

            {statusQuery.data?.status === "failed" ||
            reviewIsTerminal ||
            statusQuery.isError ? (
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
