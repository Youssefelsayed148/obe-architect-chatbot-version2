# Phase 5 Manual QA Checklist

## Setup
- Run stack: `docker compose up -d --build --force-recreate`
- Open widget page and expand chat panel.
- Confirm mode controls are visible: `Ask Mode`, `Project Mode`, and mode indicator text.

## Knowledge Questions (RAG) - 10
1. `Summarize OBE experience in villas and what they provide.`
2. `What services does OBE provide for residential projects?`
3. `Do you have experience with commercial projects?`
4. `What education-related architecture work is listed?`
5. `Tell me about sports project experience.`
6. `What public and cultural project categories are shown?`
7. `Do you have mosque design projects?`
8. `What does OBE say about landscape or exterior design?`
9. `Which project pages mention modern villa architecture?`
10. `What project types are available on your website?`

Expected behavior:
- Routed to `/api/chat/ask` in Ask Mode or Auto knowledge intent.
- Returns concise answer text.
- Shows confidence label when confidence >= `0.55`.
- Shows collapsible Sources section with clickable URLs when sources exist.

## Lead Intent Messages (Guided) - 5
1. `I need a quote for a villa project.`
2. `Can someone call me about budget and timeline?`
3. `I want to start a project in Dubai.`
4. `What is your consultation process and cost?`
5. `Can we schedule a site visit and meeting?`

Expected behavior:
- Auto-routed to Project Mode guided flow (`/api/chat/message`) unless Ask Mode is explicitly selected.
- Existing guided responses and buttons remain functional.
- Consultation form behavior remains unchanged.

## Ambiguous Messages (Clarification) - 5
1. `Hi`
2. `Hello`
3. `Help`
4. `More info`
5. `Need information`

Expected behavior:
- Widget asks one clarifying question.
- Shows two buttons:
  - `Ask about projects/services`
  - `Start a project`
- Selecting either button routes follow-up to the matching API path.

## Error and Availability Checks
- Temporarily disable public RAG (`RAG_PUBLIC_ENABLED=false`) and restart app.
- In Ask Mode, send a knowledge question.
- Expected message: `Knowledge answers are temporarily unavailable. Please use Project Mode.`
- No uncaught JS errors in browser console.
