import type { DimensionName } from "@/types/score"

export interface DimensionMeta {
  label: string
  shortLabel: string
  description: string
}

export const DIMENSION_META: Record<DimensionName, DimensionMeta> = {
  roof_potential: {
    label: "Roof Potential",
    shortLabel: "Roof",
    description: "Usable south-facing area, tilt, and shading from Google Solar API",
  },
  income_qualification: {
    label: "Income Qualification",
    shortLabel: "Income",
    description: "Block-group median household income from US Census ACS",
  },
  ownership: {
    label: "Ownership Signal",
    shortLabel: "Ownership",
    description: "Homeowner's Exemption presence from LA County Assessor",
  },
  bill_pain: {
    label: "Bill Pain",
    shortLabel: "Bill",
    description: "Utility-aware electricity rate (LADWP, SCE, or fallback)",
  },
  equity_proxy: {
    label: "Equity Strength",
    shortLabel: "Equity",
    description: "Proxy via Prop-13 tenure (older base year = more equity)",
  },
  no_existing_solar: {
    label: "Existing Solar Detection",
    shortLabel: "Solar",
    description: "Computer vision on satellite imagery — Phase 2 coming soon",
  },
  intent_signal: {
    label: "Intent Signal",
    shortLabel: "Intent",
    description: "CRM / web-form intent — Phase 2 coming soon",
  },
}

export const ACTIVE_DIMENSIONS: DimensionName[] = [
  "roof_potential",
  "income_qualification",
  "ownership",
  "bill_pain",
  "equity_proxy",
]

export const GHOST_DIMENSIONS: DimensionName[] = [
  "no_existing_solar",
  "intent_signal",
]
