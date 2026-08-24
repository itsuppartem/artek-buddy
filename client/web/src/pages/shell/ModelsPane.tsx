import { useEffect, useState } from "react";
import { api } from "../../api";
import {
  defaultModelValue,
  MODEL_PROVIDERS,
  maskedKey,
  parseDefaultModelValue,
} from "../../lib/models";
import type { ModelCredential, ModelCredentialList, ModelInfo } from "../../types";
import { Button } from "../../ui/button";
import { IconClose } from "../../ui/icons";

export function ModelsPane({
  credentials,
  onChange,
  onClose,
}: {
  credentials: ModelCredentialList | null;
  onChange: (next: ModelCredentialList) => void;
  onClose: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [models, setModels] = useState<ModelInfo[]>([]);
  const rows = credentials?.credentials ?? [];

  useEffect(() => {
    void api.models.list().then((list) => setModels(list.models ?? []));
  }, [credentials]);

  async function refresh() {
    const next = await api.models.credentials();
    onChange(next);
    const list = await api.models.list();
    setModels(list.models ?? []);
  }

  async function save(provider: string) {
    const apiKey = (drafts[provider] || "").trim();
    if (!apiKey) return;
    setBusy((current) => ({ ...current, [provider]: "save" }));
    try {
      await api.models.connect(provider, apiKey);
      setDrafts((current) => ({ ...current, [provider]: "" }));
      await refresh();
    } finally {
      setBusy((current) => {
        const next = { ...current };
        delete next[provider];
        return next;
      });
    }
  }

  async function retry(provider: string) {
    setBusy((current) => ({ ...current, [provider]: "retry" }));
    try {
      await api.models.connect(provider);
      await refresh();
    } finally {
      setBusy((current) => {
        const next = { ...current };
        delete next[provider];
        return next;
      });
    }
  }

  async function forget(provider: string) {
    setBusy((current) => ({ ...current, [provider]: "forget" }));
    try {
      await api.models.forget(provider);
      setDrafts((current) => ({ ...current, [provider]: "" }));
      await refresh();
    } finally {
      setBusy((current) => {
        const next = { ...current };
        delete next[provider];
        return next;
      });
    }
  }

  async function chooseDefault(value: string) {
    const parsed = parseDefaultModelValue(value);
    if (!parsed) return;
    await api.models.setDefault(parsed.provider, parsed.model);
    await refresh();
  }

  const defaultValue =
    credentials?.defaultProvider && credentials.defaultModel
      ? defaultModelValue(credentials.defaultProvider, credentials.defaultModel)
      : "";

  return (
    <div data-testid="models-pane">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-display text-[16px] font-semibold text-paper">Models</h2>
        <button
          type="button"
          aria-label="Close Models"
          title="Close panel"
          onClick={onClose}
          className="inline-flex h-[34px] items-center gap-1.5 rounded-[8px] border border-hairline px-2.5 text-[13px] text-paper hover:bg-raised"
        >
          <IconClose />
          Close
        </button>
      </div>
      <p className="mb-4 text-[13px] leading-5 text-mute">
        Paste an API key, save it, then pick the model this host should use.
      </p>
      <div className="flex flex-col gap-3">
        {MODEL_PROVIDERS.map((spec) => {
          const row = rows.find((item) => item.provider === spec.id);
          return (
            <ProviderRow
              key={spec.id}
              spec={spec}
              row={row}
              draft={drafts[spec.id] || ""}
              busy={busy[spec.id] || ""}
              models={models.filter((item) => item.provider === spec.id)}
              onDraft={(value) => setDrafts((current) => ({ ...current, [spec.id]: value }))}
              onSave={() => void save(spec.id)}
              onRetry={() => void retry(spec.id)}
              onForget={() => void forget(spec.id)}
              onUse={(model) => void chooseDefault(defaultModelValue(spec.id, model))}
            />
          );
        })}
      </div>
      <label className="mt-5 block text-[13px] text-mute" htmlFor="models-default">
        Default model
      </label>
      <select
        id="models-default"
        data-testid="models-default"
        aria-label="Default model"
        className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper disabled:opacity-40"
        disabled={models.length === 0}
        value={defaultValue}
        onChange={(event) => void chooseDefault(event.target.value)}
      >
        <option value="">{models.length ? "Pick a model" : "No models yet"}</option>
        {models.map((item) => (
          <option
            key={defaultModelValue(item.provider, item.id)}
            value={defaultModelValue(item.provider, item.id)}
          >
            {item.id}
          </option>
        ))}
      </select>
      {credentials?.defaultModel ? (
        <p className="mt-2 text-[13px] text-sage" data-testid="models-using">
          Using {credentials.defaultModel}
        </p>
      ) : null}
    </div>
  );
}

function ProviderRow({
  spec,
  row,
  draft,
  busy,
  models,
  onDraft,
  onSave,
  onRetry,
  onForget,
  onUse,
}: {
  spec: { id: string; label: string };
  row: ModelCredential | undefined;
  draft: string;
  busy: string;
  models: ModelInfo[];
  onDraft: (value: string) => void;
  onSave: () => void;
  onRetry: () => void;
  onForget: () => void;
  onUse: (model: string) => void;
}) {
  const keyId = `models-key-${spec.id}`;
  const saving = busy === "save";
  const loading = busy === "retry" || saving;
  const [picked, setPicked] = useState("");
  return (
    <section
      data-testid={`models-row-${spec.id}`}
      className="rounded-[12px] border border-hairline bg-plate px-3 py-3"
    >
      <h3 className="font-display text-[14.5px] text-paper">{spec.label}</h3>
      <label className="mt-2 block text-[13px] text-mute" htmlFor={keyId}>
        API key
      </label>
      {row?.hasKey && !draft ? (
        <p className="mt-1 text-[14px] text-paper" data-testid={`models-status-${spec.id}`}>
          {maskedKey(row.lastFour)} · Connected
        </p>
      ) : (
        <input
          id={keyId}
          data-testid={keyId}
          type="password"
          autoComplete="off"
          spellCheck={false}
          aria-label={`${spec.label} API key`}
          className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper"
          value={draft}
          onChange={(event) => onDraft(event.target.value)}
        />
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        <Button
          type="button"
          variant="cream"
          size="sm"
          data-testid={`models-save-${spec.id}`}
          disabled={!draft.trim() || saving}
          onClick={onSave}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
        {row?.hasKey ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid={`models-forget-${spec.id}`}
            disabled={busy === "forget"}
            onClick={onForget}
          >
            Forget
          </Button>
        ) : null}
        {row?.error ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid={`models-retry-${spec.id}`}
            disabled={loading}
            onClick={onRetry}
          >
            Retry
          </Button>
        ) : null}
      </div>
      {loading ? <p className="mt-2 text-[13px] text-mute">Loading models…</p> : null}
      {row?.error ? (
        <p className="mt-2 text-[13px] text-danger" data-testid={`models-error-${spec.id}`}>
          {row.error}
        </p>
      ) : null}
      <label className="mt-3 block text-[13px] text-mute" htmlFor={`models-picker-${spec.id}`}>
        Model
      </label>
      <select
        id={`models-picker-${spec.id}`}
        data-testid={`models-picker-${spec.id}`}
        aria-label={`${spec.label} model`}
        className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper disabled:opacity-40"
        disabled={!row?.hasKey || models.length === 0}
        value={picked}
        onChange={(event) => setPicked(event.target.value)}
      >
        <option value="">{row?.hasKey && models.length ? "Pick a model" : "No models yet"}</option>
        {models.map((item) => (
          <option key={item.id} value={item.id}>
            {item.id}
          </option>
        ))}
      </select>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-2"
        data-testid={`models-use-${spec.id}`}
        disabled={!picked}
        onClick={() => onUse(picked)}
      >
        Use this model
      </Button>
    </section>
  );
}
