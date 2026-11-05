from uuid import uuid4

from src.enums import WorkflowStatus
from src.schemas.workflow import WorkflowCreateRequest

BASE_URL = "/v1/workflows"


async def test_workflow_create_success(
        client,

):
    payload = WorkflowCreateRequest(
        instruction="Test instruction"
    )

    response = await client.post(
        url=BASE_URL,
        json=payload.model_dump()
    )

    assert response.status_code == 202

    result = response.json()

    assert result["id"] is not None
    assert result["status"] == WorkflowStatus.QUEUED.value


async def test_empty_instruction_rejected(
        client
):
    response = await client.post(
        url=BASE_URL,
        json={"instruction": ""}
    )

    assert response.status_code == 422

    result = response.json()

    assert result["detail"][0]["msg"] == "String should have at least 2 characters"


async def test_workflow_retrieval(
        client,
        workflow_create
):
    workflow_id = workflow_create.id

    response = await client.get(
        url=f"{BASE_URL}/{workflow_id}"
    )

    assert response.status_code == 200

    result = response.json()

    assert result["status"] == WorkflowStatus.QUEUED.value
    assert result["result"] is None


async def test_invalid_workflow_retrieval(
        client,
):
    invalid_workflow_id = uuid4()

    response = await client.get(
        url=f"{BASE_URL}/{invalid_workflow_id}"
    )

    assert response.status_code == 404

    result = response.json()

    assert result["detail"] == "Not Found"


async def test_workflow_create_retrieve_pipeline(
        client
):
    payload = WorkflowCreateRequest(
        instruction="Test instruction"
    )

    post_response = await client.post(
        url=BASE_URL,
        json=payload.model_dump()
    )

    assert post_response.status_code == 202

    post_result = post_response.json()

    workflow_id = post_result["id"]

    response = await client.get(
        url=f"{BASE_URL}/{workflow_id}"
    )

    assert response.status_code == 200

    result = response.json()

    assert result["status"] == WorkflowStatus.QUEUED.value
    assert result["result"] is None