import { useEffect, useState } from "react";
import { api } from "../../api";
import { storeButtonLabel, useSaveAck } from "../../lib/save-ack";
import type { BotCredential } from "../../types";
import { Button } from "../../ui/button";

function slugify(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/_/g, "-")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 32);
}

function labelFor(provider: string): string {
  return provider.replace(/-/g, " ");
}

export function BotCredentials({ botId }: { botId: string }) {
  const [rows, setRows] = useState<BotCredential[]>([]);

  useEffect(() => {
    void api.bots.credentials(botId).then(setRows);
  }, [botId]);

  function reload() {
    void api.bots.credentials(botId).then(setRows);
  }

  return (
    <div
      className="mt-6 rounded-xl border border-hairline bg-ink p-3.5"
      data-testid="bot-credentials"
    >
      <div className="text-[13.5px] text-paper">Secrets</div>
      <p className="mt-2 text-[12.5px] leading-5 text-mute">
        Add any named secret this bot needs. The host credential broker keeps values hidden. Before
        a worker uses one, you approve its disposable command. Reset and Team ↔ Private keep them.
      </p>
      <div className="mt-3 flex flex-col gap-3">
        {rows.map((item) => (
          <CredentialRow
            key={item.provider}
            botId={botId}
            provider={item.provider}
            label={labelFor(item.provider)}
            saved={item}
            onChange={reload}
          />
        ))}
        <AddCredential botId={botId} existing={rows} onChange={reload} />
      </div>
    </div>
  );
}

function AddCredential({
  botId,
  existing,
  onChange,
}: {
  botId: string;
  existing: BotCredential[];
  onChange: () => void;
}) {
  const [name, setName] = useState("");
  const [draft, setDraft] = useState("");
  const saveAck = useSaveAck();
  const slug = slugify(name);
  const taken = existing.some((item) => item.provider === slug);

  async function save() {
    const secret = draft.trim();
    if (!slug || !secret) return;
    await saveAck.run(async () => {
      await api.bots.saveCredential(botId, slug, secret);
      setName("");
      setDraft("");
      onChange();
    });
  }

  return (
    <div data-testid="bot-credential-add">
      <div className="text-[12px] font-medium text-paper">Add secret</div>
      <label className="mt-1 block text-[12px] text-mute">
        Secret name
        <input
          data-testid="bot-credential-add-name"
          name="secret-name"
          type="text"
          autoComplete="off"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="e.g. Sentry auth…"
          className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
        />
      </label>
      <label className="mt-1 block text-[12px] text-mute">
        Secret
        <input
          data-testid="bot-credential-add-secret"
          name="secret-value"
          type="password"
          autoComplete="off"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
        />
      </label>
      {saveAck.error ? (
        <p className="mt-1 text-[12.5px] text-danger" data-testid="bot-credential-add-error">
          {saveAck.error}
        </p>
      ) : null}
      {taken ? (
        <p className="mt-1 text-[12.5px] text-mute">
          That name is already stored. Replace it above.
        </p>
      ) : null}
      <div className="mt-2">
        <Button
          type="button"
          variant="cream"
          size="sm"
          data-testid="bot-credential-add-save"
          disabled={!slug || !draft.trim() || taken || saveAck.state === "saving"}
          onClick={() => void save()}
        >
          {storeButtonLabel(saveAck.state)}
        </Button>
      </div>
    </div>
  );
}

function CredentialRow({
  botId,
  provider,
  label,
  saved,
  onChange,
}: {
  botId: string;
  provider: string;
  label: string;
  saved: BotCredential | undefined;
  onChange: () => void;
}) {
  const [draft, setDraft] = useState("");
  const saveAck = useSaveAck();
  const [replacing, setReplacing] = useState(false);
  const showField = !saved || replacing;

  async function save() {
    const secret = draft.trim();
    if (!secret) return;
    await saveAck.run(async () => {
      await api.bots.saveCredential(botId, provider, secret);
      setDraft("");
      setReplacing(false);
      onChange();
    });
  }

  async function forget() {
    saveAck.cancel();
    await api.bots.forgetCredential(botId, provider);
    setDraft("");
    setReplacing(false);
    onChange();
  }

  return (
    <div data-testid={`bot-credential-${provider}`}>
      <div className="text-[12px] font-medium text-paper">{label}</div>
      {saved && !replacing ? (
        <p
          className="mt-1 text-[13px] leading-5 text-sage"
          data-testid={`bot-credential-${provider}-status`}
        >
          Saved · ••••{saved.lastFour}
        </p>
      ) : null}
      {showField ? (
        <label className="mt-1 block text-[12px] text-mute">
          Replace secret
          <input
            data-testid={`bot-credential-${provider}-secret`}
            name={`secret-${provider}`}
            type="password"
            autoComplete="off"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            className="mt-1 w-full rounded-lg border border-hairline bg-raised px-3 py-1.5 text-[14px] text-paper"
          />
        </label>
      ) : null}
      {saveAck.error ? (
        <p
          className="mt-1 text-[12.5px] text-danger"
          data-testid={`bot-credential-${provider}-error`}
        >
          {saveAck.error}
        </p>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {showField ? (
          <Button
            type="button"
            variant="cream"
            size="sm"
            data-testid={`bot-credential-${provider}-save`}
            disabled={!draft.trim() || saveAck.state === "saving"}
            onClick={() => void save()}
          >
            {storeButtonLabel(saveAck.state)}
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid={`bot-credential-${provider}-replace`}
            onClick={() => {
              setReplacing(true);
              saveAck.cancel();
            }}
          >
            Replace
          </Button>
        )}
        {saved ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid={`bot-credential-${provider}-forget`}
            onClick={() => void forget()}
          >
            Forget
          </Button>
        ) : null}
      </div>
    </div>
  );
}
