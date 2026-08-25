import { useCallback, useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { softApi } from "@/api/soft";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { useAuth } from "@/context/AuthContext";
import type { SoftAsset, SoftCategory } from "@/types";

function humanSize(bytes: number | null): string {
  if (!bytes) return "—";
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function SoftPage() {
  const { isAdmin, session } = useAuth();
  const canWrite =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

  const [categories, setCategories] = useState<SoftCategory[]>([]);
  const [assets, setAssets] = useState<SoftAsset[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<SoftAsset | null>(null);

  const [form, setForm] = useState({
    category_slug: "",
    title: "",
    version: "",
    description: "",
  });
  const [file, setFile] = useState<File | null>(null);

  const load = useCallback(async () => {
    try {
      const [cats, list] = await Promise.all([
        softApi.categories(),
        softApi.assets(filter || undefined),
      ]);
      setCategories(cats);
      setAssets(list);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<SoftAsset>[] = [
    {
      key: "title",
      header: "Nomi",
      mobile: "title",
      cell: (a) => (
        <span>
          {a.title}
          {a.version && (
            <span className="ml-1 text-xs font-normal text-slate-400">{a.version}</span>
          )}
          {a.is_cached && (
            <span
              title="Telegram keshida — bot uni bir zumda yuboradi"
              className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] text-emerald-700"
            >
              ⚡ kesh
            </span>
          )}
        </span>
      ),
    },
    {
      key: "meta",
      header: "Kategoriya",
      mobile: "meta",
      cell: (a) => (
        <>
          {a.category_label}
          {a.description ? ` — ${a.description}` : ""}
        </>
      ),
    },
    { key: "size", header: "Hajmi", align: "right", cell: (a) => humanSize(a.file_size) },
    {
      key: "views",
      header: "Ko'rishlar",
      align: "right",
      // Impressions in the bot's Soft list, which is the only place anybody browses the
      // shelf. Read next to the downloads column it separates a file nobody wants from one
      // nobody has managed to find.
      cell: (a) => <span className="tabular-nums text-slate-500">{a.view_count}</span>,
    },
    {
      key: "downloads",
      header: "Yuklab olishlar",
      align: "right",
      cell: (a) => <span className="tabular-nums">{a.download_count}</span>,
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (a) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
          <a
            href={a.download_url}
            className="inline-flex min-h-9 items-center rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
          >
            ⬇️ Yuklab olish
          </a>
          {canWrite && (
            <button
              onClick={() => setEditing(a)}
              disabled={busy}
              className="min-h-9 rounded-full border border-brand-600 px-3 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-50"
            >
              ✏️ Tahrirlash
            </button>
          )}
          {canWrite && a.is_active && (
            <button
              onClick={() =>
                window.confirm(`"${a.title}" ro'yxatdan yashirilsinmi?`) &&
                void run(() => softApi.deactivate(a.id))
              }
              disabled={busy}
              className="min-h-9 rounded-full border border-red-300 px-3 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
            >
              🗑 Yashirish
            </button>
          )}
          {canWrite && !a.is_active && (
            <button
              onClick={() => void run(() => softApi.update(a.id, { is_active: true }))}
              disabled={busy}
              className="min-h-9 rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            >
              ↩️ Qaytarish
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    // Full width, like RTM Inventar beside it in the menu: six columns and a row of action
    // buttons have nowhere to go inside a narrow container.
    <div>
      <PageHeader
        title="RTM Soft"
        subtitle="Bu yerga yuklangan fayllar botdagi «💿 Soft va drayverlar» tugmasida chiqadi"
        action={
          canWrite && (
            <button
              onClick={() => {
                setShowForm((v) => !v);
                setForm((f) => ({ ...f, category_slug: f.category_slug || categories[0]?.slug || "" }));
              }}
              className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700"
            >
              {showForm ? "✖️ Yopish" : "⬆️ Fayl yuklash"}
            </button>
          )
        }
      />

      {error && <ErrorBanner message={error} />}

      {showForm && canWrite && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!file || !form.title.trim() || !form.category_slug) return;
            void run(async () => {
              await softApi.upload({
                file,
                category_slug: form.category_slug,
                title: form.title.trim(),
                version: form.version.trim() || undefined,
                description: form.description.trim() || undefined,
              });
              setForm({ category_slug: form.category_slug, title: "", version: "", description: "" });
              setFile(null);
              setShowForm(false);
            });
          }}
          className="mb-6 grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-4"
        >
          <Field label="Kategoriya">
            <select
              required
              value={form.category_slug}
              onChange={(e) => setForm({ ...form, category_slug: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            >
              <option value="">Tanlang</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.label_uz}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Nomi">
            <input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="HP LaserJet 1102 drayver"
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Versiya / OS">
            <input
              value={form.version}
              onChange={(e) => setForm({ ...form, version: e.target.value })}
              placeholder="Win 10/11 x64"
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Fayl">
            <input
              type="file"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-2 file:min-h-9 file:rounded-lg file:border file:border-slate-300 file:bg-white file:px-3 file:text-sm"
            />
          </Field>
          <Field label="Izoh (ixtiyoriy)" className="sm:col-span-2 lg:col-span-3">
            <input
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={busy}
              className="min-h-11 w-full rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Yuklanmoqda..." : "⬆️ Yuklash"}
            </button>
          </div>
          <p className="text-xs text-slate-400 lg:col-span-4">
            Fayl 25 MB gacha. Botda birinchi marta yuborilgach Telegram uni keshlaydi —
            keyingi so'rovlar bir zumda bajariladi.
          </p>
        </form>
      )}

      <div className="mb-4">
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.label_uz} ({c.asset_count})
            </option>
          ))}
        </select>
      </div>

      <ResponsiveTable
        rows={assets}
        columns={columns}
        rowKey={(a) => a.id}
        empty="Hozircha fayl yo'q"
        rowClass={(a) => (a.is_active ? "" : "opacity-50")}
      />

      {editing && canWrite && (
        <EditAssetModal
          asset={editing}
          categories={categories}
          busy={busy}
          onClose={() => setEditing(null)}
          onSave={(patch) =>
            void run(async () => {
              await softApi.update(editing.id, patch);
              setEditing(null);
            })
          }
        />
      )}
    </div>
  );
}

/**
 * Editing what a file *says* about itself, never the bytes.
 *
 * A wrong title is the common mistake and the one that makes a driver unfindable. Swapping
 * the file itself is deliberately not offered: Telegram caches the first copy the bot
 * sends and keeps handing that one out, so a silent replacement would leave everybody
 * downloading the old file under the new name. Upload the new version and hide the old
 * row — the download history then stays attached to the file it actually describes.
 */
function EditAssetModal({
  asset,
  categories,
  busy,
  onClose,
  onSave,
}: {
  asset: SoftAsset;
  categories: SoftCategory[];
  busy: boolean;
  onClose: () => void;
  onSave: (patch: {
    category_slug: string;
    title: string;
    version: string;
    description: string;
  }) => void;
}) {
  const [draft, setDraft] = useState({
    category_slug: asset.category_slug,
    title: asset.title,
    version: asset.version ?? "",
    description: asset.description ?? "",
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3">
          <div className="min-w-0">
            <h2 className="font-semibold text-slate-800">Faylni tahrirlash</h2>
            <p className="truncate text-xs text-slate-500">
              {asset.original_filename || "fayl"} · {asset.download_count} yuklab olish ·{" "}
              {asset.view_count} ko'rish
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✖
          </button>
        </header>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.title.trim() || !draft.category_slug) return;
            onSave({
              category_slug: draft.category_slug,
              title: draft.title.trim(),
              version: draft.version.trim(),
              description: draft.description.trim(),
            });
          }}
          className="flex-1 overflow-y-auto p-5"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Nomi" className="sm:col-span-2">
              <input
                required
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              />
            </Field>
            <Field label="Kategoriya">
              <select
                required
                value={draft.category_slug}
                onChange={(e) => setDraft({ ...draft, category_slug: e.target.value })}
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              >
                {categories.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.label_uz}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Versiya / OS">
              <input
                value={draft.version}
                onChange={(e) => setDraft({ ...draft, version: e.target.value })}
                placeholder="Win 10/11 x64"
                className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
              />
            </Field>
            <Field label="Izoh" className="sm:col-span-2">
              <textarea
                rows={3}
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </Field>
          </div>

          <p className="mt-3 text-xs text-slate-400">
            Faylning o'zini almashtirib bo'lmaydi — yangisini yuklab, eskisini yashiring.
          </p>

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="min-h-11 rounded-lg border border-slate-300 px-4 text-sm text-slate-600 hover:bg-slate-50"
            >
              Bekor qilish
            </button>
            <button
              type="submit"
              disabled={busy}
              className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Saqlanmoqda..." : "💾 Saqlash"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  className = "",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
    </label>
  );
}
