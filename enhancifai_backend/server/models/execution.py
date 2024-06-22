from pydantic import BaseModel

class RunProgressRequest(BaseModel):
    run_id: int

class RunCancelsRequest(BaseModel):
    run_id: int

class RunProgressResponse(BaseModel):
    status: str

class PromptObject(BaseModel):
    prompt: str
    columns: str
    output_heading: str

class ExportSheetsRequest(BaseModel):
    run_id: int

class RunDataRequest(BaseModel):
    run_id: int

class CacheRequest(BaseModel):
    user_id: int
    filename: str
