// The model writes **bold** for the key figure: show it bold, never the asterisks (an unclosed ** while the reply is
// still appearing stays plain until its pair arrives)
export const plain = (t) => t.replace(/\*\*([^*]+)\*\*/g, '$1')
export function withBold(t) {
  return t.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    /^\*\*[^*]+\*\*$/.test(part) ? <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong> : part)
}
