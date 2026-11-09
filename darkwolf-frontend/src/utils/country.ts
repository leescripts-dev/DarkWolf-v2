const countryCodes: Record<string, string> = {
  us: "us", usa: "us", "united states": "us", "united states of america": "us",
  gb: "gb", uk: "gb", "great britain": "gb", england: "gb", "united kingdom": "gb",
  dz: "dz", algeria: "dz", th: "th", thailand: "th",
  ae: "ae", uae: "ae", "united arab emirates": "ae",
  af: "af", afghanistan: "af", al: "al", albania: "al", ad: "ad", andorra: "ad",
  ao: "ao", angola: "ao", ar: "ar", argentina: "ar", am: "am", armenia: "am",
  au: "au", australia: "au", at: "at", austria: "at", az: "az", azerbaijan: "az",
  bd: "bd", bangladesh: "bd", be: "be", belgium: "be", br: "br", brazil: "br",
  ca: "ca", canada: "ca", cl: "cl", chile: "cl", cn: "cn", china: "cn",
  co: "co", colombia: "co", hr: "hr", croatia: "hr", cz: "cz", czechia: "cz", "czech republic": "cz",
  dk: "dk", denmark: "dk", eg: "eg", egypt: "eg", fi: "fi", finland: "fi",
  fr: "fr", france: "fr", de: "de", germany: "de", gr: "gr", greece: "gr",
  hk: "hk", "hong kong": "hk", hu: "hu", hungary: "hu", in: "in", india: "in",
  id: "id", indonesia: "id", ir: "ir", iran: "ir", iq: "iq", iraq: "iq",
  ie: "ie", ireland: "ie", il: "il", israel: "il", it: "it", italy: "it",
  jp: "jp", japan: "jp", ke: "ke", kenya: "ke", kr: "kr", "south korea": "kr",
  my: "my", malaysia: "my", mx: "mx", mexico: "mx", ma: "ma", morocco: "ma",
  nl: "nl", netherlands: "nl", nz: "nz", "new zealand": "nz", ng: "ng", nigeria: "ng",
  no: "no", norway: "no", pk: "pk", pakistan: "pk", ph: "ph", philippines: "ph",
  pl: "pl", poland: "pl", pt: "pt", portugal: "pt", ro: "ro", romania: "ro",
  ru: "ru", russia: "ru", sa: "sa", "saudi arabia": "sa", rs: "rs", serbia: "rs",
  sg: "sg", singapore: "sg", za: "za", "south africa": "za", es: "es", spain: "es",
  se: "se", sweden: "se", ch: "ch", switzerland: "ch", tw: "tw", taiwan: "tw",
  tr: "tr", turkey: "tr", türkiye: "tr", ua: "ua", ukraine: "ua", vn: "vn", vietnam: "vn",
};

export function countryFlagCode(country: string | null | undefined): string | null {
  if (!country) return null;
  const normalized = country
    .normalize("NFKC")
    .replace(/\p{Extended_Pictographic}/gu, "")
    .split(",")[0]
    .trim()
    .toLocaleLowerCase();

  if (countryCodes[normalized]) return countryCodes[normalized];
  return /^[a-z]{2}$/.test(normalized) ? normalized : null;
}
