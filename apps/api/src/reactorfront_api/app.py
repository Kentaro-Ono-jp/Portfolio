from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Header, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from reactorfront_api.domain import ProblemCode, ProcessingStatus, PublicProblem
from reactorfront_api.event_contracts import JsonSchemaEventValidator
from reactorfront_api.persistence import SqlAlchemySubmissionRepository, create_database_engine
from reactorfront_api.rabbitmq import PikaOutboxPublisher
from reactorfront_api.request_limits import (
    MULTIPART_ENVELOPE_BYTES,
    UploadRequestBodyLimitMiddleware,
)
from reactorfront_api.schemas import (
    DocumentAcceptedResponse,
    DocumentStatusResponse,
    HealthResponse,
    ProblemResponse,
    serialize_document_status,
)
from reactorfront_api.service import MAX_DOCUMENT_BYTES, DocumentService
from reactorfront_api.settings import Settings, get_settings
from reactorfront_api.storage import S3ObjectStorage

CORRELATION_HEADER = "X-Correlation-ID"
DOCUMENT_UPLOAD_PATH = "/api/v1/documents"
PdfUpload = Annotated[UploadFile, File()]
CorrelationIdHeader = Annotated[UUID | None, Header(alias=CORRELATION_HEADER)]


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
        headers={CORRELATION_HEADER: str(problem.correlation_id)},
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


def create_app(*, service: DocumentService | None = None) -> FastAPI:
    owns_service = service is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.document_service = service or build_document_service(get_settings())
        try:
            yield
        finally:
            if owns_service:
                get_document_service(app).close()

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
            400: {"model": ProblemResponse},
            413: {"model": ProblemResponse},
            415: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def create_document(
        response: Response,
        file: PdfUpload,
        correlation_id: CorrelationIdHeader = None,
    ) -> DocumentAcceptedResponse:
        request_correlation_id = correlation_id or uuid4()
        result = get_document_service(app).submit(
            stream=file.file,
            original_filename=file.filename,
            content_type=file.content_type,
            correlation_id=request_correlation_id,
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
            404: {"model": ProblemResponse},
            422: {"model": ProblemResponse},
            503: {"model": ProblemResponse},
        },
    )
    def get_document(
        document_id: UUID,
        response: Response,
        correlation_id: CorrelationIdHeader = None,
    ) -> DocumentStatusResponse:
        request_correlation_id = correlation_id or uuid4()
        result = get_document_service(app).get_status(
            document_id=document_id,
            correlation_id=request_correlation_id,
        )
        response.headers[CORRELATION_HEADER] = str(request_correlation_id)
        return serialize_document_status(result)

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
