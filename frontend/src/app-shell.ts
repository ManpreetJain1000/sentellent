export type AppShell = {
  title: string;
  subtitle: string;
  scopeHighlights: string[];
  retentionPolicyDays: number;
  tenantModel: string;
  dataPolicy: string;
};

export function buildAppShell(): AppShell {
  return {
    title: "Sentellent",
    subtitle:
      "A tenant-scoped chief of staff for authentication, organization management, chat workflows, and task tracking.",
    scopeHighlights: [
      "authentication",
      "organization management",
      "chat workflows",
      "task tracking",
    ],
    retentionPolicyDays: 30,
    tenantModel: "shared PostgreSQL with tenant_id enforced across domain tables",
    dataPolicy: "Sensitive data is encrypted at rest and tenant-level deletion is supported.",
  };
}
