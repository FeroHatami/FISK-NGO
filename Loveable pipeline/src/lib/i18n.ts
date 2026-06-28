import { createContext, useContext, useSyncExternalStore, useCallback } from "react";

export type Lang = "EN" | "DE";

// Global store for language (bypasses React tree issues with routers)
let currentLang: Lang = "EN";
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): Lang {
  return currentLang;
}

export function setGlobalLang(lang: Lang) {
  currentLang = lang;
  listeners.forEach((l) => l());
}

export function useLang(): Lang {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

// Keep context for backward compat but it's no longer the source of truth
export const LangContext = createContext<Lang>("EN");

// UI string translations
const strings = {
  // Navigation
  "nav.home": { EN: "Home", DE: "Startseite" },
  "nav.inbox": { EN: "Smart Inbox", DE: "Intelligenter Posteingang" },
  "nav.funding": { EN: "Funding", DE: "Förderung" },
  "nav.opportunities": { EN: "Opportunity Finder", DE: "Chancen-Finder" },
  "nav.search": { EN: "Search across everything…", DE: "Überall suchen…" },

  // Home page
  "home.eyebrow": { EN: "Home", DE: "Startseite" },
  "home.greeting": { EN: "Morning, Anja. The world needs you — here's where to start.", DE: "Guten Morgen, Anja. Die Welt braucht dich – hier geht's los." },
  "home.actionRequired": { EN: "Action required", DE: "Handlungsbedarf" },
  "home.importantUpdates": { EN: "Important updates", DE: "Wichtige Neuigkeiten" },
  "home.upcomingDeadlines": { EN: "Upcoming deadlines", DE: "Kommende Fristen" },
  "home.noDeadlines": { EN: "No upcoming deadlines.", DE: "Keine bevorstehenden Fristen." },
  "home.nothingInRegion": { EN: "Nothing in this region right now.", DE: "Gerade nichts in dieser Region." },
  "home.openInbox": { EN: "Open Smart Inbox", DE: "Posteingang öffnen" },
  "home.filteringBy": { EN: "Filtering by", DE: "Gefiltert nach" },
  "home.showMore": { EN: "Show more", DE: "Mehr anzeigen" },
  "home.showLess": { EN: "Show less", DE: "Weniger anzeigen" },

  // Inbox
  "inbox.title": { EN: "Inbox", DE: "Posteingang" },
  "inbox.eyebrow": { EN: "Smart Inbox", DE: "Intelligenter Posteingang" },
  "inbox.items": { EN: "items — sorted by priority", DE: "Elemente — nach Priorität sortiert" },
  "inbox.filters": { EN: "Filters", DE: "Filter" },
  "inbox.noMatch": { EN: "No items match your filters.", DE: "Keine Einträge für diese Filter." },
  "inbox.selectItem": { EN: "Select an item to read the AI summary.", DE: "Wähle einen Eintrag, um die KI-Zusammenfassung zu lesen." },
  "inbox.aiSummary": { EN: "AI Summary", DE: "KI-Zusammenfassung" },
  "inbox.suggestedStep": { EN: "Suggested next step", DE: "Empfohlener nächster Schritt" },
  "inbox.loading": { EN: "Loading inbox...", DE: "Posteingang wird geladen..." },
  "inbox.error": { EN: "Failed to load items. Is the backend running?", DE: "Laden fehlgeschlagen. Läuft das Backend?" },

  // Detail view
  "detail.viewSource": { EN: "View source", DE: "Quelle ansehen" },
  "detail.original": { EN: "Original", DE: "Original" },
  "detail.translation": { EN: "Translation", DE: "Übersetzung" },
  "detail.showOriginal": { EN: "Show original", DE: "Original anzeigen" },
  "detail.showTranslation": { EN: "Show translation", DE: "Übersetzung anzeigen" },
  "detail.deadline": { EN: "Deadline", DE: "Frist" },
  "detail.amount": { EN: "Amount", DE: "Betrag" },
  "detail.organization": { EN: "Organization", DE: "Organisation" },
  "detail.eligibility": { EN: "Eligibility", DE: "Förderberechtigung" },
  "detail.requirements": { EN: "Requirements", DE: "Anforderungen" },
  "detail.sender": { EN: "Sender", DE: "Absender" },
  "detail.originalLanguage": { EN: "Original language", DE: "Originalsprache" },

  // Actions
  "action.apply": { EN: "Apply", DE: "Bewerben" },
  "action.reply": { EN: "Reply", DE: "Antworten" },
  "action.read": { EN: "Read", DE: "Lesen" },
  "action.monitor": { EN: "Monitor", DE: "Beobachten" },
  "action.startApplication": { EN: "Start application", DE: "Bewerbung starten" },
  "action.draftReply": { EN: "Draft a reply", DE: "Antwort entwerfen" },
  "action.markRead": { EN: "Mark as read after review", DE: "Nach Prüfung als gelesen markieren" },
  "action.addWatchlist": { EN: "Add to watchlist", DE: "Zur Beobachtungsliste hinzufügen" },

  // Filters
  "filter.type": { EN: "Type", DE: "Typ" },
  "filter.priority": { EN: "Priority", DE: "Priorität" },
  "filter.topic": { EN: "Topic", DE: "Thema" },
  "filter.region": { EN: "Region", DE: "Region" },
  "filter.high": { EN: "High", DE: "Hoch" },
  "filter.medium": { EN: "Medium", DE: "Mittel" },
  "filter.low": { EN: "Low", DE: "Niedrig" },

  // Funding page
  "funding.eyebrow": { EN: "Funding research", DE: "Förderrecherche" },
  "funding.title": { EN: "Describe your project. I'll find the funding.", DE: "Beschreibe dein Projekt. Ich finde die Förderung." },
  "funding.describe": { EN: "Describe the project you're seeking funding for — sector, country, budget, applicant type, timeline.", DE: "Beschreibe das Projekt, für das du Förderung suchst — Sektor, Land, Budget, Antragstellertyp, Zeitplan." },
  "funding.search": { EN: "Search", DE: "Suchen" },
  "funding.open": { EN: "Open", DE: "Offen" },
  "funding.urgent": { EN: "Urgent", DE: "Dringend" },
  "funding.rolling": { EN: "Rolling", DE: "Laufend" },
  "funding.all": { EN: "All", DE: "Alle" },
  "funding.searchOpp": { EN: "Search opportunities", DE: "Möglichkeiten suchen" },
  "funding.noMatch": { EN: "No opportunities match these filters.", DE: "Keine Möglichkeiten für diese Filter." },
  "funding.matched": { EN: "AI-matched results", DE: "KI-gestützte Ergebnisse" },
  "funding.noResults": { EN: "No matching funding opportunities found for this description.", DE: "Keine passenden Fördermöglichkeiten für diese Beschreibung gefunden." },
  "funding.loading": { EN: "Loading funding opportunities...", DE: "Fördermöglichkeiten werden geladen..." },
  "funding.matchReason": { EN: "Match reason:", DE: "Übereinstimmungsgrund:" },

  // Opportunities page
  "opp.eyebrow": { EN: "AI-detected", DE: "KI-erkannt" },
  "opp.title": { EN: "Opportunity Finder", DE: "Chancen-Finder" },
  "opp.subtitle": { EN: "We quietly surface partnerships and collaborations that match what you actually do — before you have to look for them.", DE: "Wir finden leise Partnerschaften und Kooperationen, die zu eurer Arbeit passen — bevor ihr danach suchen müsst." },
  "opp.analyzing": { EN: "Analyzing items for opportunities...", DE: "Einträge werden auf Chancen analysiert..." },
  "opp.error": { EN: "Failed to load insights. Is the backend running?", DE: "Laden fehlgeschlagen. Läuft das Backend?" },
  "opp.empty": { EN: "No partnership opportunities detected right now. Check back when new items arrive.", DE: "Derzeit keine Partnerschaftsmöglichkeiten erkannt. Schau zurück, wenn neue Einträge eintreffen." },
  "opp.viewDetails": { EN: "View details", DE: "Details anzeigen" },
  "opp.back": { EN: "← Back to today", DE: "← Zurück zu heute" },

  // Briefing
  "briefing.title": { EN: "Daily Briefing", DE: "Tägliches Briefing" },
  "briefing.actionNeeded": { EN: "Action needed", DE: "Handlungsbedarf" },
  "briefing.caughtUp": { EN: "No high-priority items right now. You're all caught up.", DE: "Keine hochprioritären Einträge. Alles erledigt." },
  "briefing.loading": { EN: "Loading briefing...", DE: "Briefing wird geladen..." },
  "briefing.error": { EN: "Could not load briefing. Is the backend running?", DE: "Briefing konnte nicht geladen werden. Läuft das Backend?" },

  // Badges
  "badge.funding": { EN: "Funding", DE: "Förderung" },
  "badge.news": { EN: "News", DE: "Nachrichten" },
  "badge.email": { EN: "Email", DE: "E-Mail" },
  "badge.report": { EN: "Report", DE: "Bericht" },
  "badge.alert": { EN: "Alert", DE: "Warnung" },
  "badge.now": { EN: "Now", DE: "Jetzt" },
  "badge.today": { EN: "Today", DE: "Heute" },
  "badge.thisWeek": { EN: "This week", DE: "Diese Woche" },
  "badge.later": { EN: "Later", DE: "Später" },

  // Copilot
  "copilot.askAi": { EN: "Ask AI", DE: "KI fragen" },
  "copilot.greeting": { EN: "Good morning. I've already read everything overnight. Ask me anything.", DE: "Guten Morgen. Ich habe über Nacht alles gelesen. Frag mich was du möchtest." },
  "copilot.placeholder": { EN: "Ask anything about your work…", DE: "Frag mich alles über deine Arbeit…" },

  // Map
  "map.fieldMap": { EN: "Field map", DE: "Feldkarte" },
  "map.clickFilter": { EN: "Click a marker to filter", DE: "Klicke auf einen Marker zum Filtern" },
  "map.clear": { EN: "Clear", DE: "Zurücksetzen" },
  "map.loading": { EN: "Loading map...", DE: "Karte wird geladen..." },
} as const;

export type StringKey = keyof typeof strings;

export function t(key: StringKey, lang: Lang): string {
  return strings[key]?.[lang] ?? strings[key]?.EN ?? key;
}
