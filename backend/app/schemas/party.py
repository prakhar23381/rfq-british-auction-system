import uuid

from app.schemas.common import ApiModel


class PartyOut(ApiModel):
    """A buyer or supplier as shown next to RFQs, bids and activity entries."""

    id: uuid.UUID
    name: str
    company_name: str
