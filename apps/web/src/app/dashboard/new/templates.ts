// Templates from PLAN 2.1; only the ones the runner supports today are selectable.
// Tool ids match NAT function types where one exists (agents/simple-agent/workflow.yml).
export const templates = [
  {
    id: "personal", name: "Personal automation", desc: "Email triage, calendar, reminders, daily brief.", tools: "Gmail, Calendar, Sheets, Drive, web search", ready: true,
    instructions: "You help me stay on top of my day. Summarise what matters, draft replies for me to review, and never send or delete anything without asking.",
    toolset: [
      { id: "current_datetime", desc: "Read the current date and time", tier: 0, on: true },
      { id: "gmail_read", desc: "Read your email", tier: 0, on: true },
      { id: "gmail_draft", desc: "Draft replies (you send them)", tier: 1, on: true },
      { id: "calendar_read", desc: "Read your calendar", tier: 0, on: true },
      { id: "calendar_write", desc: "Create and move events", tier: 2, on: false },
      { id: "web_search", desc: "Search the web", tier: 0, on: false },
    ],
  },
  {
    id: "research", name: "Research / analyst", desc: "Search the web and your documents, write up findings.", tools: "Web search, fetch, doc writer", ready: true,
    instructions: "You research questions using your tools, cite every source you use, and say plainly when you could not find an answer.",
    toolset: [
      { id: "current_datetime", desc: "Read the current date and time", tier: 0, on: true },
      { id: "wiki_search", desc: "Search Wikipedia", tier: 0, on: true },
      { id: "web_search", desc: "Search the web", tier: 0, on: true },
      { id: "web_fetch", desc: "Open and read a web page", tier: 0, on: true },
      { id: "doc_write", desc: "Write a report document", tier: 1, on: false },
    ],
  },
  { id: "support", name: "Customer support", desc: "Answer customers from your knowledge base and orders.", tools: "KB search, ticketing, order lookup, draft reply", ready: false },
  { id: "ops", name: "Ops / workflow", desc: "Keep sheets, forms and helpdesk queues moving.", tools: "Sheets, forms, helpdesk", ready: false },
  { id: "sales", name: "Sales / SDR", desc: "Research leads and draft outreach.", tools: "CRM, enrichment, email drafts", ready: false },
  { id: "recruiting", name: "Recruiting", desc: "Parse resumes, build shortlists, schedule interviews.", tools: "Resume parsing, candidate profile, scheduling", ready: false },
  { id: "voice", name: "Caller agent (voice)", desc: "Answer and place phone calls.", tools: "Speech, telephony, calendar, CRM", ready: false },
];
