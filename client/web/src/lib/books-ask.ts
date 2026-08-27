export type SkillBookChip = { slug: string; name: string };

export function runPromptForBook(name: string): string {
  return `please run ${name}`;
}

export function slugsConsumedByRunPrompt(text: string, books: SkillBookChip[]): string[] {
  const body = text.trim();
  if (!body) return [];
  return books.filter((book) => body === runPromptForBook(book.name)).map((book) => book.slug);
}

export function hideBookSlug(
  hidden: Record<string, string[]>,
  botId: string,
  slug: string,
): Record<string, string[]> {
  const already = hidden[botId] ?? [];
  if (already.includes(slug)) return hidden;
  return { ...hidden, [botId]: [...already, slug] };
}

export function visibleSkillBooks(
  books: SkillBookChip[],
  hidden: Record<string, string[]>,
  botId: string | undefined,
): SkillBookChip[] {
  if (!botId) return books;
  const skipped = new Set(hidden[botId] ?? []);
  return books.filter((book) => !skipped.has(book.slug));
}
