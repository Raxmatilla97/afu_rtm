import { useCallback, useEffect, useState } from "react";
import { describeError } from "@/api/errors";
import { inventoryApi, type ItemDraft } from "@/api/inventory";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { useAuth } from "@/context/AuthContext";
import type {
  InventoryCategory,
  InventoryItem,
  InventoryMovement,
  InventorySummary,
  Money,
} from "@/types";

const EMPTY_DRAFT: ItemDraft = {
  category_slug: "",
  name: "",
  unit: "dona",
  min_quantity: 0,
  unit_price: null,
  status: "available",
  note: null,
  initial_quantity: 0,
};

const STATUS_OPTIONS = [
  ["available", "✅ Mavjud"],
  ["planned", "📝 Rejalashtirilgan"],
  ["ordered", "🚚 Buyurtma qilingan"],
  ["archived", "📦 Arxivda"],
] as const;

const MOVEMENT_OPTIONS = [
  ["purchase", "🛒 Kirim (sotib olindi)", 1],
  ["return", "↩️ Qaytarildi", 1],
  ["write_off", "🗑 Hisobdan chiqarish", -1],
  ["adjustment", "✏️ Tuzatish", 1],
] as const;

function money(value: Money): string {
  if (!value) return "—";
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toLocaleString("uz-UZ")} so'm` : String(value);
}

export function InventoryPage() {
  const { isAdmin, session } = useAuth();
  const canWrite =
    isAdmin || (session.kind === "employee" && session.employee.can_manage_assignments);

  const [categories, setCategories] = useState<InventoryCategory[]>([]);
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [summary, setSummary] = useState<InventorySummary | null>(null);
  const [q, setQ] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [onlyLow, setOnlyLow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState<ItemDraft>(EMPTY_DRAFT);
  const [openItem, setOpenItem] = useState<InventoryItem | null>(null);
  const [movements, setMovements] = useState<InventoryMovement[]>([]);

  const load = useCallback(async () => {
    try {
      const [cats, list, sum] = await Promise.all([
        inventoryApi.categories(),
        inventoryApi.items({
          q: q || undefined,
          category_slug: categoryFilter || undefined,
          only_low: onlyLow || undefined,
        }),
        inventoryApi.summary(),
      ]);
      setCategories(cats);
      setItems(list);
      setSummary(sum);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    }
  }, [q, categoryFilter, onlyLow]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
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

  async function openMovements(item: InventoryItem) {
    setOpenItem(item);
    try {
      setMovements(await inventoryApi.movements(item.id));
    } catch (e) {
      setError(describeError(e));
    }
  }

  const columns: Column<InventoryItem>[] = [
    {
      key: "name",
      header: "Nomi",
      mobile: "title",
      cell: (item) => item.name,
    },
    {
      key: "meta",
      header: "Kategoriya",
      mobile: "meta",
      cell: (item) => (
        <>
          {item.category_label}
          {item.note ? ` — ${item.note}` : ""}
        </>
      ),
    },
    {
      key: "quantity",
      header: "Qoldiq",
      align: "right",
      cell: (item) => (
        <>
          <span
            className={`font-semibold tabular-nums ${
              item.is_low ? "text-red-600" : "text-slate-800"
            }`}
          >
            {item.quantity}
          </span>
          <span className="text-xs text-slate-400"> {item.unit}</span>
          {item.min_quantity > 0 && (
            <span className="ml-1 text-[11px] text-slate-400">min {item.min_quantity}</span>
          )}
        </>
      ),
    },
    {
      key: "price",
      header: "Narxi",
      align: "right",
      cell: (item) => <span className="tabular-nums">{money(item.unit_price)}</span>,
    },
    {
      key: "status",
      header: "Holati",
      cell: (item) => <span className="text-xs">{item.status_label}</span>,
    },
    {
      key: "actions",
      header: "Amallar",
      cell: (item) => (
        <div className="flex flex-wrap justify-end gap-1.5 md:justify-start">
          <button
            onClick={() => openMovements(item)}
            className="min-h-9 rounded-full border border-slate-300 px-3 text-xs text-slate-600 hover:bg-slate-100"
          >
            📜 Tarix
          </button>
          {canWrite && <MovementButton item={item} busy={busy} onSubmit={run} />}
        </div>
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="RTM Inventar"
        subtitle="Ombor qoldig'i, sarflar va xaridlar. Har bir o'zgarish sababi bilan yoziladi."
        action={
          canWrite && (
            <button
              onClick={() => {
                setCreating((v) => !v);
                setDraft({ ...EMPTY_DRAFT, category_slug: categories[0]?.slug ?? "" });
              }}
              className="min-h-11 rounded-lg bg-brand-600 px-4 text-sm font-medium text-white hover:bg-brand-700"
            >
              {creating ? "✖️ Bekor qilish" : "➕ Yangi inventar"}
            </button>
          )
        }
      />

      {error && <ErrorBanner message={error} />}

      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          <Tile label="Turlari" value={summary.total_items} />
          <Tile label="Omborda bor" value={summary.in_stock_items} tone="#0ca30c" />
          <Tile
            label="Tugayapti"
            value={summary.low_items}
            tone={summary.low_items ? "#d03b3b" : undefined}
            icon={summary.low_items ? "⚠️" : undefined}
          />
          <Tile label="Rejada" value={summary.planned_items} />
          <Tile label="Ombor qiymati" value={money(summary.stock_value)} small />
          <Tile
            label="Shu oy sarflandi"
            value={summary.consumed_this_month}
            note={summary.spent_this_month ? `xarid: ${money(summary.spent_this_month)}` : undefined}
          />
        </div>
      )}

      {creating && canWrite && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!draft.name.trim() || !draft.category_slug) return;
            void run(async () => {
              await inventoryApi.createItem(draft);
              setCreating(false);
              setDraft(EMPTY_DRAFT);
            });
          }}
          className="mb-6 grid gap-3 rounded-xl border border-slate-200 bg-white p-5 sm:grid-cols-2 lg:grid-cols-3"
        >
          <Field label="Nomi">
            <input
              required
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="HP 85A toner"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Kategoriya">
            <select
              required
              value={draft.category_slug}
              onChange={(e) => setDraft({ ...draft, category_slug: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Tanlang</option>
              {categories.map((c) => (
                <option key={c.slug} value={c.slug}>
                  {c.label_uz}
                </option>
              ))}
            </select>
          </Field>
          <Field label="O'lchov birligi">
            <input
              value={draft.unit}
              onChange={(e) => setDraft({ ...draft, unit: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Boshlang'ich qoldiq">
            <input
              type="number"
              min={0}
              value={draft.initial_quantity}
              onChange={(e) =>
                setDraft({ ...draft, initial_quantity: Number(e.target.value) || 0 })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Minimal qoldiq" hint="Shu songa yetganda ogohlantiriladi. 0 — o'chiq">
            <input
              type="number"
              min={0}
              value={draft.min_quantity}
              onChange={(e) => setDraft({ ...draft, min_quantity: Number(e.target.value) || 0 })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Narxi (ixtiyoriy)" hint="Bir dona uchun, so'mda">
            <input
              type="number"
              min={0}
              step="0.01"
              value={draft.unit_price ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, unit_price: e.target.value ? e.target.value : null })
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Holati">
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            >
              {STATUS_OPTIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Izoh (ixtiyoriy)" className="sm:col-span-2">
            <input
              value={draft.note ?? ""}
              onChange={(e) => setDraft({ ...draft, note: e.target.value || null })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <div className="flex items-end lg:col-span-3">
            <button
              type="submit"
              disabled={busy}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Saqlash
            </button>
          </div>
        </form>
      )}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Nomi bo'yicha qidirish..."
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-64"
        />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-auto"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((c) => (
            <option key={c.slug} value={c.slug}>
              {c.label_uz} ({c.item_count})
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={onlyLow}
            onChange={(e) => setOnlyLow(e.target.checked)}
          />
          Faqat tugayotganlar
        </label>
      </div>

      <ResponsiveTable
        rows={items}
        columns={columns}
        rowKey={(i) => i.id}
        empty="Hech narsa topilmadi"
        rowClass={(i) => (i.is_low ? "bg-red-50/60" : "")}
      />
      {openItem && (
        <HistoryPanel
          item={openItem}
          movements={movements}
          canWrite={canWrite}
          onClose={() => setOpenItem(null)}
          onUploaded={() => openMovements(openItem)}
        />
      )}
    </div>
  );
}

function MovementButton({
  item,
  busy,
  onSubmit,
}: {
  item: InventoryItem;
  busy: boolean;
  onSubmit: (action: () => Promise<unknown>) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<string>("purchase");
  const [count, setCount] = useState(1);
  const [price, setPrice] = useState("");
  const [note, setNote] = useState("");

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        disabled={busy}
        className="rounded-full border border-brand-600 px-2.5 py-1 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-50"
      >
        ± Harakat
      </button>
    );
  }

  const sign = MOVEMENT_OPTIONS.find(([value]) => value === reason)?.[2] ?? 1;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (count <= 0) return;
        void onSubmit(async () => {
          await inventoryApi.addMovement(item.id, {
            delta: sign * count,
            reason,
            unit_price: price || null,
            note: note || null,
          });
          setOpen(false);
          setCount(1);
          setPrice("");
          setNote("");
        });
      }}
      className="flex flex-wrap items-center gap-1.5 rounded-lg bg-slate-100 p-2"
    >
      <select
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        className="rounded border border-slate-300 px-2 py-1 text-xs"
      >
        {MOVEMENT_OPTIONS.map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <input
        type="number"
        min={1}
        value={count}
        onChange={(e) => setCount(Number(e.target.value) || 0)}
        className="w-16 rounded border border-slate-300 px-2 py-1 text-xs"
      />
      <input
        type="number"
        min={0}
        step="0.01"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
        placeholder="narxi"
        className="w-24 rounded border border-slate-300 px-2 py-1 text-xs"
      />
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="izoh"
        className="w-28 rounded border border-slate-300 px-2 py-1 text-xs"
      />
      <button
        type="submit"
        className="rounded bg-brand-600 px-2 py-1 text-xs text-white hover:bg-brand-700"
      >
        ✓
      </button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="rounded px-1.5 py-1 text-xs text-slate-500"
      >
        ✖
      </button>
    </form>
  );
}

function HistoryPanel({
  item,
  movements,
  canWrite,
  onClose,
  onUploaded,
}: {
  item: InventoryItem;
  movements: InventoryMovement[];
  canWrite: boolean;
  onClose: () => void;
  onUploaded: () => void;
}) {
  const [uploading, setUploading] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 p-4 sm:items-center">
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl bg-white">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div>
            <h2 className="font-semibold text-slate-800">{item.name}</h2>
            <p className="text-xs text-slate-500">
              Qoldiq: {item.quantity} {item.unit} · {item.category_label}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            ✖
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-5">
          {movements.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">Harakatlar yo'q</p>
          ) : (
            <ul className="space-y-2">
              {movements.map((m) => (
                <li
                  key={m.id}
                  className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm"
                >
                  <span>
                    <span
                      className={`font-semibold tabular-nums ${
                        m.delta > 0 ? "text-emerald-700" : "text-red-700"
                      }`}
                    >
                      {m.delta > 0 ? "+" : ""}
                      {m.delta}
                    </span>{" "}
                    <span className="text-slate-600">{m.reason_label}</span>
                    {m.request_number && (
                      <a
                        href={`/requests/${m.request_id}`}
                        className="ml-2 text-brand-600 hover:underline"
                      >
                        {m.request_number}
                      </a>
                    )}
                    {m.note && <span className="ml-2 text-xs text-slate-400">{m.note}</span>}
                  </span>
                  <span className="text-xs text-slate-400">
                    {m.employee_name ? `${m.employee_name} · ` : ""}
                    {new Date(m.created_at).toLocaleString("uz-UZ")}
                    {m.total_price ? ` · ${money(m.total_price)}` : ""}
                  </span>
                  {m.attachments.length > 0 && (
                    <span className="w-full">
                      {m.attachments.map((a) => (
                        <a
                          key={a.id}
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="mr-2 text-xs text-brand-600 hover:underline"
                        >
                          🧾 {a.original_filename || "chek"}
                        </a>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {canWrite && (
          <footer className="border-t border-slate-200 px-5 py-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
              🧾 Chek yoki hujjat biriktirish
              <input
                type="file"
                className="hidden"
                disabled={uploading}
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  setUploading(true);
                  try {
                    await inventoryApi.uploadReceipt(item.id, file);
                    onUploaded();
                  } finally {
                    setUploading(false);
                  }
                }}
              />
            </label>
            <p className="mt-1 text-xs text-slate-400">
              Ixtiyoriy — chek bo'lmasa ham inventar hisobga olinaveradi.
            </p>
          </footer>
        )}
      </div>
    </div>
  );
}

function Tile({
  label,
  value,
  note,
  tone,
  icon,
  small,
}: {
  label: string;
  value: number | string;
  note?: string;
  tone?: string;
  icon?: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div
        className={`font-bold tabular-nums ${small ? "text-base" : "text-2xl"}`}
        style={{ color: tone ?? "#2a78d6" }}
      >
        {icon && <span className="mr-1">{icon}</span>}
        {value}
      </div>
      <div className="text-xs text-slate-500">{label}</div>
      {note && <div className="mt-0.5 text-[11px] text-slate-400">{note}</div>}
    </div>
  );
}

function Field({
  label,
  hint,
  className = "",
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-0.5 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}
