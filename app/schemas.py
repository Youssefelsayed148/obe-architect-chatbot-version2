from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Literal

Channel = Literal["web", "instagram", "whatsapp"]

class ChatMessageIn(BaseModel):
    channel: Channel = "web"
    user_id: str
    session_id: Optional[str] = None
    text: Optional[str] = None
    button_id: Optional[str] = None

class Button(BaseModel):
    id: str
    label: str

class OutMessage(BaseModel):
    type: Literal["text"] = "text"
    text: str

class FormField(BaseModel):
    key: str
    label: str
    kind: Literal["text", "email", "tel", "select", "textarea"] = "text"
    required: bool = True
    options: Optional[List[str]] = None

class ChatMessageOut(BaseModel):
    session_id: str
    messages: List[OutMessage]
    buttons: List[Button] = Field(default_factory=list)
    form: Optional[FormField] = None


class LeadCreateIn(BaseModel):
    name: str
    phone: str
    email: str
    consultant_type: Optional[str] = None
    source: str = "chatbot"
    session_id: Optional[str] = None


class LeadCreateOut(BaseModel):
    ok: bool = True
    lead_id: int


class AnalyticsEventIn(BaseModel):
    event_name: Literal["project_category_click"]
    category: Optional[str] = None
    department: Optional[str] = None
    url: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    source: str = "chatbot"

    @model_validator(mode="after")
    def _require_department_for_click(self):
        if self.event_name == "project_category_click" and not (self.department or self.category):
            raise ValueError("department is required for click events (or provide category for backward compatibility)")
        return self


class AnalyticsEventOut(BaseModel):
    ok: bool = True


class AnalyticsClickCountItem(BaseModel):
    department: str
    clicks: int


class AnalyticsRangeOut(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None


class AnalyticsClicksByDepartmentOut(BaseModel):
    range: AnalyticsRangeOut
    items: List[AnalyticsClickCountItem]
    total_clicks: int
