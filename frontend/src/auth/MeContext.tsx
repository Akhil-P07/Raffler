import { createContext, useContext } from "react";
import type { Me } from "../api/types";

interface MeContextValue {
  me: Me | null;
  /** Re-fetch /me (after switching org, editing org, etc.). */
  reload: () => Promise<void>;
}

export const MeContext = createContext<MeContextValue>({
  me: null,
  reload: async () => {},
});

export function useMe(): MeContextValue {
  return useContext(MeContext);
}

export function isOwner(me: Me | null): boolean {
  return me?.role === "owner";
}
