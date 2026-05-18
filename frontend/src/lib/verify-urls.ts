import { formatAIN } from "@/lib/format"

export function assessorPortalUrl(apn: string): string {
  return `https://portal.assessor.lacounty.gov/parceldetail/${formatAIN(apn)}`
}

export function googleSatelliteUrl(lat: number, lng: number): string {
  return `https://www.google.com/maps/place/${lat},${lng}/@${lat},${lng},19z/data=!3m1!1e3`
}

export function projectSunroofUrl(lat: number, lng: number): string {
  return `https://sunroof.withgoogle.com/building/${lat}/${lng}/details`
}

export function censusAcsBlockGroupUrl(geoid: string | null | undefined): string {
  if (!geoid) return "https://data.census.gov/table?q=ACSDT5Y2024.B19013"
  return `https://data.census.gov/table/ACSDT5Y2024.B19013?g=1500000US${geoid}`
}

export function calEnviroScreenUrl(): string {
  return "https://oehha.ca.gov/calenviroscreen/sb535"
}

export function ladwpRateSheetUrl(): string {
  return "https://www.ladwp.com/account/customer-service/electric-rates"
}

export function sceRateSheetUrl(): string {
  return "https://www.sce.com/regulatory/tariff-books"
}

export function utilityRateSheetUrl(utility: string | null | undefined): string {
  if (utility === "LADWP") return ladwpRateSheetUrl()
  if (utility === "SCE") return sceRateSheetUrl()
  return "https://www.cpuc.ca.gov/industries-and-topics/electrical-energy/electric-rates"
}
