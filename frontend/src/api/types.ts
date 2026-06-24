// Mirrors backend/schemas.py. Keep in sync with the API contract.

export type RafflePlan = "free" | "club";
export type RaffleStatus = "active" | "closed" | "drawn";

export interface Raffle {
  id: string;
  name: string;
  status: RaffleStatus;
  drawn_at: string | null;
  created_at: string;
}

export interface RaffleDetail extends Raffle {
  entry_count: number;
  ticket_count: number;
}

export interface Ticket {
  id: string;
  ticket_number: number;
  token: string;
  registered: boolean;
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

// Public registration responses (no org data leaked).
export interface RegisterInfo {
  ticket_number: number;
  raffle_name: string;
  registered: boolean;
}

export interface RegisterConfirmation {
  ticket_number: number;
  raffle_name: string;
  name: string;
  message: string;
}
