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
    "/api/v1/documents/{documentId}/source": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get an owned document's private PDF source */
        get: operations["getDocumentSource"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{documentId}/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get the current review representation */
        get: operations["getDocumentReview"];
        /** Commit one terminal approval or correction */
        put: operations["putDocumentReview"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{documentId}/audit-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get the owned document's sanitized audit history */
        get: operations["getDocumentAuditEvents"];
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
        ReviewDecisionRequest: {
            finalClassification: components["schemas"]["Classification"];
        };
        Review: components["schemas"]["UnreviewedReview"] | components["schemas"]["ApprovedReview"] | components["schemas"]["CorrectedReview"];
        UnreviewedReview: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "unreviewed";
            machineClassification: components["schemas"]["Classification"];
            machineConfidence: number;
            modelVersion: string;
            /** @constant */
            reviewVersion: 0;
        };
        TerminalReview: components["schemas"]["ApprovedReview"] | components["schemas"]["CorrectedReview"];
        ApprovedReview: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "approved";
            machineClassification: components["schemas"]["Classification"];
            machineConfidence: number;
            modelVersion: string;
            /** @constant */
            reviewVersion: 1;
            finalClassification: components["schemas"]["Classification"];
            /** Format: uuid */
            reviewerPrincipalId: string;
            /** Format: date-time */
            decidedAt: string;
        } & ({
            /** @constant */
            machineClassification: "invoice";
            /** @constant */
            finalClassification: "invoice";
        } | {
            /** @constant */
            machineClassification: "report";
            /** @constant */
            finalClassification: "report";
        });
        CorrectedReview: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            status: "corrected";
            machineClassification: components["schemas"]["Classification"];
            machineConfidence: number;
            modelVersion: string;
            /** @constant */
            reviewVersion: 1;
            finalClassification: components["schemas"]["Classification"];
            /** Format: uuid */
            reviewerPrincipalId: string;
            /** Format: date-time */
            decidedAt: string;
        } & ({
            /** @constant */
            machineClassification: "invoice";
            /** @constant */
            finalClassification: "report";
        } | {
            /** @constant */
            machineClassification: "report";
            /** @constant */
            finalClassification: "invoice";
        });
        AuditHistory: {
            /** Format: uuid */
            documentId: string;
            events: components["schemas"]["AuditEvent"][];
        };
        AuditEvent: {
            /** Format: uuid */
            eventId: string;
            /** @enum {string} */
            action: "document.submitted" | "processing.completed" | "processing.failed" | "review.approved" | "review.corrected";
            /** Format: date-time */
            occurredAt: string;
            /** Format: uuid */
            actorPrincipalId: string;
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            /** Format: uuid */
            reviewId?: string;
            /** Format: uuid */
            correlationId: string;
            /** @constant */
            detailsVersion: 1;
            details: Record<string, never>;
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
        AuthenticationRequiredProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 401;
            /** @constant */
            code: "AUTHENTICATION_REQUIRED";
        };
        InsufficientCapabilityProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 403;
            /** @constant */
            code: "INSUFFICIENT_CAPABILITY";
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
        SourceUnavailableProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 503;
            /** @constant */
            code: "SOURCE_UNAVAILABLE";
        };
        ReviewNotAvailableProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 409;
            /** @constant */
            code: "REVIEW_NOT_AVAILABLE";
        };
        IdempotencyConflictProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 409;
            /** @constant */
            code: "IDEMPOTENCY_CONFLICT";
        };
        PreconditionFailedProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 412;
            /** @constant */
            code: "PRECONDITION_FAILED";
        };
        PreconditionRequiredProblem: components["schemas"]["Problem"] & {
            /** @constant */
            status: 428;
            /** @constant */
            code: "PRECONDITION_REQUIRED";
        };
    };
    responses: {
        /** @description A missing or invalid bearer access token. */
        AuthenticationRequired: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                "WWW-Authenticate": components["headers"]["BearerChallenge"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["AuthenticationRequiredProblem"];
            };
        };
        /** @description The authenticated principal lacks the required capability. */
        InsufficientCapability: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["InsufficientCapabilityProblem"];
            };
        };
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
        /** @description Source storage or source integrity is temporarily unavailable. */
        SourceAccessUnavailable: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["SourceUnavailableProblem"] | components["schemas"]["DependencyUnavailableProblem"];
            };
        };
        /** @description The document has no completed machine result available for review. */
        ReviewNotAvailable: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["ReviewNotAvailableProblem"];
            };
        };
        /** @description The review is terminal or the idempotency key conflicts. */
        ReviewWriteConflict: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["ReviewNotAvailableProblem"] | components["schemas"]["IdempotencyConflictProblem"];
            };
        };
        /** @description The supplied review entity tag is stale or does not match. */
        PreconditionFailed: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["PreconditionFailedProblem"];
            };
        };
        /** @description The required review If-Match header is absent. */
        PreconditionRequired: {
            headers: {
                "X-Correlation-ID": components["headers"]["CorrelationId"];
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["PreconditionRequiredProblem"];
            };
        };
    };
    parameters: {
        /** @description Server-generated document identifier. */
        DocumentId: string;
        /** @description Optional caller-provided identifier used for traceability. */
        CorrelationId: string;
        /** @description Latest strong review entity tag; omission returns 428. */
        IfMatch: string;
        /** @description UUID scoped to the authenticated principal and review operation. */
        IdempotencyKey: string;
    };
    requestBodies: never;
    headers: {
        /** @description Correlation identifier assigned to this request flow. */
        CorrelationId: string;
        /** @description Sanitized OAuth bearer-token challenge. */
        BearerChallenge: string;
        /** @description Opaque strong entity tag for the returned review version. */
        ReviewEntityTag: string;
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
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
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
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
            404: components["responses"]["DocumentNotFound"];
            422: components["responses"]["InvalidRequest"];
            503: components["responses"]["DependencyUnavailable"];
        };
    };
    getDocumentSource: {
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
            /** @description The verified private PDF source. */
            200: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    /** @description Sanitized inline source filename. */
                    "Content-Disposition"?: "inline; filename=\"source.pdf\"";
                    /** @description Verified source size in bytes. */
                    "Content-Length"?: number;
                    /** @description Strong entity tag derived from the persisted SHA-256 digest. */
                    ETag?: string;
                    /** @description Disables content-type sniffing. */
                    "X-Content-Type-Options"?: "nosniff";
                    [name: string]: unknown;
                };
                content: {
                    "application/pdf": string;
                };
            };
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
            404: components["responses"]["DocumentNotFound"];
            422: components["responses"]["InvalidRequest"];
            503: components["responses"]["SourceAccessUnavailable"];
        };
    };
    getDocumentReview: {
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
            /** @description Current immutable machine evidence and human-review state. */
            200: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    ETag: components["headers"]["ReviewEntityTag"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Review"];
                };
            };
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
            404: components["responses"]["DocumentNotFound"];
            409: components["responses"]["ReviewNotAvailable"];
            422: components["responses"]["InvalidRequest"];
            503: components["responses"]["DependencyUnavailable"];
        };
    };
    putDocumentReview: {
        parameters: {
            query?: never;
            header: {
                /** @description Optional caller-provided identifier used for traceability. */
                "X-Correlation-ID"?: components["parameters"]["CorrelationId"];
                /** @description Latest strong review entity tag; omission returns 428. */
                "If-Match"?: components["parameters"]["IfMatch"];
                /** @description UUID scoped to the authenticated principal and review operation. */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description Server-generated document identifier. */
                documentId: components["parameters"]["DocumentId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewDecisionRequest"];
            };
        };
        responses: {
            /** @description The committed terminal decision or its identical replay. */
            200: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    ETag: components["headers"]["ReviewEntityTag"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TerminalReview"];
                };
            };
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
            404: components["responses"]["DocumentNotFound"];
            409: components["responses"]["ReviewWriteConflict"];
            412: components["responses"]["PreconditionFailed"];
            422: components["responses"]["InvalidRequest"];
            428: components["responses"]["PreconditionRequired"];
            503: components["responses"]["DependencyUnavailable"];
        };
    };
    getDocumentAuditEvents: {
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
            /** @description Deterministically ordered append-only product audit events. */
            200: {
                headers: {
                    "X-Correlation-ID": components["headers"]["CorrelationId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditHistory"];
                };
            };
            401: components["responses"]["AuthenticationRequired"];
            403: components["responses"]["InsufficientCapability"];
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
