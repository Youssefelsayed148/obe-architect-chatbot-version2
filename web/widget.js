let sessionId = null;
let typingEl = null;

const WIDGET_CONFIG = window.OBE_CHATBOT_CONFIG || {};
const API_BASE = (
  typeof WIDGET_CONFIG.apiBase === "string" && WIDGET_CONFIG.apiBase.trim()
    ? WIDGET_CONFIG.apiBase
    : window.location.origin
).replace(/\/+$/, "");
const API_ROOT = `${API_BASE}/api`;
const CHAT_USER_ID = (
  typeof WIDGET_CONFIG.userId === "string" && WIDGET_CONFIG.userId.trim()
    ? WIDGET_CONFIG.userId.trim()
    : "web_user"
);
const URL_REGEX = /(https?:\/\/[\w\-._~:/?#[\]@!$&'()*+,;=%]+)/gi;
const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const LEAD_INTENT_KEYWORDS = [
  "quote",
  "budget",
  "price",
  "cost",
  "contact",
  "call",
  "phone",
  "consultation",
  "meeting",
  "start project",
  "start a project",
  "hire",
  "timeline",
  "timeframe",
  "sqft",
  "sqm",
  "area",
  "location",
  "site visit",
  "my name is",
  "my phone",
  "my email",
];
const CONSULTANT_TYPES = [
  "Architectural Design",
  "Interior Design",
  "Landscape",
  "Fit-out / Execution",
  "Engineering / Technical",
  "Other",
];
const PROJECTS_BASE_LINK = "https://obearchitects.com/obe/projectlists.php?category=";
const PROJECT_THUMB_PLACEHOLDER = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='220' viewBox='0 0 320 220'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0' x2='1' y1='0' y2='1'%3E%3Cstop offset='0%25' stop-color='%230f6fb5'/%3E%3Cstop offset='100%25' stop-color='%231a8ca3'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='320' height='220' fill='url(%23g)'/%3E%3Ccircle cx='260' cy='50' r='40' fill='rgba(255,255,255,0.18)'/%3E%3Ccircle cx='60' cy='180' r='56' fill='rgba(255,255,255,0.12)'/%3E%3C/svg%3E";
const THUMBS_BASE_PATH = `${API_ROOT}/static/chatbot/thumbs`;

function getCurrentScriptSrc() {
  if (document.currentScript && document.currentScript.src) {
    return document.currentScript.src;
  }

  const scriptTags = document.querySelectorAll("script[src]");
  const lastScript = scriptTags[scriptTags.length - 1];
  return lastScript && lastScript.src ? lastScript.src : `${window.location.origin}/widget.js`;
}

function ensureWidgetStyles() {
  if (document.querySelector('link[data-obe-widget="true"]')) {
    return;
  }

  const cssHref = (
    typeof WIDGET_CONFIG.cssUrl === "string" && WIDGET_CONFIG.cssUrl.trim()
      ? WIDGET_CONFIG.cssUrl
      : new URL("./widget.css", getCurrentScriptSrc()).toString()
  );

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = cssHref;
  link.dataset.obeWidget = "true";
  document.head.appendChild(link);
}

function ensureWidgetMarkup() {
  if (document.getElementById("launcher") && document.getElementById("panel")) {
    return;
  }

  const container = document.createElement("div");
  container.dataset.obeWidgetRoot = "true";
  container.innerHTML = `
    <button id="launcher" aria-label="Open chat" aria-expanded="false">Chat with OBE</button>
    <div id="panel" aria-hidden="true">
      <div id="panelHeader">
        <div class="brandDot"></div>
        <div>
          <div class="title">OBE Architects</div>
          <div class="subtitle">Design support assistant</div>
        </div>
      </div>
      <div id="chatBody">
        <div id="chatScroll">
          <div id="messages" aria-live="polite"></div>
          <div id="buttons"></div>
          <div id="leadFormHost"></div>
          <div id="form"></div>
        </div>
        <div id="composer">
          <input id="chatInput" type="text" maxlength="2000" placeholder="Type your message..." aria-label="Type your message" />
          <button id="chatSendBtn" type="button">Send</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(container);
}

ensureWidgetStyles();
ensureWidgetMarkup();
const projectCategories = [
  // Add future categories by appending { id, title, imageKey?, link }.
  // Thumbnail files should be placed at `${THUMBS_BASE_PATH}/${imageKey || id}.jpg` (or .webp fallback).
  { id: "villas", title: "Villas", link: `${PROJECTS_BASE_LINK}villas` },
  { id: "commercial", title: "Commercial", link: `${PROJECTS_BASE_LINK}commercial` },
  { id: "education", title: "Education", link: `${PROJECTS_BASE_LINK}education` },
  { id: "sports", title: "Sports", link: `${PROJECTS_BASE_LINK}sports` },
  { id: "public_cultural", title: "Public & Cultural", imageKey: "public-and-clutural", link: `${PROJECTS_BASE_LINK}publicncultural` },
  { id: "mosques", title: "Mosques", link: `${PROJECTS_BASE_LINK}mosques` },
];

const panel = document.getElementById("panel");
const chatBody = document.getElementById("chatBody");
const chatScrollEl = document.getElementById("chatScroll");
const launcher = document.getElementById("launcher");
const messagesEl = document.getElementById("messages");
const buttonsEl = document.getElementById("buttons");
const leadFormHostEl = document.getElementById("leadFormHost");
const formEl = document.getElementById("form");
const chatInputEl = document.getElementById("chatInput");
const chatSendBtnEl = document.getElementById("chatSendBtn");
const WHATSAPP_NUMBER = "201016662324";

const leadFormState = {
  values: {
    name: "",
    phone: "",
    email: "",
    consultant_type: "",
  },
  errors: {},
  submitError: "",
  isSubmitting: false,
  submitted: false,
  submittedLead: null,
};
const chatUiState = {
  isSending: false,
  lastRagSources: [],
  lastRagTopic: "",
  lastRagAt: 0,
  followUpCount: 0,
};

if (chatSendBtnEl && chatSendBtnEl.dataset.bound !== "1") {
  chatSendBtnEl.dataset.bound = "1";
  chatSendBtnEl.addEventListener("click", () => {
    submitComposerText().catch(() => {
      addMessage("Something went wrong. Please try again.", "error");
    });
  });
}
if (chatInputEl && chatInputEl.dataset.bound !== "1") {
  chatInputEl.dataset.bound = "1";
  chatInputEl.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitComposerText().catch(() => {
        addMessage("Something went wrong. Please try again.", "error");
      });
    }
  });
}

if (launcher && launcher.dataset.bound !== "1") {
  launcher.dataset.bound = "1";
  launcher.addEventListener("click", async () => {
    const isOpen = panel.classList.toggle("is-open");
    panel.setAttribute("aria-hidden", String(!isOpen));
    launcher.setAttribute("aria-expanded", String(isOpen));

    if (isOpen && !sessionId) {
      try {
        await sendGuidedMessage({ text: null, buttonId: null });
      } catch (_err) {
        addMessage("Network error. Please try again.", "error");
      }
    }
  });
}

function scrollToLatest() {
  const scrollHost = chatScrollEl || chatBody;
  if (!scrollHost) return;
  scrollHost.scrollTop = scrollHost.scrollHeight;
}

function deriveLinkLabel(url) {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname.toLowerCase();

    if (path.includes("project")) return "View Projects";
    if (path.includes("service")) return "View Services";
    if (path.includes("contact")) return "Contact Us";
    if (path.includes("about")) return "Learn About Us";

    const domain = parsed.hostname.replace(/^www\./i, "");
    return `Open ${domain}`;
  } catch {
    return "Open Link";
  }
}

function buildStructuredMessage(text) {
  if (!text) {
    return { text: "", buttons: [] };
  }

  const urls = [...text.matchAll(URL_REGEX)].map(match => match[0]);
  const uniqueUrls = [...new Set(urls)];
  const buttons = uniqueUrls.map(url => ({ label: deriveLinkLabel(url), url }));
  const normalizedText = text.replace(URL_REGEX, "").replace(/\s{2,}/g, " ").trim();

  return { text: normalizedText, buttons };
}

function normalizePhone(value) {
  const trimmed = value.trim();
  if (!trimmed) return null;

  const compact = trimmed.replace(/[()\-.\s]/g, "");
  const withPlus = compact.startsWith("00") ? `+${compact.slice(2)}` : compact;
  if (withPlus.includes("+") && !withPlus.startsWith("+")) return null;

  const digits = withPlus.replace(/\D/g, "");
  if (digits.length < 8 || digits.length > 15) return null;

  return `+${digits}`;
}

function validateLeadValues(values) {
  const errors = {};
  const cleanName = values.name.trim();
  const cleanEmail = values.email.trim();
  const normalizedPhone = normalizePhone(values.phone);

  if (cleanName.length < 2) {
    errors.name = "Please enter your full name (at least 2 characters).";
  }

  if (!normalizedPhone) {
    errors.phone = "Please enter a valid international phone number (e.g., +971...).";
  }

  if (!EMAIL_REGEX.test(cleanEmail)) {
    errors.email = "Please enter a valid email address.";
  }

  return { errors, normalizedPhone, cleanName, cleanEmail };
}

function buildWhatsAppPrefillText(lead = null) {
  const lines = [
    "Hi, I just submitted the consultation form and want to contact you immediately.",
  ];

  if (lead && lead.name) lines.push(`Name: ${lead.name}`);
  if (lead && lead.phone) lines.push(`Phone: ${lead.phone}`);
  if (lead && lead.email) lines.push(`Email: ${lead.email}`);

  return lines.join("\n");
}

function openWhatsApp(lead = null) {
  const text = buildWhatsAppPrefillText(lead);
  const url = `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(text)}`;
  window.open(url, "_blank", "noopener,noreferrer");
}

function trackCategoryClick(category, url, currentSessionId, currentUserId) {
  const payload = {
    event_name: "project_category_click",
    category,
    department: category,
    url,
    session_id: currentSessionId || null,
    user_id: currentUserId || null,
    source: "chatbot",
  };

  const endpoint = `${API_ROOT}/analytics/event`;

  try {
    if (navigator.sendBeacon) {
      const blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
      navigator.sendBeacon(endpoint, blob);
      return;
    }
  } catch (_err) {
    // Fire-and-forget: avoid blocking link opening.
  }

  fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {
    // Fire-and-forget: ignore network errors.
  });
}

function createButtonComponent({ label, variant = "default", href = null, onClick = null }) {
  const el = href ? document.createElement("a") : document.createElement("button");
  el.className = `btn ${variant === "primary" ? "btnPrimary" : ""} ${href ? "btnLink" : ""}`.trim();
  el.textContent = label;

  if (href) {
    el.href = href;
    el.target = "_blank";
    el.rel = "noopener noreferrer";
    if (onClick) {
      el.addEventListener("click", onClick);
    }
  } else {
    el.type = "button";
    el.onclick = onClick;
  }

  return el;
}

function appendInlineMarkdown(parent, rawText) {
  const text = String(rawText || "");
  const re = /\*\*(.+?)\*\*/g;
  let last = 0;
  let match = re.exec(text);

  while (match) {
    if (match.index > last) {
      parent.appendChild(document.createTextNode(text.slice(last, match.index)));
    }
    const strong = document.createElement("strong");
    strong.textContent = match[1];
    parent.appendChild(strong);
    last = match.index + match[0].length;
    match = re.exec(text);
  }

  if (last < text.length) {
    parent.appendChild(document.createTextNode(text.slice(last)));
  }
}

function renderMarkdownFragment(markdownText) {
  const fragment = document.createDocumentFragment();
  const lines = String(markdownText || "").replace(/\r\n/g, "\n").split("\n");
  let listEl = null;
  let titleSet = false;

  const flushList = () => {
    if (listEl) {
      fragment.appendChild(listEl);
      listEl = null;
    }
  };

  lines.forEach(rawLine => {
    const line = rawLine.trim();
    if (!line) {
      flushList();
      return;
    }

    if (!titleSet && !line.startsWith("- ") && !line.startsWith("* ") && !/^(\*\*)?key highlights(\*\*)?$/i.test(line)) {
      flushList();
      const title = document.createElement("div");
      title.className = "msgTitle";
      appendInlineMarkdown(title, line.replace(/^#{1,6}\s*/, ""));
      fragment.appendChild(title);
      titleSet = true;
      return;
    }

    if (line.startsWith("### ")) {
      flushList();
      const h3 = document.createElement("h3");
      appendInlineMarkdown(h3, line.slice(4));
      fragment.appendChild(h3);
      return;
    }

    if (/^(\*\*)?key highlights(\*\*)?$/i.test(line)) {
      flushList();
      const section = document.createElement("h3");
      section.className = "msgSectionTitle";
      section.textContent = "Key highlights";
      fragment.appendChild(section);
      return;
    }

    if (line.startsWith("- ")) {
      if (!listEl) {
        listEl = document.createElement("ul");
      }
      const li = document.createElement("li");
      appendInlineMarkdown(li, line.slice(2));
      listEl.appendChild(li);
      return;
    }

    flushList();
    const p = document.createElement("p");
    appendInlineMarkdown(p, line);
    fragment.appendChild(p);
  });

  flushList();
  return fragment;
}

function extractFollowUpQuestions(text) {
  const lines = String(text || "").split("\n");
  const questions = [];
  let inSection = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      if (inSection) break;
      continue;
    }
    if (/^follow-up questions?:/i.test(line)) {
      inSection = true;
      const inline = line.replace(/^follow-up questions?:/i, "").trim();
      if (inline) questions.push(inline);
      continue;
    }
    if (inSection) {
      if (/^[-*•]/.test(line)) {
        questions.push(line.replace(/^[-*•]\s*/, "").trim());
        continue;
      }
      break;
    }
    if (/^follow-up question:/i.test(line)) {
      questions.push(line.replace(/^follow-up question:/i, "").trim());
    }
  }
  return questions.filter(Boolean).slice(0, 1);
}

function stripFollowUpLine(text) {
  const lines = String(text || "").split("\n");
  const out = [];
  let skipping = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (/^follow-up questions?:/i.test(line)) {
      skipping = true;
      continue;
    }
    if (skipping) {
      if (/^[-*•]/.test(line) || !line) continue;
      skipping = false;
    }
    if (/^follow-up question:/i.test(line)) continue;
    out.push(raw);
  }
  return out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function extractRagContextUrls(sources) {
  if (!Array.isArray(sources)) return [];
  const urls = sources
    .map(source => {
      if (typeof source === "string") return source.trim();
      if (source && typeof source === "object" && typeof source.url === "string") return source.url.trim();
      return "";
    })
    .filter(Boolean);
  return [...new Set(urls)].slice(0, 12);
}

function createMessageComponent({
  role = "bot",
  text = "",
  buttons = [],
  isMarkdown = false,
  followUpQuestions = [],
  followUpButtons = [],
}) {
  const wrapper = document.createElement("div");
  wrapper.className = `msg ${role}`;

  if (text) {
    const textEl = document.createElement("div");
    textEl.className = "msgText";
    if (role === "bot" && isMarkdown) {
      textEl.classList.add("msgMarkdown");
      textEl.appendChild(renderMarkdownFragment(text));
    } else {
      textEl.textContent = text;
    }
    wrapper.appendChild(textEl);
  }

  if (role === "bot" && isMarkdown) {
    const rawButtons = Array.isArray(followUpButtons) ? followUpButtons : [];
    const rawQuestions = Array.isArray(followUpQuestions) ? followUpQuestions : [];
    const followUps = rawButtons.length > 0 ? rawButtons : rawQuestions;
    const unique = [];
    const seen = new Set();
    followUps.forEach(textValue => {
      const clean = String(textValue || "").trim();
      if (!clean || seen.has(clean)) return;
      seen.add(clean);
      unique.push(clean);
    });
    unique.slice(0, 3).forEach(followUpText => {
      const clean = String(followUpText || "").trim();
      if (!clean) return;
      const followUpBtn = document.createElement("button");
      followUpBtn.type = "button";
      followUpBtn.className = "btn followUpBtn";
      followUpBtn.textContent = clean;
      followUpBtn.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        sendUserText(clean, {
          source: "followup",
          forceIntent: "knowledge",
          includeRagContext: true,
        }).catch(() => {
          addMessage("Something went wrong. Please try again.", "error");
        });
      });
      wrapper.appendChild(followUpBtn);
    });
  }

  if (buttons.length > 0) {
    const actions = document.createElement("div");
    actions.className = "msgActions";

    buttons.forEach(button => {
      actions.appendChild(createButtonComponent({ label: button.label, href: button.url, variant: "primary" }));
    });

    wrapper.appendChild(actions);
  }

  return wrapper;
}

function createDropdownComponent({ name, value, options, onChange, hasError }) {
  const select = document.createElement("select");
  select.name = name;
  if (hasError) {
    select.classList.add("leadInputError");
  }

  const firstOption = document.createElement("option");
  firstOption.value = "";
  firstOption.textContent = "Select consultant type (optional)";
  select.appendChild(firstOption);

  options.forEach(optionText => {
    const option = document.createElement("option");
    option.value = optionText;
    option.textContent = optionText;
    if (value === optionText) {
      option.selected = true;
    }
    select.appendChild(option);
  });

  select.addEventListener("change", event => onChange(event.target.value));
  return select;
}

function createLeadFormFieldComponent({ label, input, errorText }) {
  const field = document.createElement("div");
  field.className = "leadField";

  const labelEl = document.createElement("label");
  labelEl.className = "leadLabel";
  labelEl.textContent = label;

  field.appendChild(labelEl);
  field.appendChild(input);

  if (errorText) {
    const error = document.createElement("div");
    error.className = "leadError";
    error.textContent = errorText;
    field.appendChild(error);
  }

  return field;
}

function createProjectCategoryCardComponent({ title, imageUrl, link }) {
  const card = document.createElement("article");
  card.className = "projectCard";

  const thumbFrame = document.createElement("div");
  thumbFrame.className = "projectThumbFrame";

  const thumb = document.createElement("img");
  thumb.className = "projectThumb";
  thumb.src = imageUrl || PROJECT_THUMB_PLACEHOLDER;
  thumb.alt = `${title} projects thumbnail`;
  thumb.loading = "lazy";
  thumb.decoding = "async";

  const body = document.createElement("div");
  body.className = "projectBody";

  const titleEl = document.createElement("div");
  titleEl.className = "projectTitle";
  titleEl.textContent = title;

  const cta = createButtonComponent({
    label: `View ${title} Projects`,
    href: link,
    variant: "primary",
    onClick: () => trackCategoryClick(title, link, sessionId, CHAT_USER_ID),
  });
  cta.classList.add("projectCta");

  body.appendChild(titleEl);
  body.appendChild(cta);
  thumbFrame.appendChild(thumb);
  card.appendChild(thumbFrame);
  card.appendChild(body);
  return card;
}

function getCategoryImageSources(categoryKey) {
  return [
    `${THUMBS_BASE_PATH}/${categoryKey}.jpg`,
    `${THUMBS_BASE_PATH}/${categoryKey}.webp`,
  ];
}

function attachThumbWithFallback(thumb, thumbFrame, categoryKey) {
  const sources = getCategoryImageSources(categoryKey);
  let index = 0;

  const loadCurrent = () => {
    thumb.src = sources[index];
  };

  thumb.onerror = () => {
    index += 1;
    if (index < sources.length) {
      loadCurrent();
      return;
    }

    thumbFrame.classList.add("projectThumbFallback");
    thumb.remove();
  };

  loadCurrent();
}

function isProjectCategoryButton(button) {
  return projectCategories.some(category => category.id === button.id);
}

function renderProjectCategoryCards(buttons) {
  const wrapper = document.createElement("div");
  wrapper.className = "projectCards";

  buttons.forEach(button => {
    const category = projectCategories.find(item => item.id === button.id);
    if (!category) return;

    wrapper.appendChild(
      createProjectCategoryCardComponent({
        title: category.title || button.label,
        imageUrl: null,
        link: category.link || PROJECTS_BASE_LINK,
      }),
    );

    const latestCard = wrapper.lastElementChild;
    if (!latestCard) return;
    const thumbFrame = latestCard.querySelector(".projectThumbFrame");
    const thumb = latestCard.querySelector(".projectThumb");
    if (!thumbFrame || !thumb) return;
    const categoryKey = category.imageKey || category.id;
    attachThumbWithFallback(thumb, thumbFrame, categoryKey);
  });

  const consultCta = createButtonComponent({
    label: "Request a consultation",
    variant: "primary",
    onClick: () => {
      showConsultationForm();
    },
  });
  consultCta.classList.add("projectMenuConsultCta");
  consultCta.setAttribute("aria-label", "Request a consultation");
  wrapper.appendChild(consultCta);

  buttonsEl.appendChild(wrapper);
}

function createLeadPostSubmitComponent() {
  const card = document.createElement("div");
  card.className = "leadForm leadSubmitCard";
  card.id = "consultation";

  const title = document.createElement("div");
  title.className = "leadFormTitle";
  title.textContent = "Submitted ✅";
  card.appendChild(title);

  const subtitle = document.createElement("div");
  subtitle.className = "leadSubmitSubtitle";
  subtitle.textContent = "Want to contact immediately?";
  card.appendChild(subtitle);

  const action = createButtonComponent({
    label: "Open WhatsApp",
    variant: "primary",
    onClick: () => openWhatsApp(leadFormState.submittedLead),
  });
  action.classList.add("leadSubmitWhatsAppCta");
  action.setAttribute("aria-label", "Open WhatsApp chat");
  card.appendChild(action);

  return card;
}

function createLeadFormComponent() {
  if (leadFormState.submitted) {
    return createLeadPostSubmitComponent();
  }

  const card = document.createElement("div");
  card.className = "leadForm";
  card.id = "consultation";

  const title = document.createElement("div");
  title.className = "leadFormTitle";
  title.textContent = "Request a consultant";
  card.appendChild(title);

  const grid = document.createElement("div");
  grid.className = "leadGrid";

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.placeholder = "Full name";
  nameInput.value = leadFormState.values.name;
  if (leadFormState.errors.name) {
    nameInput.classList.add("leadInputError");
  }
  nameInput.addEventListener("input", event => {
    leadFormState.values.name = event.target.value;
    delete leadFormState.errors.name;
  });

  const phoneInput = document.createElement("input");
  phoneInput.type = "tel";
  phoneInput.placeholder = "+971...";
  phoneInput.value = leadFormState.values.phone;
  if (leadFormState.errors.phone) {
    phoneInput.classList.add("leadInputError");
  }
  phoneInput.addEventListener("input", event => {
    leadFormState.values.phone = event.target.value;
    delete leadFormState.errors.phone;
  });

  const emailInput = document.createElement("input");
  emailInput.type = "email";
  emailInput.placeholder = "name@example.com";
  emailInput.value = leadFormState.values.email;
  if (leadFormState.errors.email) {
    emailInput.classList.add("leadInputError");
  }
  emailInput.addEventListener("input", event => {
    leadFormState.values.email = event.target.value;
    delete leadFormState.errors.email;
  });

  const consultantDropdown = createDropdownComponent({
    name: "consultant_type",
    value: leadFormState.values.consultant_type,
    options: CONSULTANT_TYPES,
    hasError: false,
    onChange: value => {
      leadFormState.values.consultant_type = value;
    },
  });

  grid.appendChild(createLeadFormFieldComponent({ label: "Full name *", input: nameInput, errorText: leadFormState.errors.name }));
  grid.appendChild(createLeadFormFieldComponent({ label: "Phone / WhatsApp *", input: phoneInput, errorText: leadFormState.errors.phone }));
  grid.appendChild(createLeadFormFieldComponent({ label: "Email *", input: emailInput, errorText: leadFormState.errors.email }));
  grid.appendChild(createLeadFormFieldComponent({ label: "Consultant type", input: consultantDropdown, errorText: "" }));

  card.appendChild(grid);

  const actions = document.createElement("div");
  actions.className = "leadActions";

  const cancelBtn = createButtonComponent({
    label: "Cancel",
    onClick: () => {
      leadFormState.submitted = false;
      leadFormState.submittedLead = null;
      leadFormHostEl.innerHTML = "";
      const buttons = buttonsEl.querySelectorAll("button");
      buttons.forEach(btn => {
        btn.disabled = false;
        btn.classList.remove("is-loading");
      });
    },
  });

  const submitBtn = createButtonComponent({ label: "Submit", variant: "primary" });
  submitBtn.disabled = leadFormState.isSubmitting;
  if (leadFormState.isSubmitting) {
    submitBtn.classList.add("is-loading");
  }

  submitBtn.onclick = async () => {
    leadFormState.submitError = "";
    const validation = validateLeadValues(leadFormState.values);
    leadFormState.errors = validation.errors;

    if (Object.keys(leadFormState.errors).length > 0) {
      renderLeadForm();
      return;
    }

    leadFormState.isSubmitting = true;
    renderLeadForm();

    try {
      const res = await fetch(`${API_ROOT}/consultation/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: validation.cleanName,
          phone: validation.normalizedPhone,
          email: validation.cleanEmail,
          consultant_type: leadFormState.values.consultant_type || null,
          source: "chatbot",
          session_id: sessionId,
        }),
      });
      const body = await res.json().catch(() => null);

      if (!res.ok || (body && body.ok === false)) {
        throw new Error(`Lead API returned ${res.status}`);
      }

      addMessage("Thanks! Our team will contact you soon.", "bot");
      leadFormState.submittedLead = {
        name: validation.cleanName,
        phone: validation.normalizedPhone,
        email: validation.cleanEmail,
      };
      leadFormState.values = { name: "", phone: "", email: "", consultant_type: "" };
      leadFormState.errors = {};
      leadFormState.submitError = "";
      leadFormState.isSubmitting = false;
      leadFormState.submitted = true;
      renderLeadForm();
    } catch (_err) {
      leadFormState.submitted = false;
      leadFormState.isSubmitting = false;
      leadFormState.submitError = "Could not submit now. Please try again in a moment.";
      renderLeadForm();
    }
  };

  actions.appendChild(cancelBtn);
  actions.appendChild(submitBtn);
  card.appendChild(actions);

  if (leadFormState.submitError) {
    const status = document.createElement("div");
    status.className = "leadStatus";
    status.textContent = leadFormState.submitError;
    card.appendChild(status);
  }

  return card;
}

function showConsultationForm() {
  leadFormState.submitted = false;
  leadFormState.submittedLead = null;
  renderLeadForm();
}

function renderLeadForm() {
  leadFormHostEl.innerHTML = "";
  leadFormHostEl.appendChild(createLeadFormComponent());
  const consultationEl = document.getElementById("consultation");
  if (consultationEl && typeof consultationEl.scrollIntoView === "function") {
    consultationEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  scrollToLatest();
}

function extractProjectId(url) {
  try {
    const parsed = new URL(url);
    if (!parsed.pathname.endsWith("project-detail.php")) return "";
    const id = parsed.searchParams.get("id") || "";
    return /^\d+$/.test(id) ? id : "";
  } catch {
    return "";
  }
}

function sourceTitleFromUrl(url) {
  const projectId = extractProjectId(url);
  if (projectId) {
    return `Villa Project #${projectId}`;
  }
  return "OBE Project";
}

function normalizeSourceEntry(source) {
  if (typeof source === "string") {
    const url = source.trim();
    return url
      ? { url, title: "OBE Source", location: null, status: null, size: null, overview: "", isLegacy: true }
      : null;
  }

  if (!source || typeof source !== "object") return null;
  const url = typeof source.url === "string" ? source.url.trim() : "";
  if (!url) return null;

  const rawTitle = typeof source.title === "string" ? source.title.trim() : "";
  const rawOverview = typeof source.overview === "string"
    ? source.overview.trim()
    : (typeof source.blurb === "string"
      ? source.blurb.trim()
      : (typeof source.summary === "string" ? source.summary.trim() : ""));

  return {
    url,
    title: rawTitle || sourceTitleFromUrl(url),
    location: typeof source.location === "string" && source.location.trim() ? source.location.trim() : null,
    status: typeof source.status === "string" && source.status.trim() ? source.status.trim() : null,
    size: typeof source.size === "string" && source.size.trim() ? source.size.trim() : null,
    overview: rawOverview,
    isLegacy: false,
  };
}

function addMessage(text, role = "bot", options = {}) {
  const { isMarkdown = false, followUpQuestions = [], followUpButtons = [] } = options;
  const structured = role === "bot" ? buildStructuredMessage(text) : { text, buttons: [] };
  const renderedText = role === "bot" && isMarkdown ? text : structured.text;
  const renderedButtons = role === "bot" && isMarkdown ? [] : structured.buttons;
  messagesEl.appendChild(createMessageComponent({
    role,
    text: renderedText,
    buttons: renderedButtons,
    isMarkdown,
    followUpQuestions,
    followUpButtons,
  }));
  scrollToLatest();
}

function renderRagDetails({ sources = [] }) {
  if (!Array.isArray(sources) || sources.length === 0) {
    return;
  }
  const normalizedSources = sources
    .map(normalizeSourceEntry)
    .filter(Boolean);
  if (normalizedSources.length === 0) return;

  const wrapper = document.createElement("div");
  wrapper.className = "msg bot ragMeta";
  const details = document.createElement("details");
  details.className = "ragSources";

  const summary = document.createElement("summary");
  summary.textContent = `Related projects (${normalizedSources.length})`;
  details.appendChild(summary);

  const cards = document.createElement("div");
  cards.className = "ragSourceCards";

  normalizedSources.forEach(source => {
    const card = document.createElement("article");
    card.className = "ragSourceCard";

    const title = document.createElement("div");
    title.className = "ragSourceTitle";
    title.textContent = source.title || "OBE Source";
    card.appendChild(title);

    const meta = [source.location, source.status, source.size].filter(Boolean);
    if (meta.length > 0) {
      const metaRow = document.createElement("div");
      metaRow.className = "ragSourceMeta";
      metaRow.textContent = meta.join(" • ");
      card.appendChild(metaRow);
    }

    if (source.overview) {
      const overviewText = document.createElement("div");
      overviewText.className = "ragSourceOverview";
      overviewText.textContent = source.overview;
      card.appendChild(overviewText);
    }

    if (!source.title && !source.overview) {
      const rawUrl = document.createElement("div");
      rawUrl.className = "ragSourceUrl";
      rawUrl.textContent = source.url;
      card.appendChild(rawUrl);
    }

    const link = document.createElement("a");
    link.className = "ragSourceLink";
    link.href = source.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "View project \u2192";
    card.appendChild(link);

    cards.appendChild(card);
  });

  details.appendChild(cards);
  wrapper.appendChild(details);

  messagesEl.appendChild(wrapper);
  scrollToLatest();
}

function detectIntent(text) {
  const normalized = (text || "").trim().toLowerCase();
  if (!normalized) return "knowledge";

  const strongLeadKeywords = LEAD_INTENT_KEYWORDS.filter(keyword => !["area", "location", "timeline", "timeframe"].includes(keyword));
  const weakLeadKeywords = ["area", "location", "timeline", "timeframe"];
  const leadContextHints = ["quote", "budget", "cost", "price", "consultation", "meeting", "start project", "start a project", "hire", "contact", "call", "phone", "my name is", "my phone", "my email"];

  const strongMatch = strongLeadKeywords.some(keyword => normalized.includes(keyword));
  const weakMatch = weakLeadKeywords.some(keyword => normalized.includes(keyword));
  const hasLeadContext = leadContextHints.some(keyword => normalized.includes(keyword));
  const isLikelyQuestion = /(^|\s)(what|which|how|tell me|do you|can you|is there|are there)\b/.test(normalized) || normalized.includes("?");

  if (strongMatch) return "lead";
  if (weakMatch && hasLeadContext && !isLikelyQuestion) return "lead";

  return "knowledge";
}

function normalizeCategory(text) {
  const normalized = String(text || "").toLowerCase();
  if (!normalized) return null;
  if (normalized.includes("public") && (normalized.includes("cultural") || normalized.includes("culture"))) return "public-and-cultural";
  if (normalized.includes("villas") || normalized.includes("villa projects")) return "villas";
  if (normalized.includes("commercial")) return "commercial";
  if (normalized.includes("sports") || normalized.includes("sport")) return "sports";
  if (normalized.includes("education") || normalized.includes("educational")) return "education";
  if (normalized.includes("mosques") || normalized.includes("mosque")) return "mosques";
  return null;
}

function categoryTitle(categorySlug) {
  switch (categorySlug) {
    case "villas":
      return "Villas Designed by OBE Architects";
    case "commercial":
      return "Commercial Projects by OBE Architects";
    case "sports":
      return "Sports Facilities Designed by OBE Architects";
    case "education":
      return "Education Projects by OBE Architects";
    case "mosques":
      return "Mosques Designed by OBE Architects";
    case "public-and-cultural":
      return "Public & Cultural Projects by OBE Architects";
    default:
      return "OBE Projects by OBE Architects";
  }
}

function buildCategoryFallback(categorySlug) {
  return [
    categoryTitle(categorySlug),
    "",
    "KEY HIGHLIGHTS",
    "- **Note:** Not enough portfolio text was retrieved for this category.",
    "- **Try:** Ask about a specific project name or choose a department.",
  ].join("\n");
}

function setComposerDisabled(disabled) {
  if (chatInputEl) {
    chatInputEl.disabled = disabled;
  }
  if (chatSendBtnEl) {
    chatSendBtnEl.disabled = disabled;
  }
}

function showTypingIndicator() {
  if (typingEl) return;

  typingEl = document.createElement("div");
  typingEl.className = "msg typing";
  typingEl.innerHTML = 'Typing<div class="typingDots"><span></span><span></span><span></span></div>';
  messagesEl.appendChild(typingEl);
  scrollToLatest();
}

function hideTypingIndicator() {
  if (!typingEl) return;
  typingEl.remove();
  typingEl = null;
}

function disableOptionButtons(clickedButton) {
  const allButtons = buttonsEl.querySelectorAll("button");
  allButtons.forEach(btn => {
    btn.disabled = true;
  });

  if (clickedButton) {
    clickedButton.classList.add("is-loading");
  }
}

function shouldIncludeLastRagContext({ source = "input", includeRagContext = false }) {
  if (includeRagContext) return true;
  if (source === "followup") return true;
  if (!chatUiState.lastRagAt) return false;
  const elapsedMs = Date.now() - chatUiState.lastRagAt;
  return elapsedMs <= 5 * 60 * 1000;
}

async function requestRagAnswer(question, { source = "input", includeRagContext = false } = {}) {
  const useContextUrls = includeRagContext || source === "followup";
  const contextUrls = useContextUrls
    ? extractRagContextUrls(chatUiState.lastRagSources)
    : [];

  const payload = {
    user_id: CHAT_USER_ID,
    question,
  };
  if (sessionId) {
    payload.session_id = sessionId;
  }
  if (chatUiState.followUpCount) {
    payload.follow_up_count = chatUiState.followUpCount;
  }
  if (contextUrls.length > 0) {
    payload.context_urls = contextUrls;
    payload.use_context_urls = true;
  }

  const res = await fetch(`${API_ROOT}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.status === 404 || res.status === 502 || res.status === 503) {
    addMessage("Knowledge answers are temporarily unavailable. Please try again or use the menu options.", "bot");
    return;
  }
  if (!res.ok) {
    addMessage("Knowledge answers are temporarily unavailable. Please try again or use the menu options.", "bot");
    return;
  }

  const out = await res.json();
  const normalizedCategory = normalizeCategory(question);
  let answer = typeof out.answer === "string" && out.answer.trim()
    ? out.answer.trim()
    : "";
  if (!answer && normalizedCategory) {
    answer = buildCategoryFallback(normalizedCategory);
  }
  if (normalizedCategory && /^i don't know based on the available sources\.?$/i.test(answer)) {
    answer = buildCategoryFallback(normalizedCategory);
  }
  if (!answer) {
    answer = "I don't have enough portfolio content to answer that precisely.";
  }
  const followUpButtons = Array.isArray(out.follow_up_buttons)
    ? out.follow_up_buttons.map(btn => String(btn || "").trim()).filter(Boolean)
    : [];
  const followUpQuestions = followUpButtons.length > 0 ? [] : extractFollowUpQuestions(answer);
  const displayAnswer = stripFollowUpLine(answer);
  const markdownFormat = out.answer_format === "markdown" || /(^|\n)(###\s+|- )/.test(answer);
  addMessage(displayAnswer, "bot", {
    isMarkdown: markdownFormat,
    followUpQuestions,
    followUpButtons,
  });
  if (followUpButtons.length > 0 || followUpQuestions.length > 0) {
    chatUiState.followUpCount += 1;
  }
  renderRagDetails({
    sources: Array.isArray(out.sources) ? out.sources : [],
  });

  chatUiState.lastRagSources = Array.isArray(out.sources) ? out.sources : [];
  chatUiState.lastRagAt = Date.now();
  const firstLine = displayAnswer.split("\n").map(line => line.trim()).find(Boolean) || "";
  chatUiState.lastRagTopic = firstLine.replace(/^#{1,6}\s*/, "");
}

async function sendGuidedMessage({ text, buttonId }) {
  const res = await fetch(`${API_ROOT}/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      channel: "web",
      user_id: CHAT_USER_ID,
      session_id: sessionId,
      text,
      button_id: buttonId,
    }),
  });

  if (!res.ok) {
    throw new Error(`API returned ${res.status}`);
  }

  const out = await res.json();
  if (out && out.session_id) {
    sessionId = out.session_id;
    chatUiState.followUpCount = 0;
  }
  renderChatUi(out);
}

async function sendUserText(
  text,
  { source = "input", forceIntent = null, guidedButtonId = null, includeRagContext = false } = {},
) {
  const cleanText = (text || "").trim();
  if (!cleanText || chatUiState.isSending) return;

  chatUiState.isSending = true;
  setComposerDisabled(true);
  addMessage(cleanText, "user");
  showTypingIndicator();

  try {
    if (guidedButtonId) {
      await sendGuidedMessage({ text: null, buttonId: guidedButtonId });
      return;
    }

    const resolvedIntent = forceIntent || detectIntent(cleanText);
    if (resolvedIntent === "lead") {
      await sendGuidedMessage({ text: cleanText, buttonId: null });
      return;
    }

    await requestRagAnswer(cleanText, { source, includeRagContext });
  } catch (_err) {
    addMessage("Network error. Please try again.", "error");
  } finally {
    hideTypingIndicator();
    setComposerDisabled(false);
    chatUiState.isSending = false;
  }
}

/*
Manual smoke checks:
1) Type a knowledge question -> POST /api/chat/ask.
2) Type a lead-intent message -> POST /api/chat/message.
3) Click guided menu buttons -> POST /api/chat/message.
4) Scroll long chat and confirm the input stays visible.
*/
async function submitComposerText() {
  const text = chatInputEl ? chatInputEl.value.trim() : "";
  if (!text) return;
  if (chatInputEl) {
    chatInputEl.value = "";
  }
  await sendUserText(text, { source: "input" });
}

function renderOptionButtons(buttons = []) {
  buttonsEl.innerHTML = "";

  const projectButtons = buttons.filter(isProjectCategoryButton);
  const nonProjectButtons = buttons.filter(button => !isProjectCategoryButton(button));

  if (projectButtons.length > 0) {
    renderProjectCategoryCards(projectButtons);
  }

  nonProjectButtons.forEach(button => {
    const option = createButtonComponent({
      label: button.label,
      onClick: async () => {
        if (button.id === "consult") {
          disableOptionButtons(option);
          await new Promise(resolve => setTimeout(resolve, 300));
          option.classList.remove("is-loading");
          addMessage(button.label, "user");
          showConsultationForm();
          return;
        }

        leadFormHostEl.innerHTML = "";
        disableOptionButtons(option);
        await sendUserText(button.label, {
          source: "guided_button",
          guidedButtonId: button.id,
        });
      },
    });

    buttonsEl.appendChild(option);
  });
}

function renderLegacyForm(out) {
  formEl.innerHTML = "";
  if (!out.form) return;

  const note = document.createElement("div");
  note.className = "formLabel";
  note.textContent = "Please use Request a Consultation to submit your details.";
  formEl.appendChild(note);
}

function renderMessages(messages = []) {
  messages.forEach(message => {
    addMessage(message.text, "bot");
  });
}

function renderChatUi(out) {
  renderMessages(out.messages || []);
  renderOptionButtons(out.buttons || []);
  renderLegacyForm(out);
  scrollToLatest();
}
