import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createDocument,
  DocumentRequestError,
  getDocument,
} from "@/lib/browser-api";
import { DocumentWorkflow } from "@/components/document-workflow";
import { MAX_PDF_BYTES } from "@/lib/file-validation";
import {
  acceptedDocument,
  canonicalProblem,
  completedStatus,
  failedStatus,
  processingStatus,
  queuedStatus,
} from "@/test/fixtures";

vi.mock("@/lib/browser-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/browser-api")>();
  return {
    ...actual,
    createDocument: vi.fn(),
    getDocument: vi.fn(),
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
      <DocumentWorkflow />
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
  vi.mocked(createDocument).mockReset();
  vi.mocked(getDocument).mockReset();
});

afterEach(cleanup);

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

    expect(await screen.findByText("invoice")).toBeInTheDocument();
    expect(screen.getByText("98.7%")).toBeInTheDocument();
    expect(screen.getByText("document-type-v1")).toBeInTheDocument();
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
    expect(await screen.findByText("invoice")).toBeInTheDocument();
    await waitFor(() => expect(getDocument).toHaveBeenCalledTimes(2));
  });
});
