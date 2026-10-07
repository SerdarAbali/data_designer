export function designStatusLabel(status: string): string {
  if (status === "healthy") return "Valid";
  if (status === "attention") return "Needs review";
  return "Draft";
}

export function designValidationReason(reason: string): string {
  if (reason === "A dependency cycle prevents reliable health analysis.") {
    return "Contract dependencies contain a cycle, so design validation is incomplete.";
  }
  if (reason === "No target fields are mapped.") {
    return "No target fields are mapped.";
  }
  if (reason === "One or more target fields have multiple active writers.") {
    return "One or more target fields are mapped by multiple contracts.";
  }
  const upstreamPrefix = "Depends on unhealthy upstream integration(s): ";
  if (reason.startsWith(upstreamPrefix)) {
    return `Depends on upstream contracts that need validation: ${reason.slice(upstreamPrefix.length)}`;
  }
  return reason;
}
