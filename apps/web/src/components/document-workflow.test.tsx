import {
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDocument,
  DocumentRequestError,
  getDocumentAuditHistory,
  getDocumentReview,
  getDocument,
  submitDocumentReview,
} from "@/lib/browser-api";
import { DocumentWorkflow } from "@/components/document-workflow";
import { MAX_PDF_BYTES } from "@/lib/file-validation";
import {
  acceptedDocument,
  approvedReview,
  auditHistory,
  canonicalProblem,
  completedStatus,
  correctedReview,
  failedStatus,
  processingStatus,
  queuedStatus,
  REVIEW_ENTITY_TAG,
  REVIEWER_PRINCIPAL_ID,
  unreviewedReview,
} from "@/test/fixtures";

vi.mock("@/lib/browser-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/browser-api")>();
  return {
    ...actual,
    createDocument: vi.fn(),
    getDocumentAuditHistory: vi.fn(),
    getDocumentReview: vi.fn(),
    getDocument: vi.fn(),
    submitDocumentReview: vi.fn(),
  };
});

function renderWorkflow() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <DocumentWorkflow csrfToken="csrf-proof" />
    </QueryClientProvider>,
  );
}

function pdf(name = "invoice.pdf") {
  return new File(["%PDF-1.7"], name, { type: "application/pdf" });
}

async function submit(file = pdf()) {
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText("Source PDF"), file);
  await user.click(
    screen.getByRole("button", { name: "Start classification" }),
  );
  return user;
}

beforeEach(() => {
  onlineManager.setOnline(true);
  vi.mocked(createDocument).mockReset();
  vi.mocked(getDocumentAuditHistory).mockReset();
  vi.mocked(getDocumentReview).mockReset();
  vi.mocked(getDocument).mockReset();
  vi.mocked(submitDocumentReview).mockReset();
  vi.mocked(getDocumentReview).mockResolvedValue({
    review: approvedReview,
    entityTag: REVIEW_ENTITY_TAG,
  });
  vi.mocked(getDocumentAuditHistory).mockResolvedValue(auditHistory);
  vi.mocked(submitDocumentReview).mockResolvedValue({
    review: approvedReview,
    entityTag: REVIEW_ENTITY_TAG,
  });
});

afterEach(() => {
  cleanup();
  onlineManager.setOnline(true);
});

describe("DocumentWorkflow", () => {
  it("validates missing, wrong-type, and oversized files before requesting", async () => {
    renderWorkflow();
    const user = userEvent.setup({ applyAccept: false });
    await user.click(
      screen.getByRole("button", { name: "Start classification" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Choose one PDF");

    await user.upload(
      screen.getByLabelText("Source PDF"),
      new File(["text"], "notes.txt", { type: "text/plain" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Start classification" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("application/pdf");

    await user.upload(
      screen.getByLabelText("Source PDF"),
      new File([new Uint8Array(MAX_PDF_BYTES + 1)], "large.pdf", {
        type: "application/pdf",
      }),
    );
    await user.click(
      screen.getByRole("button", { name: "Start classification" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent("5 MiB");
    expect(createDocument).not.toHaveBeenCalled();
  });

  it("submits once, locks the form, and shows accepted state", async () => {
    let resolveStatus!: (value: typeof queuedStatus) => void;
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument).mockReturnValue(
      new Promise((resolve) => {
        resolveStatus = resolve;
      }),
    );
    renderWorkflow();
    const user = await submit();

    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Submission accepted" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(createDocument).toHaveBeenCalledTimes(1);
    resolveStatus(queuedStatus);
    expect(await screen.findByText("Queued")).toBeInTheDocument();
  });

  it.each([
    ["queued", queuedStatus, "Queued"],
    ["processing", processingStatus, "Processing"],
  ])("renders the %s progress state", async (_name, status, label) => {
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument).mockResolvedValue(status);
    renderWorkflow();
    await submit();
    expect(await screen.findByText(label)).toBeInTheDocument();
    expect(screen.getByLabelText("Polling for status")).toBeInTheDocument();
  });

  it("renders the completed result and resets for another document", async () => {
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument).mockResolvedValue(completedStatus);
    renderWorkflow();
    const user = await submit();

    expect(
      await within(screen.getByLabelText("Machine result")).findByText(
        "invoice",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("98.7%")).toBeInTheDocument();
    expect(screen.getByText("document-type-v1")).toBeInTheDocument();
    expect(await screen.findByText("Human decision")).toBeInTheDocument();
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("review.approved")).toBeInTheDocument();
    expect(screen.getAllByText(REVIEWER_PRINCIPAL_ID).length).toBeGreaterThan(
      1,
    );
    expect(
      screen.queryByLabelText("Polling for status"),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Classify another PDF" }),
    );
    expect(
      screen.getByRole("button", { name: "Start classification" }),
    ).toBeEnabled();
    expect(screen.queryByText("invoice")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Source PDF")).toHaveFocus();
  });

  it("commits a correction and reuses its idempotency key after uncertainty", async () => {
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument).mockResolvedValue(completedStatus);
    vi.mocked(getDocumentReview).mockResolvedValue({
      review: unreviewedReview,
      entityTag: REVIEW_ENTITY_TAG,
    });
    vi.mocked(submitDocumentReview)
      .mockRejectedValueOnce(new DocumentRequestError(canonicalProblem))
      .mockResolvedValueOnce({
        review: correctedReview,
        entityTag: `"${"b".repeat(64)}"`,
      });
    renderWorkflow();
    const user = await submit();

    await user.click(await screen.findByRole("radio", { name: "report" }));
    await user.click(
      screen.getByRole("button", {
        name: "Correct classification to report",
      }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "application/pdf",
    );
    await user.click(
      screen.getByRole("button", {
        name: "Correct classification to report",
      }),
    );
    expect(await screen.findByText("Corrected")).toBeInTheDocument();
    expect(screen.getByText("Final decision")).toBeInTheDocument();
    expect(submitDocumentReview).toHaveBeenCalledTimes(2);
    const firstKey = vi.mocked(submitDocumentReview).mock.calls[0]![3];
    expect(vi.mocked(submitDocumentReview).mock.calls[1]![3]).toBe(firstKey);
    expect(vi.mocked(submitDocumentReview).mock.calls[0]!.slice(0, 3)).toEqual([
      acceptedDocument.documentId,
      "report",
      REVIEW_ENTITY_TAG,
    ]);
  });

  it("renders a sanitized failed terminal result", async () => {
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument).mockResolvedValue(failedStatus);
    renderWorkflow();
    await submit();

    expect(await screen.findByText("Failed")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("integrity check");
    expect(
      screen.queryByLabelText("Polling for status"),
    ).not.toBeInTheDocument();
  });

  it.each([
    ["completed", completedStatus, "invoice"],
    ["failed", failedStatus, "Failed"],
  ])(
    "does not refetch a %s terminal result after reconnecting",
    async (_name, status, label) => {
      vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
      vi.mocked(getDocument)
        .mockResolvedValueOnce(status)
        .mockResolvedValue(queuedStatus);
      renderWorkflow();
      await submit();

      if (label === "invoice") {
        expect(
          await within(screen.getByLabelText("Machine result")).findByText(
            label,
          ),
        ).toBeInTheDocument();
      } else {
        expect(await screen.findByText(label)).toBeInTheDocument();
      }
      expect(getDocument).toHaveBeenCalledTimes(1);

      await act(async () => {
        onlineManager.setOnline(false);
      });
      await act(async () => {
        onlineManager.setOnline(true);
      });

      expect(getDocument).toHaveBeenCalledTimes(1);
      if (label === "invoice") {
        expect(
          within(screen.getByLabelText("Machine result")).getByText(label),
        ).toBeInTheDocument();
      } else {
        expect(screen.getByText(label)).toBeInTheDocument();
      }
    },
  );

  it("shows submission problems without leaking raw errors", async () => {
    vi.mocked(createDocument).mockRejectedValue(
      new DocumentRequestError(canonicalProblem),
    );
    renderWorkflow();
    await submit();

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("application/pdf");
    expect(alert).toHaveTextContent(canonicalProblem.correlationId);
  });

  it("stops after a polling error and supports explicit retry", async () => {
    vi.mocked(createDocument).mockResolvedValue(acceptedDocument);
    vi.mocked(getDocument)
      .mockRejectedValueOnce(new DocumentRequestError(canonicalProblem))
      .mockResolvedValueOnce(completedStatus);
    renderWorkflow();
    const user = await submit();

    expect(
      await screen.findByRole("button", { name: "Retry status" }),
    ).toBeVisible();
    expect(
      screen.queryByLabelText("Polling for status"),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry status" }));
    expect(
      await within(screen.getByLabelText("Machine result")).findByText(
        "invoice",
      ),
    ).toBeInTheDocument();
    await waitFor(() => expect(getDocument).toHaveBeenCalledTimes(2));
  });
});
