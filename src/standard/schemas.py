from pydantic import BaseModel 

class HumanizeRequest(BaseModel):
    text: str

class HumanizeResponse(BaseModel):
    original: str
    rewritten: str
    score_before: float
    score_after: float
