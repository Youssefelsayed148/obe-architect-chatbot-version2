from datetime import datetime
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Json
from app.settings import settings
from app.services.lead_email_templates import build_subject, build_body_text, build_body_html
from app.services.handoff_email_templates import (
    build_subject as build_handoff_subject,
    build_body_text as build_handoff_body_text,
    build_body_html as build_handoff_body_html,
)

def init_db():
    with connect(settings.postgres_dsn) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS leads (
          id BIGSERIAL PRIMARY KEY,
          created_at TIMESTAMPTZ DEFAULT now(),
          name TEXT NOT NULL,
          phone TEXT NOT NULL,
          email TEXT NOT NULL,
          project_type TEXT,
          message TEXT,
          source TEXT NOT NULL,
          session_id TEXT NOT NULL
        );
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS email_outbox (
          id BIGSERIAL PRIMARY KEY,
          event_key TEXT NOT NULL UNIQUE,
          lead_id BIGINT REFERENCES leads(id) ON DELETE CASCADE,
          event_type TEXT NOT NULL DEFAULT 'lead',
          to_email TEXT NOT NULL,
          subject TEXT NOT NULL,
          body_text TEXT NOT NULL,
          body_html TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          attempts INT NOT NULL DEFAULT 0,
          last_error TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          sent_at TIMESTAMPTZ
        );
        """)
        con.execute("ALTER TABLE email_outbox ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'lead';")
        con.execute("ALTER TABLE email_outbox ALTER COLUMN lead_id DROP NOT NULL;")
        con.execute("CREATE INDEX IF NOT EXISTS idx_email_outbox_status_created_at ON email_outbox(status, created_at);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_email_outbox_lead_id ON email_outbox(lead_id);")

        con.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
          id BIGSERIAL PRIMARY KEY,
          event_name TEXT NOT NULL,
          category TEXT,
          department TEXT,
          url TEXT,
          session_id TEXT,
          user_id TEXT,
          source TEXT NOT NULL DEFAULT 'chatbot',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """)
        con.execute("ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS department TEXT;")
        con.execute("ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS route_taken TEXT;")
        con.execute("ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS retrieval_top_score DOUBLE PRECISION;")
        con.execute("ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS retrieval_k INTEGER;")
        con.execute("ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS fallback_reason TEXT;")

        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_event_name ON analytics_events(event_name);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_category ON analytics_events(category);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_department ON analytics_events(department);")
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_analytics_events_clicks_grouping "
            "ON analytics_events(event_name, department, created_at);"
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_session_id ON analytics_events(session_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analytics_events_source ON analytics_events(source);")

        if settings.rag_enabled or settings.rag_public_enabled:
            embed_dim = int(getattr(settings, "rag_embed_dim", 768))
            con.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            con.execute("""
            CREATE TABLE IF NOT EXISTS rag_documents (
              id BIGSERIAL PRIMARY KEY,
              url TEXT UNIQUE NOT NULL,
              title TEXT,
              doc_type TEXT,
              source TEXT,
              content_hash TEXT,
              scraped_at_utc TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """)
            con.execute("ALTER TABLE IF EXISTS rag_documents ADD COLUMN IF NOT EXISTS doc_type TEXT;")
            con.execute(f"""
            CREATE TABLE IF NOT EXISTS rag_chunks (
              id BIGSERIAL PRIMARY KEY,
              document_url TEXT NOT NULL REFERENCES rag_documents(url) ON DELETE CASCADE,
              chunk_index INT NOT NULL,
              chunk_text TEXT NOT NULL,
              chunk_char_len INT NOT NULL,
              embedding VECTOR({embed_dim}) NOT NULL,
              embedding_model TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              UNIQUE(document_url, chunk_index, embedding_model)
            );
            """)
            con.execute("CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_url ON rag_chunks(document_url);")
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_ivfflat "
                "ON rag_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
            )

        con.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
          id BIGSERIAL PRIMARY KEY,
          channel TEXT NOT NULL,
          external_user_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          state TEXT,
          handoff_status TEXT NOT NULL DEFAULT 'bot',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(channel, external_user_id)
        );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_conversations_handoff_status ON conversations(handoff_status);")

        con.execute("""
        CREATE TABLE IF NOT EXISTS messages (
          id BIGSERIAL PRIMARY KEY,
          conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
          direction TEXT NOT NULL,
          provider_message_id TEXT,
          payload JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE(conversation_id, provider_message_id)
        );
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_messages_provider_message_id ON messages(provider_message_id);")
        con.commit()

def insert_lead(*, name: str, phone: str, email: str, project_type: str | None,
                message: str | None, source: str, session_id: str) -> int:
    with connect(settings.postgres_dsn) as con:
        with con.cursor() as cur:
            cur.execute(
                """INSERT INTO leads(name, phone, email, project_type, message, source, session_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (name, phone, email, project_type, message, source, session_id),
            )
            lead_id = cur.fetchone()[0]
        con.commit()
        return lead_id


def insert_consultation_lead(*, name: str, phone: str, email: str, consultant_type: str | None,
                             source: str, session_id: str) -> int:
    return insert_lead(
        name=name,
        phone=phone,
        email=email,
        project_type=consultant_type,
        message=None,
        source=source,
        session_id=session_id,
    )


def insert_consultation_lead_and_enqueue_email(
    *,
    name: str,
    phone: str,
    email: str,
    consultant_type: str | None,
    source: str,
    session_id: str,
    notify_to: str,
) -> int:
    notify_to_clean = (notify_to or "").strip()
    if not notify_to_clean:
        raise RuntimeError("LEADS_NOTIFY_TO is not configured")

    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """INSERT INTO leads(name, phone, email, project_type, message, source, session_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id, created_at""",
                (name, phone, email, consultant_type, None, source, session_id),
            )
            lead_row = cur.fetchone()
            lead_id = int(lead_row["id"])
            lead_data = {
                "id": lead_id,
                "created_at": lead_row["created_at"],
                "name": name,
                "email": email,
                "phone": phone,
                "consultant_type": consultant_type,
                "message": None,
                "source": source,
                "session_id": session_id,
            }
            event_key = f"lead_notify:{lead_id}"
            cur.execute(
                """INSERT INTO email_outbox(event_key, lead_id, to_email, subject, body_text, body_html)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (event_key) DO NOTHING""",
                (
                    event_key,
                    lead_id,
                    notify_to_clean,
                    build_subject(str(lead_id)),
                    build_body_text(lead_data),
                    build_body_html(lead_data),
                ),
            )
        con.commit()
        return lead_id


def insert_analytics_event(
    *,
    event_name: str,
    category: str | None,
    department: str | None,
    url: str | None,
    session_id: str | None,
    user_id: str | None,
    source: str,
    route_taken: str | None,
    retrieval_top_score: float | None,
    retrieval_k: int | None,
    fallback_reason: str | None,
) -> None:
    with connect(settings.postgres_dsn) as con:
        con.execute(
            """
            INSERT INTO analytics_events(
                event_name, category, department, url, session_id, user_id, source,
                route_taken, retrieval_top_score, retrieval_k, fallback_reason
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                event_name,
                category,
                department,
                url,
                session_id,
                user_id,
                source,
                route_taken,
                retrieval_top_score,
                retrieval_k,
                fallback_reason,
            ),
        )
        con.commit()


def get_click_counts_by_department(*, start: datetime | None = None, end: datetime | None = None):
    query = (
        "SELECT COALESCE(NULLIF(BTRIM(department), ''), 'unknown') AS department, COUNT(*) AS clicks "
        "FROM analytics_events "
        "WHERE event_name = 'project_category_click'"
    )
    params = []
    if start is not None:
        query += " AND created_at >= %s"
        params.append(start)
    if end is not None:
        query += " AND created_at <= %s"
        params.append(end)
    query += " GROUP BY 1 ORDER BY clicks DESC, department ASC"

    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            return cur.fetchall()


def claim_pending_email_outbox(limit: int = 10):
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                WITH picked AS (
                    SELECT id
                    FROM email_outbox
                    WHERE status = 'pending' AND attempts < 8
                    ORDER BY created_at
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE email_outbox e
                SET attempts = e.attempts + 1
                FROM picked
                WHERE e.id = picked.id
                RETURNING e.id, e.lead_id, e.event_type, e.to_email, e.subject, e.body_text, e.body_html, e.attempts
                """,
                (limit,),
            )
            rows = cur.fetchall()
        con.commit()
        return rows


def mark_email_outbox_sent(outbox_id: int) -> None:
    with connect(settings.postgres_dsn) as con:
        con.execute(
            "UPDATE email_outbox SET status='sent', sent_at=now(), last_error=NULL WHERE id=%s",
            (outbox_id,),
        )
        con.commit()


def mark_email_outbox_failure(outbox_id: int, error: str) -> None:
    with connect(settings.postgres_dsn) as con:
        con.execute(
            """
            UPDATE email_outbox
            SET last_error=%s,
                status=CASE WHEN attempts >= 8 THEN 'failed' ELSE 'pending' END
            WHERE id=%s
            """,
            (error[:2000], outbox_id),
        )
        con.commit()


def list_leads(limit: int = 50):
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, created_at, name, phone, email, project_type, source, session_id "
                "FROM leads ORDER BY id DESC LIMIT %s",
                (limit,),
            )
            return cur.fetchall()


def get_conversation_by_id(conversation_id: int):
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, channel, external_user_id, session_id, state, handoff_status, created_at, updated_at "
                "FROM conversations WHERE id=%s",
                (conversation_id,),
            )
            row = cur.fetchone()
            return row


def get_or_create_conversation(*, channel: str, external_user_id: str, session_id: str):
    with connect(settings.postgres_dsn) as con:
        with con.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO conversations(channel, external_user_id, session_id)
                VALUES (%s,%s,%s)
                ON CONFLICT (channel, external_user_id)
                DO UPDATE SET updated_at=now()
                RETURNING id, channel, external_user_id, session_id, state, handoff_status, created_at, updated_at
                """,
                (channel, external_user_id, session_id),
            )
            row = cur.fetchone()
        con.commit()
        return row


def update_conversation_state(conversation_id: int, state: str | None) -> None:
    with connect(settings.postgres_dsn) as con:
        con.execute(
            "UPDATE conversations SET state=%s, updated_at=now() WHERE id=%s",
            (state, conversation_id),
        )
        con.commit()


def update_handoff_status(conversation_id: int, status: str) -> None:
    with connect(settings.postgres_dsn) as con:
        con.execute(
            "UPDATE conversations SET handoff_status=%s, updated_at=now() WHERE id=%s",
            (status, conversation_id),
        )
        con.commit()


def insert_message(
    *,
    conversation_id: int,
    direction: str,
    provider_message_id: str | None,
    payload: dict,
) -> int | None:
    with connect(settings.postgres_dsn) as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages(conversation_id, direction, provider_message_id, payload)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT (conversation_id, provider_message_id) DO NOTHING
                RETURNING id
                """,
                (conversation_id, direction, provider_message_id, Json(payload)),
            )
            row = cur.fetchone()
        con.commit()
        return int(row[0]) if row else None


def enqueue_handoff_email(
    *,
    conversation_id: int,
    channel: str,
    external_user_id: str,
    last_message: str | None,
    notify_to: str,
    event_key: str,
) -> None:
    notify_to_clean = (notify_to or "").strip()
    if not notify_to_clean:
        raise RuntimeError("HANDOFF_NOTIFY_TO is not configured")

    details = {
        "conversation_id": conversation_id,
        "created_at": datetime.utcnow(),
        "channel": channel,
        "external_user_id": external_user_id,
        "last_message": last_message,
    }

    with connect(settings.postgres_dsn) as con:
        with con.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_outbox(event_key, lead_id, event_type, to_email, subject, body_text, body_html)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_key) DO NOTHING
                """,
                (
                    event_key,
                    None,
                    "handoff_requested",
                    notify_to_clean,
                    build_handoff_subject(str(conversation_id)),
                    build_handoff_body_text(details),
                    build_handoff_body_html(details),
                ),
            )
        con.commit()
