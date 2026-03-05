from app.schemas import ChatMessageIn, ChatMessageOut, OutMessage, Button
from app.store.redis_sessions import get_session, set_state, set_data
from app.bot import content


def _screen(session_id: str, text: str, buttons=None, form=None) -> ChatMessageOut:
    return ChatMessageOut(
        session_id=session_id,
        messages=[OutMessage(text=text)],
        buttons=buttons or [],
        form=form,
    )


def handle_message(session_id: str, msg: ChatMessageIn) -> ChatMessageOut:
    sess = get_session(session_id)
    state = sess.state

    def main_menu():
        set_state(session_id, "WELCOME")
        return _screen(
            session_id,
            content.WELCOME_TEXT,
            buttons=[
                Button(id="projects", label="Browse Projects"),
                Button(id="services", label="Our Services"),
                Button(id="consult", label="Request a Consultation"),
            ],
        )

    def consult_cta():
        set_state(session_id, "WELCOME")
        return _screen(
            session_id,
            "Please use the consultation form in this chat to share your details.",
            buttons=[Button(id="menu", label="Back to Menu")],
        )

    # First open: return welcome if nothing is sent
    if state == "WELCOME" and msg.button_id is None and msg.text is None:
        return main_menu()

    # ===== WELCOME =====
    if state == "WELCOME":
        if msg.button_id == "projects":
            set_state(session_id, "PROJECTS_MENU")
            return _screen(
                session_id,
                content.PROJECTS_TEXT,
                buttons=[
                    Button(id="villas", label="Villas"),
                    Button(id="commercial", label="Commercial"),
                    Button(id="education", label="Education"),
                    Button(id="sports", label="Sports"),
                    Button(id="public_cultural", label="Public & Cultural"),
                    Button(id="mosques", label="Mosques"),
                    Button(id="back", label="Back to Menu"),
                ],
            )

        if msg.button_id == "services":
            set_state(session_id, "SERVICES_MENU")
            return _screen(
                session_id,
                content.SERVICES_TEXT,
                buttons=[
                    Button(id="architecture", label="Architectural Design"),
                    Button(id="interiors", label="Interior Design"),
                    Button(id="supervision", label="Supervision"),
                    Button(id="masterplanning", label="Master Planning"),
                    Button(id="back", label="Back to Menu"),
                ],
            )

        if msg.button_id == "consult":
            return consult_cta()

        return main_menu()

    # ===== PROJECTS =====
    if state == "PROJECTS_MENU":
        if msg.button_id == "back":
            return main_menu()

        if msg.button_id in content.CATEGORY_LABELS:
            set_data(session_id, "project_category", msg.button_id)
            set_state(session_id, "PROJECT_CATEGORY_DETAIL")
            cat = content.CATEGORY_LABELS[msg.button_id]
            project_link = content.PROJECT_CATEGORY_LINKS.get(msg.button_id, content.PROJECT_LINK)
            return _screen(
                session_id,
                f"You can explore our recent **{cat}** projects here:\n{project_link}\n\n"
                "Would you like to discuss a similar project with our team?",
                buttons=[
                    Button(id="consult", label="Request a Consultation"),
                    Button(id="menu", label="Back to Menu"),
                ],
            )

        return _screen(session_id, content.PROJECTS_TEXT)

    if state == "PROJECT_CATEGORY_DETAIL":
        if msg.button_id == "menu":
            return main_menu()
        if msg.button_id == "consult":
            return consult_cta()
        return main_menu()

    # ===== SERVICES =====
    if state == "SERVICES_MENU":
        if msg.button_id == "back":
            return main_menu()

        if msg.button_id in content.SERVICE_BLURBS:
            set_data(session_id, "service", msg.button_id)
            set_state(session_id, "SERVICE_DETAIL")
            blurb = content.SERVICE_BLURBS[msg.button_id]
            return _screen(
                session_id,
                f"{blurb}\n\nLearn more:\n{content.EXPERTISE_LINK}\n\nWould you like to discuss your project?",
                buttons=[
                    Button(id="consult", label="Request a Consultation"),
                    Button(id="menu", label="Back to Menu"),
                ],
            )

        return _screen(session_id, content.SERVICES_TEXT)

    if state == "SERVICE_DETAIL":
        if msg.button_id == "menu":
            return main_menu()
        if msg.button_id == "consult":
            return consult_cta()
        return main_menu()

    # Legacy states from old multi-turn lead capture are now redirected.
    if state in {"FORM_NAME", "FORM_PHONE", "FORM_EMAIL", "FORM_PROJECT_TYPE", "FORM_MESSAGE"}:
        return consult_cta()

    if state == "CONFIRMATION":
        return main_menu() if msg.button_id == "menu" else main_menu()

    return main_menu()
