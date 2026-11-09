export function displayOrganizationName(
  name: string,
  ransomwareGroup: string | null,
) {
  if (ransomwareGroup?.toLowerCase() !== "kazu") return name;
  return name.replace(/^[\u{1f1e6}-\u{1f1ff}]{2}\s*/u, "");
}
