from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Header, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from reactorfront_api.authentication import (
    Capability,
    RequestAuthorizer,
    build_request_authorizer,
)
from reactorfront_api.domain import (
    PrincipalRecord,
    ProblemCode,
    ProcessingStatus,
    PublicProblem,
    review_entity_tag,
)
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.persistence import SqlAlchemySubmissionRepository, create_database_engine
from reactorfront_api.rabbitmq import PikaOutboxPublisher
from reactorfront_api.request_limits import (
    MULTIPART_ENVELOPE_BYTES,
    UploadRequestBodyLimitMiddleware,
)
from reactorfront_api.schemas import (
    AuditHistoryResponse,
    DocumentAcceptedResponse,
    DocumentStatusResponse,
    HealthResponse,
    ProblemResponse,
    ReviewDecisionRequest,
    ReviewResponse,
    TerminalReviewResponse,
    serialize_audit_history,
    serialize_document_status,
    serialize_review,
    serialize_terminal_review,
)
from reactorfront_api.service import MAX_DOCUMENT_BYTES, DocumentService
from reactorfront_api.settings import Settings, get_settings
from reactorfront_api.storage import S3ObjectStorage

CORRELATION_HEADER = "X-Correlation-ID"
DOCUMENT_UPLOAD_PATH = "/api/v1/documents"
PdfUpload = Annotated[UploadFile, File()]
CorrelationIdHeader = Annotated[UUID | None, Header(alias=CORRELATION_HEADER)]
IfMatchHeader = Annotated[
    str | None,
    Header(alias="If-Match", pattern=r'^"[a-f0-9]{64}"$'),
]
IdempotencyKeyHeader = Annotated[UUID, Header(alias="Idempotency-Key")]
DOCUMENT_PRINCIPAL_STATE = "document_principal"
DOCUMENT_CORRELATION_STATE = "document_correlation_id"


def build_document_service(settings: Settings) -> DocumentService:
    repository = SqlAlchemySubmissionRepository(
        engine=create_database_engine(settings.database_url)
    )
    object_storage = S3ObjectStorage.create(
        endpoint_url=settings.s3_endpoint_url,
        access_key_id=settings.s3_access_key_id,
        secret_access_key=settings.s3_secret_access_key.get_secret_value(),
        bucket=settings.s3_bucket,
        region=settings.s3_region,
    )
    event_validator = JsonSchemaEventValidator(contract_directory=settings.event_contract_directory)
    broker_readiness = PikaOutboxPublisher(
        broker_url=settings.rabbitmq_url.get_secret_value(),
        timeout_seconds=settings.rabbitmq_timeout_seconds,
    )
    return DocumentService(
        repository=repository,
        object_storage=object_storage,
        event_validator=event_validator,
        broker_readiness=broker_readiness,
    )


def public_problem_response(problem: PublicProblem) -> JSONResponse:
    body = ProblemResponse(
        type=problem.type_uri,
        title=problem.title,
        status=problem.status,
        detail=problem.detail,
        code=problem.code.value,
        correlation_id=problem.correlation_id,
    )
    return JSONResponse(
        status_code=problem.status,
        content=jsonable_encoder(body, by_alias=True),
        media_type="application/problem+json",
        headers={
            **problem.response_headers,
            CORRELATION_HEADER: str(problem.correlation_id),
        },
    )


def document_too_large_response(correlation_id: UUID) -> JSONResponse:
    return public_problem_response(
        PublicProblem(
            status=413,
            code=ProblemCode.DOCUMENT_TOO_LARGE,
            title="Document too large",
            detail="The uploaded file exceeds the 5 MiB limit.",
            correlation_id=correlation_id,
        )
    )


def request_correlation_id(request: Request) -> UUID:
    candidate = request.headers.get(CORRELATION_HEADER)
    if candidate is not None:
        try:
            return UUID(candidate)
        except ValueError:
            pass
    return uuid4()


def document_capability(method: str, path: str) -> Capability | None:
    normalized_path = path[:-1] if path.endswith("/") else path
    if method == "POST" and normalized_path == DOCUMENT_UPLOAD_PATH:
        return Capability.DOCUMENTS_SUBMIT
    segments = normalized_path.split("/")
    if segments[:4] != ["", "api", "v1", "documents"]:
        return None
    if method == "PUT" and len(segments) == 6 and segments[4] and segments[5] == "review":
        return Capability.REVIEWS_WRITE
    if method != "GET":
        return None
    if len(segments) == 5 and segments[4]:
        return Capability.DOCUMENTS_READ
    if len(segments) == 6 and segments[4] and segments[5] in {"source", "review"}:
        return Capability.DOCUMENTS_READ
    if len(segments) == 6 and segments[4] and segments[5] == "audit-events":
        return Capability.AUDIT_READ
    return None


def authorized_document_context(request: Request) -> tuple[PrincipalRecord, UUID]:
    principal = cast(
        PrincipalRecord,
        getattr(request.state, DOCUMENT_PRINCIPAL_STATE),
    )
    correlation_id = cast(
        UUID,
        getattr(request.state, DOCUMENT_CORRELATION_STATE),
    )
    return principal, correlation_id


def create_app(
    *,
    service: DocumentService | None = None,
    authorizer: RequestAuthorizer | None = None,
) -> FastAPI:
    owns_service = service is None
    owns_authorizer = authorizer is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()
        app.state.document_service = service or build_document_service(settings)
        app.state.request_authorizer = authorizer or build_request_authorizer(settings)
        try:
            yield
        finally:
            if owns_service:
                get_document_service(app).close()
            if owns_authorizer:
                get_request_authorizer(app).close()

    app = FastAPI(
        title="ReactorFront Document Intelligence API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        UploadRequestBodyLimitMiddleware,
        path=DOCUMENT_UPLOAD_PATH,
        max_body_bytes=MAX_DOCUMENT_BYTES + MULTIPART_ENVELOPE_BYTES,
        response_factory=document_too_large_response,
    )

    @app.middleware("http")
    async def authorize_document_operation(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        capability = document_capability(request.method, request.url.path)
        if capability is None:
            return await call_next(request)
        correlation_id = request_correlation_id(request)
        try:
            principal = get_request_authorizer(app).authorize(
                authorization_header=request.headers.get("Authorization"),
                capability=capability,
                correlation_id=correlation_id,
            )
        except PublicProblem as problem:
            return public_problem_response(problem)
        setattr(request.state, DOCUMENT_PRINCIPAL_STATE, principal)
        setattr(request.state, DOCUMENT_CORRELATION_STATE, correlation_id)
        return await call_next(request)

    @app.exception_handler(PublicProblem)
    async def handle_public_problem(_request: Request, problem: PublicProblem) -> JSONResponse:
        return public_problem_response(problem)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return public_problem_response(
            PublicProblem(
                status=422,
                code=ProblemCode.INVALID_REQUEST,
                title="Invalid request",
                detail="The request does not satisfy the API contract.",
                correlation_id=request_correlation_id(request),
            )
        )

    @app.post(
        DOCUMENT_UPLOAD_PATH,
        response_model=DocumentAcceptedResponse,
        status_code=status.HTTP_202_ACCEPTED,
        responses={
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            400: {"model": ProblemResponse},
            413: {"model": ProblemResponse},
            415: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def create_document(
        request: Request,
        response: Response,
        file: PdfUpload,
        correlation_id: CorrelationIdHeader = None,
    ) -> DocumentAcceptedResponse:
        principal, request_correlation_id = authorized_document_context(request)
        result = get_document_service(app).submit(
            stream=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
            correlation_id=request_correlation_id,
            principal_id=principal.principal_id,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        return DocumentAcceptedResponse(
            document_id=result.document_id,
            job_id=result.job_id,
            status=ProcessingStatus.ACCEPTED,
        )

    @app.get(
        "/api/v1/documents/{document_id}",
        response_model=DocumentStatusResponse,
        response_model_exclude_none=True,
        responses={
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            404: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def get_document(
        request: Request,
        document_id: UUID,
        response: Response,
        correlation_id: CorrelationIdHeader = None,
    ) -> DocumentStatusResponse:
        principal, request_correlation_id = authorized_document_context(request)
        result = get_document_service(app).get_status(
            document_id=document_id,
            principal_id=principal.principal_id,
            correlation_id=request_correlation_id,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        return serialize_document_status(result)

    @app.get(
        "/api/v1/documents/{document_id}/source",
        response_class=Response,
        responses={
            200: {
                "content": {"application/pdf": {}},
                "description": "The authorized private PDF source.",
            },
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            404: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def get_document_source(
        request: Request,
        document_id: UUID,
        correlation_id: CorrelationIdHeader = None,
    ) -> Response:
        principal, request_correlation_id = authorized_document_context(request)
        source = get_document_service(app).get_source(
            document_id=document_id,
            principal_id=principal.principal_id,
            correlation_id=request_correlation_id,
        )
        return Response(
            content=source.content,
            status_code=status.HTTP_200_OK,
            media_type=source.content_type,
            headers={
                CORRELATION_HEADER: str(request_correlation_id),
                "Content-Disposition": 'inline; filename="source.pdf"',
                "Content-Length": str(source.size_bytes),
                "ETag": f'"{source.sha256}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get(
        "/api/v1/documents/{document_id}/review",
        response_model=ReviewResponse,
        response_model_exclude_none=True,
        responses={
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            404: {"model": ProblemResponse},
            409: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def get_document_review(
        request: Request,
        document_id: UUID,
        response: Response,
        correlation_id: CorrelationIdHeader = None,
    ) -> ReviewResponse:
        principal, request_correlation_id = authorized_document_context(request)
        record = get_document_service(app).get_review(
            document_id=document_id,
            principal_id=principal.principal_id,
            correlation_id=request_correlation_id,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        response.headers["ETag"] = review_entity_tag(record)
        return serialize_review(record)

    @app.put(
        "/api/v1/documents/{document_id}/review",
        response_model=TerminalReviewResponse,
        response_model_exclude_none=True,
        responses={
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            404: {"model": ProblemResponse},
            409: {"model": ProblemResponse},
            412: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            428: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def put_document_review(
        request: Request,
        document_id: UUID,
        decision: ReviewDecisionRequest,
        response: Response,
        idempotency_key: IdempotencyKeyHeader,
        if_match: IfMatchHeader = None,
        correlation_id: CorrelationIdHeader = None,
    ) -> TerminalReviewResponse:
        principal, request_correlation_id = authorized_document_context(request)
        record = get_document_service(app).submit_review(
            document_id=document_id,
            principal_id=principal.principal_id,
            correlation_id=request_correlation_id,
            final_classification=decision.final_classification,
            if_match=if_match,
            idempotency_key=idempotency_key,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        response.headers["ETag"] = review_entity_tag(record)
        return serialize_terminal_review(record)

    @app.get(
        "/api/v1/documents/{document_id}/audit-events",
        response_model=AuditHistoryResponse,
        response_model_exclude_none=True,
        responses={
            401: {"model": ProblemResponse},
            403: {"model": ProblemResponse},
            404: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def get_document_audit_events(
        request: Request,
        document_id: UUID,
        response: Response,
        correlation_id: CorrelationIdHeader = None,
    ) -> AuditHistoryResponse:
        principal, request_correlation_id = authorized_document_context(request)
        history = get_document_service(app).get_audit_history(
            document_id=document_id,
            principal_id=principal.principal_id,
            correlation_id=request_correlation_id,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        return serialize_audit_history(history)

    @app.get("/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        return HealthResponse()

    @app.get(
        "/ready",
        response_model=HealthResponse,
        responses={503: {"model": ProblemResponse}},
    )
    def get_readiness() -> HealthResponse:
        if not get_document_service(app).is_ready():
            raise PublicProblem(
                status=503,
                code=ProblemCode.DEPENDENCY_UNAVAILABLE,
                title="Dependency unavailable",
                detail="A required service is temporarily unavailable.",
                correlation_id=uuid4(),
            )
        return HealthResponse()

    return app


def get_document_service(app: FastAPI) -> DocumentService:
    return cast(DocumentService, app.state.document_service)


def get_request_authorizer(app: FastAPI) -> RequestAuthorizer:
    return cast(RequestAuthorizer, app.state.request_authorizer)
