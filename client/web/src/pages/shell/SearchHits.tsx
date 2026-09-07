import { InboxHit } from "./InboxHit";

export type HostSearchHit = {
  id: string;
  documentKind: "message" | "memory" | "artifact" | "bot";
  resourceId: string;
  sourceId: string;
  title: string;
  snippet: string;
};

const KIND_LABEL: Record<HostSearchHit["documentKind"], string> = {
  message: "Message",
  memory: "Memory",
  artifact: "File",
  bot: "Chat",
};

export function SearchHits({
  query,
  hits,
  onOpenBot,
}: {
  query: string;
  hits: HostSearchHit[];
  onOpenBot: (botId: string) => void;
}) {
  if (!hits.length) return null;
  return (
    <div data-testid="search-hits" className="mb-1 flex flex-col gap-0.5">
      {hits.map((hit) => {
        const openable = hit.resourceId.startsWith("bot_");
        const label = hit.title || KIND_LABEL[hit.documentKind];
        return (
          <button
            key={hit.id}
            type="button"
            data-testid="search-hit"
            data-kind={hit.documentKind}
            data-bot-id={openable ? hit.resourceId : undefined}
            disabled={!openable}
            onClick={() => {
              if (openable) onOpenBot(hit.resourceId);
            }}
            className="rounded-xl px-2.5 py-2 text-left hover:bg-raised disabled:opacity-70"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-[13px] text-paper">
                <InboxHit text={label} query={query} />
              </span>
              <span className="shrink-0 font-mono text-[8.5px] uppercase text-mute">
                {KIND_LABEL[hit.documentKind]}
              </span>
            </div>
            {hit.snippet ? (
              <div className="mt-0.5 truncate text-[11.5px] text-mute">
                <InboxHit text={hit.snippet} query={query} />
              </div>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
