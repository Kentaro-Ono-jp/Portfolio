/**
 * Generated from packages/contracts/openapi/openapi.yaml.
 * Regenerate with: pnpm contracts:generate
 * Do not make direct changes to this file.
 */

export interface paths {
    "/api/v1/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit a PDF for classification */
        post: operations["createDocument"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{documentId}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get document processing status */
        get: operations["getDocument"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Check whether the API process is running */
        get: operations["getHealth"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Check whether the API can accept useful work */
        get: operations["getReadiness"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** @enum {string} */
        Classification: "invoice" | "report";
        DocumentAccepted: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /** @constant */
            status: "accepted";
        };
        DocumentStatus: components["schemas"]["AcceptedDocumentStatus"] | components["schemas"]["QueuedDocumentStatus"] | components["schemas"]["ProcessingDocumentStatus"] | components["schemas"]["CompletedDocumentStatus"] | components["schemas"]["FailedDocumentStatus"];
        AcceptedDocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "accepted";
            /** Format: date-time */
            createdAt: string;
        };
        QueuedDocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "queued";
            /** Format: date-time */
            createdAt: string;
        };
        ProcessingDocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "processing";
            /** Format: date-time */
            createdAt: string;
            /** Format: date-time */
            startedAt: string;
        };
        CompletedDocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "completed";
            classification: components["schemas"]["Classification"];
            confidence: number;
            modelVersion: string;
            /** Format: date-time */
            createdAt: string;
            /** Format: date-time */
            startedAt: string;
            /** Format: date-time */
            completedAt: string;
        };
        FailedDocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "failed";
            failureCode: string;
            /** Format: date-time */
            createdAt: string;
            /** Format: date-time */
            startedAt?: string;
            /** Format: date-time */
            completedAt: string;
        };
        Health: {
            /** @constant */
            status: "ok";
        };
        Problem: {
            /** Format: uri-reference */
            type: string;
            title: string;
            status: number;
            detail?: string;
            code: string;
            /** Format: uuid */
            correlationId: string;
        };
        InvalidRequestProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 422;
            /** @constant */
            code: "INVALID_REQUEST";
        };
        InvalidDocumentProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 400;
            /** @constant */
            code: "INVALID_DOCUMENT";
        };
        DocumentTooLargeProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 413;
            /** @constant */
            code: "DOCUMENT_TOO_LARGE";
        };
        UnsupportedMediaTypeProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 415;
            /** @constant */
            code: "UNSUPPORTED_MEDIA_TYPE";
        };
        DocumentNotFoundProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 404;
            /** @constant */
            code: "DOCUMENT_NOT_FOUND";
        };
        DependencyUnavailableProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 503;
            /** @constant */
            code: "DEPENDENCY_UNAVAILABLE";
        };
    };
    responses: {
        /** @description A path, header, or request-body value violates the API contract. */
        InvalidRequest: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["InvalidRequestProblem"];
            };
        };
        /** @description The submitted file is not a supported PDF. */
        InvalidDocument: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["InvalidDocumentProblem"];
            };
        };
        /** @description The submitted file exceeds the 5 MiB limit. */
        DocumentTooLarge: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["DocumentTooLargeProblem"];
            };
        };
        /** @description The request does not contain an application/pdf file. */
        UnsupportedMediaType: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["UnsupportedMediaTypeProblem"];
            };
        };
        /** @description No document exists for the supplied identifier. */
        DocumentNotFound: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["DocumentNotFoundProblem"];
            };
        };
        /** @description At least one required dependency is unavailable. */
        DependencyUnavailable: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["DependencyUnavailableProblem"];
            };
        };
    };
    parameters: {
        /** @description Server-generated document identifier. */
        DocumentId: string;
        /** @description Optional caller-provided identifier used for traceability. */
        CorrelationId: string;
    };
    requestBodies: never;
    headers: {
        /** @description Correlation identifier assigned to this request flow. */
        CorrelationId: string;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    createDocument: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional caller-provided identifier used for traceability. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: string;
                };
            };
        };
        responses: {
            /** @description The document and processing job were accepted. */
            202: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentAccepted"];
                };
            };
            400: components["responses"]["InvalidDocument"];
            413: components["responses"]["DocumentTooLarge"];
            415: components["responses"]["UnsupportedMediaType"];
            422: components["responses"]["InvalidRequest"];
            503: components["responses"]["DependencyUnavailable"];
        };
    };
    getDocument: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional caller-provided identifier used for traceability. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
            };
            path: {
                /** @description Server-generated document identifier. */
                documentId: components["parameters"]["DocumentId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Current document and processing state. */
            200: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentStatus"];
                };
            };
            404: components["responses"]["DocumentNotFound"];
            422: components["responses"]["InvalidRequest"];
            503: components["responses"]["DependencyUnavailable"];
        };
    };
    getHealth: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description The process is running. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    getReadiness: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Required runtime dependencies are reachable. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
            503: components["responses"]["DependencyUnavailable"];
        };
    };
}
