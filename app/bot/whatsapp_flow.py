from dataclasses import dataclass
from typing import Literal

from app.bot import content
from app.bot.state_machine import handle_message
from app.schemas import ChatMessageIn
from app.store.redis_sessions import get_session, set_state

MENU_CONSULTATION = "MENU_CONSULTATION"
MENU_PROJECTS = "MENU_PROJECTS"
MENU_HUMAN = "MENU_HUMAN"
MENU_MAIN = "MENU_MAIN"

PROJECT_ACTIONS = {
    "PROJECT_VILLAS": "villas",
    "PROJECT_COMMERCIAL": "commercial",
    "PROJECT_MOSQUES": "mosques",
    "PROJECT_SPORTS": "sports",
    "PROJECT_EDUCATION": "education",
    "PROJECT_PUBLIC_CULTURAL": "public_cultural",
}


@dataclass
class WhatsAppReply:
    kind: Literal["none", "text", "buttons", "list"]
    text: str | None = None
    buttons: list[dict[str, str]] | None = None
    list_sections: list[dict] | None = None
    list_button_text: str | None = None
    new_state: str | None = None


def _main_menu() -> WhatsAppReply:
    return WhatsAppReply(
        kind="buttons",
        text="Welcome to OBE Architects. How can we help today?",
        buttons=[
            {"id": MENU_CONSULTATION, "title": "Request Consultation"},
            {"id": MENU_PROJECTS, "title": "View Projects"},
            {"id": MENU_HUMAN, "title": "Talk to Human"},
        ],
        new_state="WA_MAIN_MENU",
    )


def _projects_list() -> WhatsAppReply:
    return WhatsAppReply(
        kind="list",
        text="Select a project category:",
        list_button_text="Project Categories",
        list_sections=[
            {
                "title": "Projects",
                "rows": [
                    {"id": "PROJECT_VILLAS", "title": "Villas"},
                    {"id": "PROJECT_COMMERCIAL", "title": "Commercial"},
                    {"id": "PROJECT_MOSQUES", "title": "Mosques"},
                    {"id": "PROJECT_SPORTS", "title": "Sports"},
                    {"id": "PROJECT_EDUCATION", "title": "Education"},
                    {"id": "PROJECT_PUBLIC_CULTURAL", "title": "Public & Cultural"},
                ],
            }
        ],
        new_state="PROJECTS_MENU",
    )


def _consultation_response() -> WhatsAppReply:
    return WhatsAppReply(
        kind="buttons",
        text=(
            "To request a consultation, please share your details using our contact form:\n"
            f"{content.CONTACT_LINK}\n\n"
            "If you'd like, you can also request a human teammate here."
        ),
        buttons=[
            {"id": MENU_MAIN, "title": "Back to Menu"},
            {"id": MENU_HUMAN, "title": "Talk to Human"},
        ],
        new_state="WA_CONSULT",
    )


def _from_state_machine(session_id: str, button_id: str) -> WhatsAppReply:
    msg = ChatMessageIn(
        channel="whatsapp",
        user_id="wa",
        session_id=session_id,
        text=None,
        button_id=button_id,
    )
    response = handle_message(session_id, msg)
    text = response.messages[0].text if response.messages else content.WELCOME_TEXT
    buttons = []
    for btn in response.buttons[:3]:
        mapped_id = None
        if btn.id in {"menu", "back"}:
            mapped_id = MENU_MAIN
        elif btn.id == "consult":
            mapped_id = MENU_CONSULTATION
        if mapped_id:
            buttons.append({"id": mapped_id, "title": btn.label})

    return WhatsAppReply(
        kind="buttons" if buttons else "text",
        text=text,
        buttons=buttons if buttons else None,
        new_state=get_session(session_id).state,
    )


def handle_whatsapp_flow(session_id: str, action_id: str | None, text: str | None) -> WhatsAppReply:
    sess = get_session(session_id)
    state = (sess.state or "").strip()

    if not action_id:
        set_state(session_id, "WA_MAIN_MENU")
        return _main_menu()

    if action_id == MENU_MAIN:
        set_state(session_id, "WA_MAIN_MENU")
        return _main_menu()

    if action_id == MENU_PROJECTS:
        set_state(session_id, "PROJECTS_MENU")
        return _projects_list()

    if action_id == MENU_CONSULTATION:
        set_state(session_id, "WA_CONSULT")
        return _consultation_response()

    if action_id in PROJECT_ACTIONS:
        return _from_state_machine(session_id, PROJECT_ACTIONS[action_id])

    set_state(session_id, "WA_MAIN_MENU")
    return _main_menu()
