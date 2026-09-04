import { type FormEvent, useEffect, useState } from "react";
import { api } from "../../api";
import { MODEL_PROVIDERS, maskedKey, modelChipSelected } from "../../lib/models";
import type { ModelCredential, ModelCredentialList, ModelInfo } from "../../types";
import { Button } from "../../ui/button";
import { IconClose } from "../../ui/icons";

const EFFORTS = [
  { id: "xhigh", label: "Extra high" },
  { id: "high", label: "High" },
  { id: "medium", label: "Medium" },
  { id: "low", label: "Low" },
] as const;

function usingCaption(model: string, effort?: string | null, fast?: boolean | null): string {
  const labels: Record<string, string> = {
    xhigh: "Extra high",
    high: "High",
    medium: "Medium",
    low: "Low",
  };
  const parts = [`Using ${model}`];
  if (effort) parts.push(labels[effort] || effort);
  if (fast) parts.push("Fast");
  return parts.join(" · ");
}

export function ModelsPane({
  botId,
  credentials,
  onChange,
  onClose,
  onApplied,
}: {
  botId?: string;
  credentials: ModelCredentialList | null;
  onChange: (next: ModelCredentialList) => void;
  onClose: () => void;
  onApplied?: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [listError, setListError] = useState("");
  const [autoRetried, setAutoRetried] = useState<Record<string, boolean>>({});
  const [effort, setEffort] = useState(credentials?.defaultEffort || "xhigh");
  const [fast, setFast] = useState(credentials?.defaultFast !== false);
  const rows = credentials?.credentials ?? [];

  useEffect(() => {
    void api.models
      .list()
      .then((list) => {
        setModels(list.models ?? []);
        setListError("");
      })
      .catch((err: unknown) => {
        setListError(err instanceof Error ? err.message : "Could not load models.");
      });
  }, [credentials]);

  useEffect(() => {
    for (const row of rows) {
      if (
        row.hasKey &&
        !row.error &&
        !autoRetried[row.provider] &&
        !models.some((item) => item.provider === row.provider)
      ) {
        setAutoRetried((current) => ({ ...current, [row.provider]: true }));
        void retry(row.provider);
      }
    }
  }, [autoRetried, credentials, models, rows]);

  useEffect(() => {
    if (credentials?.defaultEffort) setEffort(credentials.defaultEffort);
    if (credentials?.defaultFast != null) setFast(credentials.defaultFast);
  }, [credentials?.defaultEffort, credentials?.defaultFast]);

  async function refresh() {
    const next = await api.models.credentials();
    onChange(next);
    try {
      const list = await api.models.list();
      setModels(list.models ?? []);
      setListError("");
    } catch (err) {
      setListError(err instanceof Error ? err.message : "Could not load models.");
    }
  }

  async function save(provider: string, apiKey: string) {
    const trimmed = apiKey.trim();
    if (!trimmed) {
      setErrors((current) => ({ ...current, [provider]: "Paste a key first." }));
      return;
    }
    setBusy((current) => ({ ...current, [provider]: "save" }));
    try {
      await api.models.connect(provider, trimmed);
      setDrafts((current) => ({ ...current, [provider]: "" }));
      setErrors((current) => ({ ...current, [provider]: "" }));
      await refresh();
    } catch (err) {
      setErrors((current) => ({
        ...current,
        [provider]: err instanceof Error ? err.message : "Could not save the key.",
      }));
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
      setErrors((current) => ({ ...current, [provider]: "" }));
      await refresh();
    } catch (err) {
      setErrors((current) => ({
        ...current,
        [provider]: err instanceof Error ? err.message : "Could not load models.",
      }));
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
      setErrors((current) => ({ ...current, [provider]: "" }));
      setAutoRetried((current) => ({ ...current, [provider]: false }));
      await refresh();
    } catch (err) {
      setErrors((current) => ({
        ...current,
        [provider]: err instanceof Error ? err.message : "Could not forget the key.",
      }));
    } finally {
      setBusy((current) => {
        const next = { ...current };
        delete next[provider];
        return next;
      });
    }
  }

  async function choose(provider: string, model: string, nextEffort = effort, nextFast = fast) {
    if (!model) return;
    try {
      await api.models.setDefault(provider, model, nextEffort, nextFast, botId);
      await refresh();
      onApplied?.();
    } catch (err) {
      setErrors((current) => ({
        ...current,
        [provider]: err instanceof Error ? err.message : "Could not use that model.",
      }));
    }
  }

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
        Paste an API key and Save. That row&apos;s model is what this host uses.
      </p>
      {listError ? (
        <p className="mb-3 text-[13px] text-danger" data-testid="models-error">
          {listError}
        </p>
      ) : null}
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
              error={errors[spec.id] || row?.error || ""}
              models={models.filter((item) => item.provider === spec.id)}
              effort={effort}
              fast={fast}
              using={
                credentials?.defaultProvider === spec.id ? (credentials.defaultModel ?? "") : ""
              }
              onDraft={(value) => setDrafts((current) => ({ ...current, [spec.id]: value }))}
              onSave={(key) => void save(spec.id, key)}
              onRetry={() => void retry(spec.id)}
              onForget={() => void forget(spec.id)}
              onUse={(model) => void choose(spec.id, model)}
              onEffort={(value) => {
                setEffort(value);
                if (credentials?.defaultModel && credentials.defaultProvider === spec.id) {
                  void choose(spec.id, credentials.defaultModel, value, fast);
                }
              }}
              onFast={(value) => {
                setFast(value);
                if (credentials?.defaultModel && credentials.defaultProvider === spec.id) {
                  void choose(spec.id, credentials.defaultModel, effort, value);
                }
              }}
            />
          );
        })}
      </div>
      {credentials?.defaultModel ? (
        <p className="mt-3 text-[13px] text-sage" data-testid="models-using">
          {usingCaption(
            credentials.defaultModel,
            credentials.defaultEffort,
            credentials.defaultFast,
          )}
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
  error,
  models,
  using,
  effort,
  fast,
  onDraft,
  onSave,
  onRetry,
  onForget,
  onUse,
  onEffort,
  onFast,
}: {
  spec: { id: string; label: string };
  row: ModelCredential | undefined;
  draft: string;
  busy: string;
  error: string;
  models: ModelInfo[];
  using: string;
  effort: string;
  fast: boolean;
  onDraft: (value: string) => void;
  onSave: (apiKey: string) => void;
  onRetry: () => void;
  onForget: () => void;
  onUse: (model: string) => void;
  onEffort: (value: string) => void;
  onFast: (value: boolean) => void;
}) {
  const keyId = `models-key-${spec.id}`;
  const saving = busy === "save";
  const loading = busy === "retry" || saving;
  const showKeyField = !(row?.hasKey && !draft);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onSave(String(data.get("api_key") || draft));
  }

  return (
    <section
      data-testid={`models-row-${spec.id}`}
      className="rounded-[12px] border border-hairline bg-plate px-3 py-3"
    >
      <h3 className="font-display text-[14.5px] text-paper">{spec.label}</h3>
      <form onSubmit={submit}>
        <label className="mt-2 block text-[13px] text-mute" htmlFor={keyId}>
          API key
        </label>
        {showKeyField ? (
          <input
            id={keyId}
            name="api_key"
            data-testid={keyId}
            type="password"
            autoComplete="off"
            spellCheck={false}
            aria-label={`${spec.label} API key`}
            className="mt-1 h-10 w-full rounded-[10px] border border-hairline bg-raised px-2.5 text-[14px] text-paper"
            value={draft}
            onChange={(event) => onDraft(event.target.value)}
          />
        ) : (
          <p className="mt-1 text-[14px] text-paper" data-testid={`models-status-${spec.id}`}>
            {maskedKey(row?.lastFour)} · Connected
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          {showKeyField ? (
            <Button
              type="submit"
              variant="cream"
              size="sm"
              data-testid={`models-save-${spec.id}`}
              disabled={saving}
            >
              {saving ? "Saving…" : "Save"}
            </Button>
          ) : null}
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
          {row?.error || error || (row?.hasKey && models.length === 0) ? (
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
      </form>
      {loading ? <p className="mt-2 text-[13px] text-mute">Loading models…</p> : null}
      {error ? (
        <p className="mt-2 text-[13px] text-danger" data-testid={`models-error-${spec.id}`}>
          {error}
        </p>
      ) : null}
      <p className="mt-3 text-[13px] text-mute">Model</p>
      <div
        data-testid={`models-picker-${spec.id}`}
        role="listbox"
        aria-label={`${spec.label} model`}
        className="mt-1 flex flex-wrap gap-1.5"
      >
        {models.length ? (
          models.map((item) => {
            const active = modelChipSelected(using, item.id);
            return (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={active}
                aria-current={active ? "true" : undefined}
                data-model={item.id}
                onClick={() => onUse(item.id)}
                className={`rounded-[8px] border px-2.5 py-1 text-[13px] ${
                  active
                    ? "border-tan bg-tan font-semibold text-ink ring-2 ring-paper"
                    : "border-hairline bg-paper text-ink hover:bg-raised hover:text-paper"
                }`}
              >
                {item.id}
                {active ? <span className="sr-only"> in use</span> : null}
              </button>
            );
          })
        ) : (
          <span className="text-[13px] text-mute">No models yet</span>
        )}
      </div>
      {spec.id === "cursor" && row?.hasKey ? (
        <div className="mt-3 flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-[13px] text-mute" htmlFor="models-effort-cursor">
              Reasoning
              <select
                id="models-effort-cursor"
                data-testid="models-effort-cursor"
                aria-label="Reasoning"
                className="ml-2 h-9 rounded-[8px] border border-hairline bg-paper px-2 text-[13px] text-ink"
                value={effort}
                onChange={(event) => onEffort(event.target.value)}
              >
                {EFFORTS.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-[13px] text-paper">
              <input
                type="checkbox"
                data-testid="models-fast-cursor"
                aria-label="Fast"
                checked={fast}
                onChange={(event) => onFast(event.target.checked)}
              />
              Fast
            </label>
          </div>
          <p className="text-[12.5px] text-mute">
            Reasoning is how long the model may think. Fast prefers a quicker reply.
          </p>
        </div>
      ) : null}
      {!models.length && !row?.hasKey ? (
        <p className="mt-2 text-[13px] text-mute" data-testid={`models-empty-${spec.id}`}>
          Paste a key on this row to load models.
        </p>
      ) : models.length ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-2"
          data-testid={`models-use-${spec.id}`}
          disabled={!using}
          onClick={() => onUse(using)}
        >
          Use this model
        </Button>
      ) : null}
    </section>
  );
}
