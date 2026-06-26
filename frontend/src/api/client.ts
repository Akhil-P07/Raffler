import axios, { AxiosError } from "axios";
import type {
  AuthResponse,
  DrawResponse,
  Entry,
  GenerateTicketsResponse,
  InviteInfo,
  Me,
  OrgMember,
  OrgSummary,
  Raffle,
  RaffleDetail,
  RaffleInput,
  RaffleLogo,
  RegisterConfirmation,
  RegisterInfo,
  Ticket,
  Winner,
} from "./types";

// In dev, default to "/api" so Vite's proxy forwards to the backend and the
// SPA stays same-origin (CSP connect-src 'self'). In prod, VITE_API_BASE is
// the real API origin.
const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

const SESSION_STORAGE = "raffler_session";

export function getSession(): string | null {
  return localStorage.getItem(SESSION_STORAGE);
}

export function setSession(token: string): void {
  localStorage.setItem(SESSION_STORAGE, token.trim());
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_STORAGE);
}

// withCredentials lets the OAuth state cookie (set by /auth/google/login) ride
// along; the session itself is a Bearer token, not a cookie.
// Authenticated client: injects the session Bearer token on every request.
const authed = axios.create({ baseURL: API_BASE, withCredentials: true });
authed.interceptors.request.use((config) => {
  const token = getSession();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

// Unauthenticated client: login/signup + the Google OAuth URL fetch.
const pub = axios.create({ baseURL: API_BASE, withCredentials: true });

/** Normalize a backend error into a plain message for the UI. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
    if (err.response?.status === 401) return "Please sign in again.";
  }
  return fallback;
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof AxiosError && err.response?.status === 401;
}

// --- Auth -----------------------------------------------------------------

export async function signup(
  email: string,
  password: string,
  orgName?: string
): Promise<AuthResponse> {
  const body: Record<string, string> = { email, password };
  if (orgName?.trim()) body.org_name = orgName.trim();
  const res = (await pub.post<AuthResponse>("/auth/register", body)).data;
  setSession(res.access_token);
  return res;
}

export async function login(
  email: string,
  password: string
): Promise<AuthResponse> {
  const res = (await pub.post<AuthResponse>("/auth/login", { email, password }))
    .data;
  setSession(res.access_token);
  return res;
}

export async function getMe(): Promise<Me> {
  return (await authed.get<Me>("/me")).data;
}

export async function updateOrg(body: {
  name?: string;
  goc_id?: string | null;
}): Promise<OrgSummary> {
  return (await authed.patch<OrgSummary>("/org", body)).data;
}

/** Switch the session to another org the user belongs to; stores the new token. */
export async function selectOrg(orgId: string): Promise<AuthResponse> {
  const res = (await authed.post<AuthResponse>("/auth/select-org", { org_id: orgId }))
    .data;
  setSession(res.access_token);
  return res;
}

// --- Org members (owner only) + invites -----------------------------------

export async function listMembers(): Promise<OrgMember[]> {
  return (await authed.get<OrgMember[]>("/org/members")).data;
}

export async function inviteMember(email: string): Promise<OrgMember> {
  return (await authed.post<OrgMember>("/org/members", { email })).data;
}

export async function removeMember(email: string): Promise<void> {
  await authed.delete(`/org/members/${encodeURIComponent(email)}`);
}

export async function getInviteInfo(token: string): Promise<InviteInfo> {
  return (await pub.get<InviteInfo>(`/invites/${token}`)).data;
}

export async function acceptInvite(
  token: string,
  password?: string
): Promise<AuthResponse> {
  const res = (
    await pub.post<AuthResponse>(`/invites/${token}/accept`, {
      password: password || null,
    })
  ).data;
  setSession(res.access_token);
  return res;
}

/** Fetch the Google consent URL (or throw if Google login isn't configured). */
export async function googleAuthUrl(): Promise<string> {
  return (await pub.get<{ auth_url: string }>("/auth/google/login")).data.auth_url;
}

// --- Raffles --------------------------------------------------------------

export async function listRaffles(): Promise<Raffle[]> {
  return (await authed.get<Raffle[]>("/raffles")).data;
}

export async function getRaffle(id: string): Promise<RaffleDetail> {
  return (await authed.get<RaffleDetail>(`/raffles/${id}`)).data;
}

export async function createRaffle(input: RaffleInput): Promise<Raffle> {
  return (await authed.post<Raffle>("/raffles", input)).data;
}

export async function updateRaffle(
  id: string,
  body: { name?: string; status?: "active" | "closed" }
): Promise<Raffle> {
  return (await authed.patch<Raffle>(`/raffles/${id}`, body)).data;
}

export async function deleteRaffle(id: string): Promise<void> {
  await authed.delete(`/raffles/${id}`);
}

// --- Tickets --------------------------------------------------------------

export async function generateTickets(
  raffleId: string,
  count: number
): Promise<GenerateTicketsResponse> {
  return (
    await authed.post<GenerateTicketsResponse>(`/raffles/${raffleId}/tickets`, {
      count,
    })
  ).data;
}

export async function listTickets(raffleId: string): Promise<Ticket[]> {
  return (await authed.get<Ticket[]>(`/raffles/${raffleId}/tickets`)).data;
}

/** Update a ticket's free-text admin note (per-ticket unique info). */
export async function updateTicketNotes(
  ticketId: string,
  notes: string
): Promise<Ticket> {
  return (await authed.patch<Ticket>(`/tickets/${ticketId}`, { notes })).data;
}

/**
 * Fetch a single ticket's QR PNG as an object URL. The endpoint is
 * ownership-checked, so a plain <img src> can't attach the auth header — we
 * fetch the bytes authenticated and wrap them. Caller revokes the URL.
 */
export async function fetchQrObjectUrl(ticketId: string): Promise<string> {
  const res = await authed.get(`/tickets/${ticketId}/qr`, {
    responseType: "blob",
  });
  return URL.createObjectURL(res.data as Blob);
}

/** Fetch the A4 print-sheet PDF (6 tickets/page) and trigger a download. */
export async function downloadTicketSheet(
  raffleId: string,
  raffleName: string
): Promise<void> {
  const res = await authed.get(`/raffles/${raffleId}/tickets/sheet`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${raffleName.replace(/[^a-z0-9]+/gi, "-")}-tickets.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// --- Logos ----------------------------------------------------------------

/** Read an SVG's intrinsic size from width/height, falling back to viewBox. */
function svgIntrinsicSize(text: string): { w: number; h: number } {
  try {
    const svg = new DOMParser().parseFromString(
      text,
      "image/svg+xml"
    ).documentElement;
    let w = parseFloat(svg.getAttribute("width") || "") || 0;
    let h = parseFloat(svg.getAttribute("height") || "") || 0;
    if (!w || !h) {
      const vb = (svg.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
      if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
        w = vb[2];
        h = vb[3];
      }
    }
    if (w > 0 && h > 0) return { w, h };
  } catch {
    /* fall through */
  }
  return { w: 300, h: 300 };
}

/**
 * Rasterize an SVG to a PNG Blob in the browser (canvas), so the backend only
 * ever stores PNG and we don't need a server-side SVG converter. Non-SVG files
 * pass through unchanged.
 *
 * Many SVGs omit width/height and only carry a viewBox; a browser then draws
 * them blank or at a tiny default. So we derive the real size, scale the
 * longest side up to a crisp 400px, and force explicit width/height onto the
 * <svg> element before rasterizing.
 */
async function rasterizeIfSvg(file: File): Promise<Blob> {
  const isSvg =
    file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg");
  if (!isSvg) return file;

  const text = await file.text();
  const { w: w0, h: h0 } = svgIntrinsicSize(text);
  const factor = 400 / Math.max(w0, h0); // scale up or down to ~400px
  const tw = Math.max(1, Math.round(w0 * factor));
  const th = Math.max(1, Math.round(h0 * factor));

  // Replace any existing width/height on the root <svg> with our explicit size.
  const sized = text.replace(
    /<svg\b([^>]*)>/i,
    (_m, attrs: string) =>
      `<svg${attrs.replace(/\s(width|height)\s*=\s*"[^"]*"/gi, "")}` +
      ` width="${tw}" height="${th}">`
  );

  const url = URL.createObjectURL(new Blob([sized], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    img.width = tw;
    img.height = th;
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Could not load SVG"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = tw;
    canvas.height = th;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Could not get a 2D canvas context");
    // Paint a white background first: tickets are white, and this prevents an
    // SVG with a transparent background (or currentColor/alpha quirks) from
    // exporting transparent pixels that render as black.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, tw, th);
    ctx.drawImage(img, 0, 0, tw, th);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("Canvas export failed"))),
        "image/png"
      )
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function listRaffleLogos(raffleId: string): Promise<RaffleLogo[]> {
  return (await authed.get<RaffleLogo[]>(`/raffles/${raffleId}/logos`)).data;
}

export async function uploadRaffleLogo(
  raffleId: string,
  file: File,
  name?: string
): Promise<RaffleLogo> {
  const png = await rasterizeIfSvg(file);
  // Rasterized SVGs become PNG; other files keep their original name so the
  // backend's content sniffing / any extension hint stays accurate.
  const filename = png === (file as Blob) ? file.name : "logo.png";
  const form = new FormData();
  form.append("file", png, filename);
  if (name?.trim()) form.append("name", name.trim());
  return (await authed.post<RaffleLogo>(`/raffles/${raffleId}/logos`, form)).data;
}

export async function fetchRaffleLogoUrl(
  raffleId: string,
  logoId: string
): Promise<string> {
  const res = await authed.get(`/raffles/${raffleId}/logos/${logoId}`, {
    responseType: "blob",
  });
  return URL.createObjectURL(res.data as Blob);
}

export async function deleteRaffleLogo(
  raffleId: string,
  logoId: string
): Promise<void> {
  await authed.delete(`/raffles/${raffleId}/logos/${logoId}`);
}

// --- Entries --------------------------------------------------------------

export async function listEntries(raffleId: string): Promise<Entry[]> {
  return (await authed.get<Entry[]>(`/raffles/${raffleId}/entries`)).data;
}

/** Download the entries CSV via an authenticated request (blob), then save. */
export async function downloadEntriesCsv(
  raffleId: string,
  raffleName: string
): Promise<void> {
  const res = await authed.get(`/raffles/${raffleId}/entries/export`, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${raffleName.replace(/[^a-z0-9]+/gi, "-")}-entries.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Owner-only: bulk-undo registrations. Returns how many were deregistered. */
export async function deregisterEntries(
  raffleId: string,
  entryIds: string[]
): Promise<number> {
  const res = await authed.post<{ deregistered: number }>(
    `/raffles/${raffleId}/entries/deregister`,
    { entry_ids: entryIds }
  );
  return res.data.deregistered;
}

// --- Draw -----------------------------------------------------------------

export async function drawRaffle(
  raffleId: string,
  prizeCount: number
): Promise<DrawResponse> {
  return (
    await authed.post<DrawResponse>(`/raffles/${raffleId}/draw`, {
      prize_count: prizeCount,
    })
  ).data;
}

export async function listWinners(raffleId: string): Promise<Winner[]> {
  return (await authed.get<Winner[]>(`/raffles/${raffleId}/winners`)).data;
}

// --- Public registration --------------------------------------------------

// Registration is now a logged-in seller action (authed), not public.
export async function getRegisterInfo(token: string): Promise<RegisterInfo> {
  return (await authed.get<RegisterInfo>(`/register/${token}`)).data;
}

export async function submitRegistration(
  token: string,
  name: string,
  email: string,
  phone: string
): Promise<RegisterConfirmation> {
  return (
    await authed.post<RegisterConfirmation>(`/register/${token}`, {
      name,
      email,
      phone,
    })
  ).data;
}
