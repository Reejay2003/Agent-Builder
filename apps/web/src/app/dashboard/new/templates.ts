// Templates from PLAN 2.1; only the ones the runner supports today are selectable.
// `recommended` are tool ids from the SDK's catalog (GET /tools), ticked by default in the Tools step.
export const templates = [
  {
    id: "personal", name: "Personal automation", desc: "Email triage, calendar, reminders, daily brief.", tools: "Gmail, Calendar, Sheets, Drive, web search", ready: true,
    instructions: "You help me stay on top of my day. Summarise what matters, draft replies for me to review, and never send or delete anything without asking.",
    recommended: ["gmail.read", "gmail.send_draft", "calendar.list_events"],
  },
  {
    id: "research", name: "Research / analyst", desc: "Search the web and your documents, write up findings.", tools: "Web search, fetch, doc writer", ready: true,
    instructions: "You research questions using your tools, cite every source you use, and say plainly when you could not find an answer.",
    recommended: ["web.search"],
  },
  { id: "support", name: "Customer support", desc: "Answer customers from your knowledge base and orders.", tools: "KB search, ticketing, order lookup, draft reply", ready: false },
  { id: "ops", name: "Ops / workflow", desc: "Keep sheets, forms and helpdesk queues moving.", tools: "Sheets, forms, helpdesk", ready: false },
  { id: "sales", name: "Sales / SDR", desc: "Research leads and draft outreach.", tools: "CRM, enrichment, email drafts", ready: false },
  { id: "recruiting", name: "Recruiting", desc: "Parse resumes, build shortlists, schedule interviews.", tools: "Resume parsing, candidate profile, scheduling", ready: false },
  { id: "voice", name: "Caller agent (voice)", desc: "Answer and place phone calls.", tools: "Speech, telephony, calendar, CRM", ready: false },
];
