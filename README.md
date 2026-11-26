# Asynchronous Research Workflow API (with LLM integration)

A backend system for asynchronously executing AI-assisted research workflows, built with **FastAPI, PostgreSQL, SQLAlchemy, and Python asyncio**.

The application accepts research requests through a REST API, persists them as workflows, and processes them using a separate background worker. Each workflow generates a structured research plan, gathers web evidence, and produces a synthesized report with source references.

The project focuses on the engineering challenges behind reliable background processing: **concurrency, transactional job claiming, execution ownership, lease management, failure handling, and integration testing**.

## Architecture

The application separates HTTP request handling from potentially long-running research execution.

```text
                 Client
                   |
                   v
              FastAPI API
              /        \
          POST          GET
            \           /
             PostgreSQL
                  |
           Claim queued job
                  |
                  v
          Background Worker
             /        \
       Research      Heartbeat
          |             |
     Gemini Plan         |
          |               |
     Tavily Search     Renew Lease
          |                 |
    Evidence Collection      |
          |                   |
    Gemini Synthesis     Renew Lease
          |                    |
     Validate Sources           |
          |                      |
    Persist Final Result     Renew Lease
          |
          v
      PostgreSQL
```

The API and worker communicate through persistent PostgreSQL workflow records, rather than relying on in-memory tasks tied to the lifetime of an HTTP request.

## Core Features

### Asynchronous Workflow Processing

- Submit research instructions through a REST API.
- Persist workflows in PostgreSQL.
- Process workflows using a separate asynchronous worker.
- Track execution through `QUEUED`, `RUNNING`, `COMPLETED`, and `FAILED` states.
- Retrieve workflow status and completed results through the API.

### Concurrency-Safe Job Claiming

Workers claim jobs using PostgreSQL transactions and `SELECT ... FOR UPDATE SKIP LOCKED`.

This allows multiple workers to compete for available workflows without successfully claiming the same row in a single execution attempt.

Each claim receives a unique UUID ownership token, identifying the specific execution attempt rather than the worker process.

### Lease Management and Crash Recovery

Long-running workflows use time-limited execution leases.

- Claims establish a configurable lease expiration.
- A concurrent heartbeat periodically renews the active lease.
- Renewal requires a valid workflow state, ownership token, and unexpired lease.
- Expired running workflows become eligible for reclamation.
- Reclaimed workflows receive new ownership tokens, invalidating previous attempts.

Lease comparisons use PostgreSQL's clock to avoid relying on potentially inconsistent worker-machine clocks.

### Atomic State Transitions

Workflow completion and failure use conditional SQL `UPDATE` statements.

A transition succeeds only when the workflow is still running, the supplied claim token matches the current owner, and the lease remains valid.

These conditions are evaluated atomically by PostgreSQL, preventing stale execution attempts from overwriting workflow state after ownership changes.

### Asynchronous Task Supervision

Research execution and heartbeat renewal run as independent asyncio tasks.

The worker supervises both tasks, observes failures, and coordinates cancellation and cleanup.

If lease renewal is rejected while research is pending, the research task is cancelled instead of continuing as though ownership were still valid.

### Structured Research and Source Validation

The research pipeline uses Google Gemini and Tavily to:

1. Generate a structured research plan.
2. Execute web searches.
3. Normalize and deduplicate retrieved results.
4. Build an evidence collection with unique source identifiers.
5. Synthesize a structured report containing findings, references, and limitations.
6. Validate that cited source identifiers exist in the collected evidence.

Citation validation enforces source-reference integrity; it does not independently prove the factual accuracy of every synthesized claim.

## Technology Stack

| Area | Technology |
|---|---|
| Language | Python |
| API | FastAPI, Pydantic |
| Database | PostgreSQL |
| Database access | Async SQLAlchemy |
| Migrations | Alembic |
| Concurrency | asyncio, PostgreSQL row locking |
| AI integration | Google Gemini |
| Web research | Tavily |
| HTTP | httpx |
| Testing | pytest, pytest-asyncio |
| Infrastructure | Docker, Docker Compose |

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/workflows` | Submit a research workflow |
| `GET` | `/v1/workflows/{workflow_id}` | Retrieve workflow status and result |

### Example: Submit a Workflow

```http
POST /v1/workflows
Content-Type: application/json

{
  "instruction": "Compare PostgreSQL and MongoDB for a high-traffic backend application."
}
```

The API returns HTTP `202 Accepted` with the newly created workflow identifier and initial status.

The client can then poll the GET endpoint to retrieve the workflow's current state and, when available, its research result.

## Local Development

The application is containerized using Docker Compose, with the API, PostgreSQL database, and background worker running as separate services.

To run locally:

1. Configure the database connection and required Google Gemini and Tavily API credentials using the project's environment configuration.
2. Start the configured services with Docker Compose:

```bash
docker compose up --build
```

3. Apply Alembic migrations in the configured application environment if they are not already applied during startup.
4. Access the FastAPI endpoints and interactive API documentation.

See `src/config.py` and the Docker Compose configuration for the environment variables and service-specific commands.

## Testing Strategy

The project includes unit and integration tests covering both research behavior and backend reliability.

### Workflow and Database Tests

- Workflow creation, claiming, completion, and failure.
- Concurrent worker claiming.
- Atomic state transitions and ownership validation.
- Rejection of stale or incorrect claim tokens.
- Lease creation, renewal, and expiration.
- Protection against unauthorized workflow updates.

### Asyncio and Worker Tests

- Periodic heartbeat renewal.
- Clean task cancellation.
- Research and heartbeat coordination.
- Research execution failures.
- Heartbeat failure while research is pending.
- Verification that obsolete executions do not persist results.

### Research Pipeline Tests

- Research planning and synthesis.
- Search-result normalization.
- Evidence collection.
- Citation identifier validation.
- Handling invalid or insufficient evidence.

Database-backed tests use a dedicated PostgreSQL test environment. External AI and search-provider interactions are mocked where appropriate, allowing application logic to be exercised without relying on live provider responses.

## Engineering Design Decisions

**PostgreSQL-backed queue:** Keeps workflow state durable and enables transactional job claiming without introducing an additional message broker.

**Short-lived database transactions:** Row locks are released after claiming rather than being held during slow external API requests.

**Per-attempt ownership tokens:** Prevent previous execution attempts from persisting results after a workflow is reclaimed.

**Database-managed leases:** Allow abandoned workflows to be identified and recovered after worker failure.

**Separate API and worker processes:** Decouple request-response latency from background execution time.

**Explicit asyncio task supervision:** Ensures that heartbeat and research failures are observed and unfinished tasks are cleaned up.

**Integration-focused testing:** Verifies important behavior against PostgreSQL instead of relying exclusively on mocked repositories.

## Reliability Considerations and Limitations

The system uses **at-least-once processing semantics** when recovering abandoned workflows. A workflow may be executed more than once after a crash or lease expiration.

Ownership tokens prevent stale attempts from updating PostgreSQL state, but they cannot automatically undo external operations already performed.

Additional production-oriented improvements could include:

- Configurable retry limits and exponential backoff.
- More flexible scheduling between recovered and newly queued jobs.
- Workflow execution timeouts.
- Expanded operational metrics and alerting.
- Stronger protection against duplicate external side effects.

The current implementation is intended to demonstrate backend architecture and reliability mechanisms, rather than claim exactly-once execution or comprehensive production infrastructure.

## Project Focus

This project was developed to explore the fundamentals of reliable backend systems, particularly:

**PostgreSQL transactions and locking, asynchronous execution, concurrency control, atomic state transitions, background processing, failure recovery, dependency injection, and testable service architecture.**

The AI research functionality provides a realistic long-running workload in which those engineering concerns become necessary.