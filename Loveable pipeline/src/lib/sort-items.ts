import type { Item } from "./mock-data";

const PRIORITY_ORDER: Record<string, number> = { high: 0, med: 1, low: 2 };

/**
 * Sort items by priority (high → med → low), then most recent date first within each tier.
 */
export function sortByPriority(items: Item[]): Item[] {
  return [...items].sort((a, b) => {
    const pa = PRIORITY_ORDER[a.priority] ?? 2;
    const pb = PRIORITY_ORDER[b.priority] ?? 2;
    if (pa !== pb) return pa - pb;
    return (b.date || "").localeCompare(a.date || "");
  });
}

import type { Lang } from "./i18n";

/** Get the language-appropriate title for an item. */
export function itemTitle(item: { title: string; title_de?: string }, lang: Lang): string {
  if (lang === "DE") return item.title_de || item.title;
  return item.title;
}
