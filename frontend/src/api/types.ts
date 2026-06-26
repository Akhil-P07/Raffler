// Mirrors backend/schemas.py. Keep in sync with the API contract.

export type RafflePlan = "free" | "club";
export type RaffleStatus = "active" | "closed" | "drawn";

// --- Auth ---

export type Role = "owner" | "member";

export interface OrgSummary {
  id: string;
  name: string;
  plan: RafflePlan;
  goc_id: string | null;
}

export interface OrgMembershipSummary extends OrgSummary {
  role: Role;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  email: string;
  role: Role;
  org: OrgSummary;
  orgs: OrgMembershipSummary[];
}

export interface Me {
  email: string;
  role: Role;
  org: OrgSummary;
  orgs: OrgMembershipSummary[];
}

export interface OrgMember {
  email: string;
  status: string; // 'owner' | 'member' | 'invited'
}

export interface InviteInfo {
  email: string;
  org_name: string;
  needs_password: boolean;
}

export interface Raffle {
  id: string;
  name: string;
  status: RaffleStatus;
  // Legal ticket-face metadata (printed on tickets; all optional).
  ticket_price: string | null;
  prizes: string | null;
  drawing_datetime: string | null;
  drawing_location: string | null;
  drawn_at: string | null;
  created_at: string;
}

/** Fields the create-raffle form collects (legal ticket-face metadata). */
export interface RaffleInput {
  name: string;
  ticket_price?: string;
  prizes?: string;
  drawing_datetime?: string; // ISO string
  drawing_location?: string;
}

export interface RaffleDetail extends Raffle {
  entry_count: number;
  ticket_count: number;
}

export interface RaffleLogo {
  id: string;
  name: string | null;
  position: number;
}

export interface Ticket {
  id: string;
  ticket_number: number;
  registered: boolean;
  // Free-text admin note for per-ticket unique info (not printed on the ticket).
  notes: string | null;
  // No `token`: the server never exposes it. The QR is fetched by ticket id
  // (GET /tickets/{id}/qr) and the print sheet is rendered server-side.
}

export interface GenerateTicketsResponse {
  raffle_id: string;
  created: number;
  tickets: Ticket[];
}

export interface Entry {
  id: string;
  name: string;
  email: string;
  phone: string | null;
  ticket_number: number;
  registered_at: string;
}

export interface Winner {
  id: string;
  prize_rank: number;
  name: string;
  email: string;
  ticket_number: number;
  drawn_at: string;
}

export interface DrawResponse {
  raffle_id: string;
  status: RaffleStatus;
  already_drawn: boolean;
  winners: Winner[];
}

// Seller-side ticket lookup. `owned` says whether the scanned ticket belongs
// to the logged-in seller's org; details are present only when owned.
export interface RegisterInfo {
  owned: boolean;
  ticket_number: number | null;
  raffle_name: string | null;
  registered: boolean | null;
  registrant_name: string | null;
  registrant_email: string | null;
  registrant_phone: string | null;
}

export interface RegisterConfirmation {
  ticket_number: number;
  raffle_name: string;
  name: string;
  message: string;
}
