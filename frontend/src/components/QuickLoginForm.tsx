import { useState } from "react";
import { authApi, type QuickLookup } from "@/api/auth";
import { ApiError } from "@/api/client";

/**
 * Signing in with an employee id number and a password set here.
 *
 * Three steps rather than one form, and the middle one exists for a reason that is not
 * convenience: after the id number is typed the screen shows **whose account this is**
 * before asking for anything else. People have been ending up inside a colleague's record,
 * so the name is put in front of them while going back still costs one click.
 *
 * The same three steps happen in the bot, driven by the same endpoints — see
 * `afu_shared/quick_login.py` for the rules both sides share.
 */
export function QuickLoginForm({ onDone, onBack }: { onDone: () => void; onBack: () => void }) {
  const [step, setStep] = useState<"id" | "password" | "setup" | "sent">("id");
  const [idNumber, setIdNumber] = useState("");
  const [who, setWho] = useState<QuickLookup | null>(null);
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      // The API answers with a written Uzbek sentence for everything a person can get
      // wrong, so it is shown as it arrives rather than translated into a status code.
      setError(
        e instanceof ApiError
          ? e.message || "Xatolik yuz berdi."
          : "Serverga ulanib bo'lmadi. Internet aloqasini tekshiring.",
      );
    } finally {
      setBusy(false);
    }
  }

  function submitId(e: React.FormEvent) {
    e.preventDefault();
    void run(async () => {
      const found = await authApi.quickLookup(idNumber.trim());
      setWho(found);
      if (found.status === "not_found") {
        setError("Bunday xodim ID raqami topilmadi. Raqamni tekshirib qaytadan kiriting.");
        return;
      }
      if (found.status === "not_eligible") {
        setError("Hisobingiz faol emas. RTM bilan bog'laning.");
        return;
      }
      if (found.status === "locked") {
        setError(
          `Parol bir necha marta noto'g'ri kiritildi. ${found.locked_minutes} daqiqadan ` +
            "keyin qaytadan urinib ko'ring.",
        );
        return;
      }
      setStep(found.status === "needs_setup" ? "setup" : "password");
    });
  }

  function submitPassword(e: React.FormEvent) {
    e.preventDefault();
    void run(async () => {
      await authApi.quickLogin(idNumber.trim(), password);
      onDone();
    });
  }

  function submitSetup(e: React.FormEvent) {
    e.preventDefault();
    void run(async () => {
      await authApi.quickSetup(idNumber.trim(), password, email.trim());
      onDone();
    });
  }

  function forgot() {
    void run(async () => {
      const result = await authApi.quickForgot(idNumber.trim());
      setNotice(result.message);
      setStep("sent");
    });
  }

  const identity = who && (
    <div className="mb-4 rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm">
      <div className="font-semibold text-brand-700">{who.full_name}</div>
      {who.department_name && <div className="text-slate-600">{who.department_name}</div>}
      <button
        type="button"
        onClick={() => {
          setStep("id");
          setWho(null);
          setPassword("");
          setError(null);
        }}
        className="mt-1 text-xs text-slate-500 underline hover:text-slate-700"
      >
        Bu men emasman — ID raqamni o'zgartirish
      </button>
    </div>
  );

  return (
    <div>
      {step === "id" && (
        <form onSubmit={submitId} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Xodim ID raqami
            </label>
            <input
              required
              inputMode="numeric"
              autoFocus
              value={idNumber}
              onChange={(e) => setIdNumber(e.target.value)}
              placeholder="masalan: 4572612075"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">
              Xodimlik guvohnomangizda va HEMIS profilingizda yozilgan raqam.
            </p>
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "Tekshirilmoqda..." : "Davom etish"}
          </button>
          <button
            type="button"
            onClick={onBack}
            className="w-full text-sm text-slate-500 hover:text-slate-700"
          >
            ⬅ Orqaga
          </button>
        </form>
      )}

      {step === "password" && (
        <form onSubmit={submitPassword} className="space-y-4">
          {identity}
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Parol</label>
            <input
              type="password"
              required
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "Kirilmoqda..." : "Kirish"}
          </button>
          <button
            type="button"
            onClick={forgot}
            disabled={busy}
            className="w-full text-sm text-brand-700 hover:underline disabled:opacity-50"
          >
            Parolni unutdingizmi?
          </button>
        </form>
      )}

      {step === "setup" && (
        <form onSubmit={submitSetup} className="space-y-4">
          {identity}
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
            Siz bu hisobga birinchi marta kiryapsiz. Parol o'ylab toping — keyingi safar
            shu parol bilan kirasiz.
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Yangi parol
            </label>
            <input
              type="password"
              required
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">
              Kamida 6 ta belgi, ichida kamida bitta harf va bitta raqam bo'lsin.
            </p>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Elektron pochta
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ism.familiya@afu.uz"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-slate-500">
              Parolni unutsangiz, tiklash havolasi shu manzilga yuboriladi.
            </p>
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {busy ? "Saqlanmoqda..." : "Parolni saqlash va kirish"}
          </button>
        </form>
      )}

      {step === "sent" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-brand-100 bg-brand-50 px-4 py-3 text-sm text-brand-700">
            {notice}
          </div>
          <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
            <li>Pochtangizni oching (kerak bo'lsa «Spam» papkasini ham tekshiring).</li>
            <li>Xatdagi «Yangi parol o'rnatish» havolasini bosing.</li>
            <li>Ochilgan sahifada yangi parolni kiriting.</li>
            <li>Shu yerga qaytib, yangi parol bilan kiring.</li>
          </ol>
          <button
            type="button"
            onClick={() => {
              setStep("password");
              setPassword("");
              setError(null);
            }}
            className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
          >
            Parolni kiritishga qaytish
          </button>
        </div>
      )}
    </div>
  );
}
