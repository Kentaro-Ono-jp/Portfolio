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
        ProcessingStatus: "accepted" | "queued" | "processing" | "completed" | "failed";
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
        DocumentStatus: {
            /** Format: uuid */
            documentId: string;
            /** Format: uuid */
            jobId: string;
            status: components["schemas"]["ProcessingStatus"];
            classification?: components["schemas"]["Classification"] | null;
            confidence?: number | null;
            modelVersion?: string | null;
            failureCode?: string | null;
            /** Format: date-time */
            createdAt: string;
            /** Format: date-time */
            startedAt?: string | null;
            /** Format: date-time */
            completedAt?: string | null;
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
    };
    responses: {
        /** @description The submitted file is not a supported PDF. */
        InvalidDocument: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["Problem"];
            };
        };
        /** @description The submitted file exceeds the 5 MiB limit. */
        DocumentTooLarge: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["Problem"];
            };
        };
        /** @description The request does not contain an application/pdf file. */
        UnsupportedMediaType: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["Problem"];
            };
        };
        /** @description No document exists for the supplied identifier. */
        DocumentNotFound: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/problem+json": components["schemas"]["Problem"];
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
            /** @description At least one required dependency is unavailable. */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/problem+json": components["schemas"]["Problem"];
                };
            };
        };
    };
}
