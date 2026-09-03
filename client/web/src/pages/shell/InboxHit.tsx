import { splitQueryMatch } from "../../lib/sidebar";

export function InboxHit({ text, query }: { text: string; query: string }) {
  return (
    <>
      {splitQueryMatch(text, query).map((part, index) =>
        part.hit ? (
          <mark
            key={`${part.text}-${index}`}
            data-testid="inbox-hit"
            className="rounded-sm bg-tan/40 text-inherit"
          >
            {part.text}
          </mark>
        ) : (
          part.text
        ),
      )}
    </>
  );
}
