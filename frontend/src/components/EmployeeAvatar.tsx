import { useState } from "react";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

const SIZES = {
  sm: "h-9 w-9 text-xs",
  md: "h-11 w-11 text-sm",
  lg: "h-14 w-14 text-lg",
  // For the detail dialog, where the photo is one of the things being looked at rather
  // than a marker next to a name.
  xl: "h-28 w-28 text-3xl",
} as const;

/**
 * An employee's photo, or their initials.
 *
 * The fallback is not decoration. HEMIS photos are downloaded during sync and a missing
 * one is normal — a broken-image icon in a list of forty people looks like the page is
 * failing, while initials look deliberate. `onError` catches the other case: a row that
 * has a path pointing at a file the sync never actually managed to write.
 */
export function EmployeeAvatar({
  name,
  imagePath,
  size = "md",
}: {
  name: string;
  imagePath?: string | null;
  size?: keyof typeof SIZES;
}) {
  // Which path failed, not merely "something failed". An administrator who uploads a new
  // portrait over one whose file was missing gets a different path back, and a plain
  // boolean would keep showing their initials until the page was reloaded.
  const [failedPath, setFailedPath] = useState<string | null>(null);
  // image_local_path is stored as "employees/<id>.jpg" and the backend serves that tree
  // under /media/.
  const src = imagePath && imagePath !== failedPath ? `/media/${imagePath}` : null;

  if (src) {
    return (
      <img
        src={src}
        alt={name}
        loading="lazy"
        onError={() => setFailedPath(imagePath ?? null)}
        className={`${SIZES[size]} shrink-0 rounded-full border border-slate-200 object-cover`}
      />
    );
  }

  return (
    <div
      aria-hidden
      title={name}
      className={`${SIZES[size]} flex shrink-0 items-center justify-center rounded-full bg-brand-50 font-semibold text-brand-700`}
    >
      {initials(name)}
    </div>
  );
}
