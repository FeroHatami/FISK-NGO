const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5000";

/** Wrapper around fetch that always includes credentials for session cookies. */
function apiFetch(url: string, init?: RequestInit): Promise<Response> {
  return fetch(url, { ...init, credentials: "include" });
}

export interface FetchItemsParams {
  type?: string;
  region?: string;
  priority?: string;
}

export async function fetchItems(params?: FetchItemsParams) {
  const url = new URL("/api/items", BASE);
  if (params?.type) url.searchParams.set("type", params.type);
  if (params?.region) url.searchParams.set("region", params.region);
  if (params?.priority) url.searchParams.set("priority", params.priority);

  const res = await apiFetch(url.toString());
  if (!res.ok) throw new Error(`Failed to fetch items: ${res.status}`);
  return res.json();
}

export interface MetaResponse {
  topics: string[];
  regions: string[];
  typeLabels: Record<string, string>;
}

export async function fetchMeta(): Promise<MetaResponse> {
  const res = await apiFetch(`${BASE}/api/meta`);
  if (!res.ok) throw new Error(`Failed to fetch meta: ${res.status}`);
  return res.json();
}

export interface BriefingHighlight {
  id: string;
  title: string;
  summary: string;
  title_de?: string;
  summary_de?: string;
}

export interface BriefingResponse {
  date: string | null;
  summary_en: string;
  summary_de: string;
  highlights: BriefingHighlight[];
  stats: { reviewed: number; newOvernight: number };
}

export async function fetchBriefing(): Promise<BriefingResponse> {
  const res = await apiFetch(`${BASE}/api/briefing`);
  if (!res.ok) throw new Error(`Failed to fetch briefing: ${res.status}`);
  return res.json();
}

export interface FundingMatch {
  id: string;
  title: string;
  summary: string;
  matchReason: string;
  amount?: string | null;
  deadline?: string | null;
  eligibility?: string | null;
  region?: string[];
  topic?: string[];
  source?: string;
  [key: string]: unknown;
}

export interface FundingSearchResponse {
  matches: FundingMatch[];
  error?: string;
}

export async function searchFunding(query: string): Promise<FundingSearchResponse> {
  const res = await apiFetch(`${BASE}/api/funding/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(`Funding search failed: ${res.status}`);
  return res.json();
}

export interface MarkerItem {
  id: string;
  title: string;
  type: string;
  urgency: string;
}

export interface MapMarkerData {
  name: string;
  lat: number;
  lng: number;
  urgency: string;
  count: number;
  items: MarkerItem[];
}

export async function fetchMarkers(): Promise<MapMarkerData[]> {
  const res = await apiFetch(`${BASE}/api/markers`);
  if (!res.ok) throw new Error(`Failed to fetch markers: ${res.status}`);
  return res.json();
}

export interface Insight {
  label: string;
  title_en: string;
  title_de: string;
  description_en: string;
  description_de: string;
  item_ids: string[];
}

export interface InsightsResponse {
  insights: Insight[];
  error?: string;
}

export async function fetchInsights(): Promise<InsightsResponse> {
  const res = await apiFetch(`${BASE}/api/insights`);
  if (!res.ok) throw new Error(`Failed to fetch insights: ${res.status}`);
  return res.json();
}

export interface EmailDraft {
  subject: string;
  body: string;
  suggested_recipients: string[];
  error?: string;
}

export async function draftEmail(message: string, language?: string): Promise<EmailDraft> {
  const res = await apiFetch(`${BASE}/api/copilot/draft-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, language: language || "en" }),
  });
  if (!res.ok) throw new Error(`Draft email failed: ${res.status}`);
  return res.json();
}

export interface SendEmailPayload {
  to: string[];
  subject: string;
  body: string;
  confirmed: true;
}

export interface SendEmailResponse {
  success: boolean;
  message?: string;
  error?: string;
}

export async function sendEmail(payload: SendEmailPayload): Promise<SendEmailResponse> {
  const res = await apiFetch(`${BASE}/api/send-email`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function searchItems(query: string): Promise<unknown[]> {
  if (!query.trim()) return [];
  const res = await apiFetch(`${BASE}/api/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) return [];
  return res.json();
}

export async function login(password: string): Promise<{ success: boolean; error?: string }> {
  const res = await apiFetch(`${BASE}/api/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ password }),
  });
  return res.json();
}

export async function logout(): Promise<void> {
  await apiFetch(`${BASE}/api/logout`, { method: "POST", credentials: "include" });
}
