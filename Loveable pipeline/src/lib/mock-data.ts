export type Priority = "high" | "med" | "low";
export type ItemType = "funding" | "news" | "email" | "report" | "alert";
export type Urgency = "now" | "today" | "this week" | "later";
export type TimeEstimate = "2 min" | "5 min" | "15 min" | "30 min" | "1h" | "2h";

export interface Item {
  id: string;
  priority: Priority;
  type: ItemType;
  title: string;
  title_de?: string;
  title_original?: string;
  source: string;
  date: string; // ISO
  topic: string[];
  region: string[];
  summary: string;
  suggestedAction: "Apply" | "Reply" | "Read" | "Monitor";
  urgency: Urgency;
  timeEstimate: TimeEstimate;
  translation?: string;
  translation_de?: string;
  original?: string;
  originalLanguage?: string;
  // funding
  deadline?: string;
  amount?: string;
  eligibility?: string;
  requirements?: string;
  fundingOrg?: string;
  // email
  sender?: string;
  // contacts
  contact_email?: string;
  contact_phone?: string;
  // link
  link?: string;
}

export const items: Item[] = [
  {
    id: "bmz-2026",
    priority: "high",
    urgency: "today",
    timeEstimate: "1h",
    type: "funding",
    title: "BMZ Call: Education & Youth in Sub-Saharan Africa",
    source: "BMZ — Engagement Global",
    date: "2026-06-25T07:14:00Z",
    topic: ["Education", "Children & Women's Rights"],
    region: ["Burundi", "East Africa"],
    summary:
      "New thematic call for proposals supporting basic education and vocational training. Burundi explicitly listed as priority country. Co-financing 25%, up to €450k over 3 years.",
    suggestedAction: "Apply",
    deadline: "2026-07-12",
    amount: "Up to €450,000",
    eligibility: "Registered German NGOs with ≥3 years field presence",
    requirements: "Logical framework, partner agreement, 25% co-financing",
    fundingOrg: "Bundesministerium für wirtschaftliche Zusammenarbeit (BMZ)",
    original:
      "Das BMZ schreibt im Rahmen der Initiative Bildung & Jugend einen neuen thematischen Förderaufruf aus...",
    translation:
      "BMZ announces a new thematic funding call within the Education & Youth initiative...",
  },
  {
    id: "burundi-partner-1",
    priority: "med",
    urgency: "today",
    timeEstimate: "15 min",
    type: "email",
    title: "Update from Bujumbura — school year preparation",
    source: "Inbox",
    sender: "Innocent Niyongabo <innocent@bk-partner.bi>",
    date: "2026-06-26T18:42:00Z",
    topic: ["Education"],
    region: ["Burundi"],
    originalLanguage: "French",
    original:
      "Chers amis, j'espère que vous allez bien. Nous préparons la rentrée scolaire. Nous avons besoin de votre confirmation pour la commande des manuels avant le 5 juillet...",
    translation:
      "Dear friends, I hope you are well. We are preparing for the new school year. We need your confirmation for the textbook order before July 5th...",
    summary:
      "Innocent requests confirmation on the textbook order (≈€2,400) before July 5 so printing can begin on schedule.",
    suggestedAction: "Reply",
  },
  {
    id: "burundi-politics",
    priority: "med",
    urgency: "this week",
    timeEstimate: "5 min",
    type: "news",
    title: "Burundi government reshuffles education ministry",
    source: "Deutsche Welle Afrique",
    date: "2026-06-26T05:30:00Z",
    topic: ["Politics", "Education"],
    region: ["Burundi"],
    summary:
      "New minister announced; signals continued focus on rural primary schools. Likely impact on partner registration timelines.",
    suggestedAction: "Monitor",
    original:
      "Le gouvernement burundais a annoncé un remaniement ministériel touchant le secteur de l'éducation...",
    translation:
      "The Burundian government announced a cabinet reshuffle affecting the education sector...",
  },
  {
    id: "unicef-report",
    priority: "low",
    urgency: "later",
    timeEstimate: "30 min",
    type: "report",
    title: "UNICEF: State of the World's Children 2026",
    source: "UNICEF",
    date: "2026-06-24T12:00:00Z",
    topic: ["Children & Women's Rights", "Health"],
    region: ["Global"],
    summary:
      "Annual flagship report. Key chapter on adolescent mental health in conflict-affected regions — relevant for upcoming grant narrative.",
    suggestedAction: "Read",
  },
  {
    id: "misereor-grant",
    priority: "med",
    urgency: "this week",
    timeEstimate: "2h",
    type: "funding",
    title: "Misereor — Women & Girls empowerment micro-grants",
    source: "Misereor",
    date: "2026-06-23T09:00:00Z",
    topic: ["Women & Girls", "Human Rights"],
    region: ["East Africa"],
    summary:
      "Rolling call. Grants €15k–€80k for community-based projects supporting women's economic participation.",
    suggestedAction: "Apply",
    deadline: "2026-09-30",
    amount: "€15,000 – €80,000",
    eligibility: "Local partner organizations, faith-based or secular",
    requirements: "Concept note (5 pages), partner letter, budget",
    fundingOrg: "Misereor e.V.",
  },
  {
    id: "wtg-investigation",
    priority: "high",
    urgency: "now",
    timeEstimate: "30 min",
    type: "alert",
    title: "Undercover footage: live transport violations at EU border",
    source: "Animal Welfare Network",
    date: "2026-06-26T22:10:00Z",
    topic: ["Animal Welfare Germany", "International Animal Welfare"],
    region: ["Germany", "Global"],
    summary:
      "New footage circulating on social media shows repeated violations at the Bulgarian-Turkish border. Press attention rising — potential statement opportunity.",
    suggestedAction: "Reply",
  },
  {
    id: "venro-event",
    priority: "low",
    urgency: "later",
    timeEstimate: "5 min",
    type: "news",
    title: "VENRO annual conference — registration open",
    source: "VENRO",
    date: "2026-06-22T08:00:00Z",
    topic: ["Humanitarian Aid"],
    region: ["Germany"],
    summary: "Early-bird until July 15. Panel on AI in humanitarian programming.",
    suggestedAction: "Monitor",
  },
  {
    id: "reliefweb-burundi",
    priority: "med",
    urgency: "this week",
    timeEstimate: "15 min",
    type: "report",
    title: "ReliefWeb: Burundi humanitarian snapshot — Q2",
    source: "ReliefWeb / OCHA",
    date: "2026-06-21T14:00:00Z",
    topic: ["Humanitarian Aid", "Health"],
    region: ["Burundi"],
    summary:
      "Cholera cases stabilizing; food insecurity worsening in Cibitoke. Useful data for grant narratives.",
    suggestedAction: "Read",
  },
];

export const briefStats = {
  reviewed: 124,
  newOvernight: 18,
};

export const ALL_TOPICS = [
  "Education",
  "Health",
  "Women & Girls",
  "Human Rights",
  "Animal Welfare Germany",
  "International Animal Welfare",
  "Politics",
  "Humanitarian Aid",
  "Children & Women's Rights",
];

export const ALL_REGIONS = ["Burundi", "East Africa", "Germany", "India", "Thailand", "Malawi", "Indonesia", "Global"];

export const TYPE_LABEL: Record<ItemType, string> = {
  funding: "Funding",
  news: "News",
  email: "Email",
  report: "Report",
  alert: "Alert",
};

export function formatRelative(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 3600) return `${Math.max(1, Math.round(diff / 60))}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  const days = Math.round(diff / 86400);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function daysUntil(iso: string) {
  const d = new Date(iso).getTime();
  return Math.ceil((d - Date.now()) / 86400000);
}
