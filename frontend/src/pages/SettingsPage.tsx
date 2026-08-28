import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  adminApi,
  type ActivityDay,
  type ActivityEvent,
  type ActorActivity,
  type SiteConfig,
  type SmtpConfig,
} from "@/api/admin";
import { describeError } from "@/api/errors";
import { ColumnChart } from "@/components/charts/ColumnChart";
import { SERIES } from "@/components/charts/palette";
import { ErrorBanner, PageHeader } from "@/components/PageHeader";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";

/**
 * Settings and monitoring, in four tabs.
 *
 * They sit together because they answer one question between them — "is this thing set up
 * and is anybody using it?" — and because each on its own is too small to be a page. Tabs
 * rather than four menu entries: an admin comes here to check something, not to navigate.
 *
 * The tab lives in the URL hash, so a reload keeps the reader where they were and a link
 * to "the SMTP tab" is a link somebody can send.
 */
const TABS = [
  { id: "sayt", label: "🌐 Sayt (SEO)" },
  { id: "pochta", label: "✉️ Pochta (SMTP)" },
  { id: "statistika", label: "📊 Bot statistikasi" },
  { id: "faoliyat", label: "👣 Faoliyat" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function initialTab(): TabId {
  const fromHash = window.location.hash.replace("#", "");
  return TABS.some((t) => t.id === fromHash) ? (fromHash as TabId) : "sayt";
}

export function SettingsPage() {
  const [tab, setTab] = useState<TabId>(initialTab);

  useEffect(() => {
    window.location.hash = tab;
  }, [tab]);

  return (
    <div>
      <PageHeader
        title="Sozlamalar va kuzatuv"
        subtitle="Sayt ma'lumotlari, pochta serveri va tizimdan foydalanish statistikasi"
      />

      <div className="mb-6 flex flex-wrap gap-2 border-b border-slate-200 pb-3">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`min-h-11 rounded-lg px-4 text-sm font-medium transition-colors ${
              tab === t.id
                ? "bg-brand-600 text-white"
                : "border border-slate-300 text-slate-600 hover:bg-slate-50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "sayt" && <SiteTab />}
      {tab === "pochta" && <SmtpTab />}
      {tab === "statistika" && <StatsTab />}
      {tab === "faoliyat" && <ActivityTab />}
    </div>
  );
}

/* ------------------------------------------------------------------ site */

function SiteTab() {
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    adminApi.siteSettings().then(setConfig).catch((e) => setError(describeError(e)));
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setConfig(await adminApi.saveSiteSettings(config));
      setSaved(true);
      // The tab title is one of the things being edited, so show the result immediately
      // rather than waiting for the next page load.
      document.title = config.title;
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  if (!config) {
    return error ? <ErrorBanner message={error} /> : <div className="text-slate-400">Yuklanmoqda...</div>;
  }

  return (
    <form onSubmit={save} className="max-w-3xl">
      {error && <ErrorBanner message={error} />}
      {saved && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          ✅ Saqlandi.
        </div>
      )}

      <Card title="Sayt ma'lumotlari">
        <p className="mb-4 text-sm text-slate-500">
          Bu matnlar brauzer sarlavhasida va qidiruv tizimlariga beriladigan meta
          teglarida ishlatiladi.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Sayt nomi (title)" className="sm:col-span-2">
            <input
              required
              maxLength={120}
              value={config.title}
              onChange={(e) => setConfig({ ...config, title: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Tavsif (description)" className="sm:col-span-2">
            <textarea
              rows={3}
              maxLength={400}
              value={config.description}
              onChange={(e) => setConfig({ ...config, description: e.target.value })}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Kalit so'zlar (keywords)" className="sm:col-span-2">
            <input
              maxLength={300}
              value={config.keywords}
              onChange={(e) => setConfig({ ...config, keywords: e.target.value })}
              placeholder="vergul bilan ajrating"
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Tashkilot">
            <input
              maxLength={160}
              value={config.organization}
              onChange={(e) => setConfig({ ...config, organization: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Aloqa uchun e-mail">
            <input
              type="email"
              maxLength={160}
              value={config.contact_email}
              onChange={(e) => setConfig({ ...config, contact_email: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Aloqa uchun telefon">
            <input
              maxLength={60}
              value={config.contact_phone}
              onChange={(e) => setConfig({ ...config, contact_phone: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
        </div>

        <button
          type="submit"
          disabled={busy}
          className="mt-5 min-h-11 rounded-lg bg-brand-600 px-5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? "Saqlanmoqda..." : "💾 Saqlash"}
        </button>
      </Card>
    </form>
  );
}

/* ------------------------------------------------------------------ smtp */

function SmtpTab() {
  const [config, setConfig] = useState<SmtpConfig | null>(null);
  const [password, setPassword] = useState("");
  const [testTo, setTestTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    adminApi.smtpSettings().then(setConfig).catch((e) => setError(describeError(e)));
  }, []);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }

  if (!config) {
    return error ? <ErrorBanner message={error} /> : <div className="text-slate-400">Yuklanmoqda...</div>;
  }

  return (
    <div className="max-w-3xl">
      {error && <ErrorBanner message={error} />}
      {notice && (
        <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {notice}
        </div>
      )}

      <Card title="Pochta serveri (SMTP)">
        <p className="mb-4 text-sm text-slate-500">
          Parolni unutgan xodimga tiklash havolasi shu server orqali yuboriladi. Bu yerda
          saqlangan qiymatlar <code className="rounded bg-slate-100 px-1">.env</code>{" "}
          fayldagi sozlamalardan ustun turadi.
        </p>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run(async () => {
              const saved = await adminApi.saveSmtpSettings({
                host: config.host,
                port: config.port,
                user: config.user,
                password,
                from_address: config.from_address,
                starttls: config.starttls,
              });
              setConfig(saved);
              setPassword("");
              setNotice("✅ Pochta sozlamalari saqlandi.");
            });
          }}
          className="grid gap-4 sm:grid-cols-2"
        >
          <Field label="SMTP server (host)">
            <input
              value={config.host}
              onChange={(e) => setConfig({ ...config, host: e.target.value })}
              placeholder="smtp.afu.uz"
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Port">
            <input
              type="number"
              min={1}
              max={65535}
              value={config.port}
              onChange={(e) => setConfig({ ...config, port: Number(e.target.value) || 587 })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Foydalanuvchi (login)">
            <input
              value={config.user}
              onChange={(e) => setConfig({ ...config, user: e.target.value })}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field
            label="Parol"
            hint={
              config.has_password
                ? "Parol saqlangan. O'zgartirmoqchi bo'lsangizgina yangisini yozing."
                : "Hozircha parol saqlanmagan."
            }
          >
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={config.has_password ? "••••••••" : ""}
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <Field label="Jo'natuvchi manzil (From)" className="sm:col-span-2">
            <input
              value={config.from_address}
              onChange={(e) => setConfig({ ...config, from_address: e.target.value })}
              placeholder="RTM Murojaatlar <no-reply@afu.uz>"
              className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm"
            />
          </Field>
          <label className="flex min-h-11 items-center gap-2 text-sm text-slate-600 sm:col-span-2">
            <input
              type="checkbox"
              checked={config.starttls}
              onChange={(e) => setConfig({ ...config, starttls: e.target.checked })}
            />
            STARTTLS (587-port uchun). 465-port bo'lsa — belgini olib tashlang.
          </label>

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={busy}
              className="min-h-11 rounded-lg bg-brand-600 px-5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {busy ? "Saqlanmoqda..." : "💾 Saqlash"}
            </button>
          </div>
        </form>
      </Card>

      <Card title="Sinov xati" className="mt-4">
        <p className="mb-3 text-sm text-slate-500">
          Sozlamalar to'g'ri ishlayotganini bilishning yagona yo'li — xat yuborib ko'rish.
          Xat navbatga qo'yiladi; yetib bormasa, worker loglarida sabab yoziladi.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            type="email"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            placeholder="sizning@pochtangiz.uz"
            className="min-h-11 flex-1 rounded-lg border border-slate-300 px-3 text-sm sm:max-w-sm"
          />
          <button
            type="button"
            disabled={busy || !testTo.trim()}
            onClick={() =>
              void run(async () => {
                const result = await adminApi.sendTestEmail(testTo.trim());
                setNotice(result.message);
              })
            }
            className="min-h-11 rounded-lg border border-brand-600 px-4 text-sm font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-50"
          >
            ✉️ Sinov xatini yuborish
          </button>
        </div>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ stats */

function StatsTab() {
  const [days, setDays] = useState(30);
  const [rows, setRows] = useState<ActivityDay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    adminApi
      .activityDaily(days)
      .then(setRows)
      .catch((e) => setError(describeError(e)))
      .finally(() => setLoading(false));
  }, [days]);

  const groups = rows.map((row) => ({
    label: row.day.slice(5),
    values: [row.bot_users, row.web_users],
  }));

  const botToday = rows.length ? rows[rows.length - 1].bot_users : 0;
  const botPeak = Math.max(0, ...rows.map((r) => r.bot_users));
  const botEvents = rows.reduce((sum, r) => sum + r.bot_events, 0);
  const webEvents = rows.reduce((sum, r) => sum + r.web_events, 0);

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm"
        >
          <option value={7}>So'nggi 7 kun</option>
          <option value={30}>So'nggi 30 kun</option>
          <option value={90}>So'nggi 90 kun</option>
        </select>
        <span className="text-sm text-slate-400">
          Bir kishi kuniga necha marta bosishidan qat'i nazar — bir marta sanaladi.
        </span>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Tile label="Bugun botda" value={botToday} />
        <Tile label="Eng yuqori kun (bot)" value={botPeak} />
        <Tile label="Botdagi amallar" value={botEvents} />
        <Tile label="Saytdagi amallar" value={webEvents} />
      </div>

      <Card title="Kunlik foydalanuvchilar">
        {loading ? (
          <div className="text-slate-400">Yuklanmoqda...</div>
        ) : (
          <ColumnChart
            groups={groups}
            series={[
              { label: "Bot", color: SERIES[0] },
              { label: "Sayt", color: SERIES[1] },
            ]}
            height={220}
            emptyMessage="Hozircha ma'lumot yig'ilmagan"
          />
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ activity */

function ActivityTab() {
  const [actors, setActors] = useState<ActorActivity[]>([]);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [source, setSource] = useState("");
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [people, feed] = await Promise.all([
        adminApi.activityActors(30),
        adminApi.activity({ source: source || undefined, q: q || undefined, limit: 150 }),
      ]);
      setActors(people);
      setEvents(feed);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoading(false);
    }
  }, [source, q]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  const actorColumns: Column<ActorActivity>[] = [
    {
      key: "name",
      header: "Xodim",
      mobile: "title",
      cell: (a) => <span className="font-medium">{a.actor_name}</span>,
    },
    {
      key: "action",
      header: "Oxirgi amal",
      mobile: "meta",
      cell: (a) => (
        <span>
          {a.last_action_label}
          {a.last_target ? ` · ${a.last_target}` : ""}
        </span>
      ),
    },
    { key: "source", header: "Qayerda", cell: (a) => sourceBadge(a.last_source) },
    {
      key: "events",
      header: "30 kunda",
      align: "right",
      cell: (a) => <span className="tabular-nums">{a.events}</span>,
    },
    {
      key: "when",
      header: "Oxirgi marta",
      cell: (a) => <span className="text-slate-500">{when(a.last_seen_at)}</span>,
    },
  ];

  const eventColumns: Column<ActivityEvent>[] = [
    {
      key: "when",
      header: "Vaqt",
      mobile: "meta",
      cell: (e) => <span className="text-slate-500">{when(e.created_at)}</span>,
    },
    {
      key: "actor",
      header: "Kim",
      mobile: "title",
      cell: (e) => <span className="font-medium">{e.actor_name}</span>,
    },
    { key: "action", header: "Amal", cell: (e) => e.action_label },
    { key: "target", header: "Nima ustida", cell: (e) => e.target || "—" },
    { key: "source", header: "Qayerda", cell: (e) => sourceBadge(e.source) },
  ];

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <Card title="Kim oxirgi marta nima qildi" className="mb-6">
        <p className="mb-3 text-sm text-slate-500">
          So'nggi 30 kun ichida tizimdan foydalangan xodimlar, eng oxirgisi yuqorida.
        </p>
        {loading ? (
          <div className="text-slate-400">Yuklanmoqda...</div>
        ) : (
          <ResponsiveTable
            rows={actors}
            columns={actorColumns}
            rowKey={(a) => a.employee_id ?? a.actor_name}
            empty="Hozircha faoliyat qayd etilmagan"
          />
        )}
      </Card>

      <Card title="So'nggi amallar">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm"
          >
            <option value="">Bot va sayt</option>
            <option value="bot">Faqat bot</option>
            <option value="web">Faqat sayt</option>
          </select>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Ism yoki murojaat raqami..."
            className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm sm:w-72"
          />
          <span className="text-sm text-slate-400">{events.length} ta yozuv</span>
        </div>

        {loading ? (
          <div className="text-slate-400">Yuklanmoqda...</div>
        ) : (
          <ResponsiveTable
            rows={events}
            columns={eventColumns}
            rowKey={(e) => e.id}
            empty="Yozuv topilmadi"
          />
        )}
      </Card>
    </div>
  );
}

function sourceBadge(source: string) {
  const bot = source === "bot";
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        bot ? "bg-brand-50 text-brand-700" : "bg-slate-100 text-slate-600"
      }`}
    >
      {bot ? "🤖 Bot" : "🌐 Sayt"}
    </span>
  );
}

/** Times are read as "how long ago", so that is what is shown, with the clock time after. */
function when(iso: string): string {
  const then = new Date(iso);
  const minutes = Math.floor((Date.now() - then.getTime()) / 60000);
  if (minutes < 1) return "hozirgina";
  if (minutes < 60) return `${minutes} daqiqa oldin`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} soat oldin`;
  return then.toLocaleString("uz-UZ", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ------------------------------------------------------------------ shared bits */

function Card({
  title,
  className = "",
  children,
}: {
  title: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white p-5 ${className}`}>
      <h2 className="mb-3 font-semibold text-slate-800">{title}</h2>
      {children}
    </section>
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
  children: ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-slate-600">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-2xl font-bold tabular-nums text-brand-700">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}
