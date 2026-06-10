// Validador mínimo: solo permite una sentencia SELECT o WITH.
// La defensa real está en la RPC `closzr_query` (SECURITY DEFINER con check).
// Esto es defensa-en-profundidad y mensajes de error más limpios para el modelo.

const FORBIDDEN = [
  /\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|comment|copy|vacuum|analyze|reindex|cluster|lock|call|do)\b/i,
];

export function assertReadOnlySql(sql: string): string {
  const trimmed = sql.trim().replace(/;\s*$/, "");
  if (!trimmed) throw new Error("Query vacía.");
  if (trimmed.includes(";")) throw new Error("Solo una sentencia por query.");
  if (!/^(select|with)\s/i.test(trimmed)) {
    throw new Error("Solo se permiten SELECT/WITH.");
  }
  for (const pattern of FORBIDDEN) {
    if (pattern.test(trimmed)) throw new Error("Operación no permitida.");
  }
  return trimmed;
}
