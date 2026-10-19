import api from './api'
import { toast } from './toast'
import { KINDS } from './categories'

/** "Applied Entertainment to 2 other Swiggy transactions. [Undo]" after an edit teaches a rule. */
export function ruleToast(rule, onChanged) {
  const what = rule.field === 'kind' ? (KINDS[rule.value]?.label ?? rule.value) : rule.value
  toast({
    message: rule.applied_count > 0
      ? `Applied ${what} to ${rule.applied_count} other ${rule.merchant} transaction${rule.applied_count === 1 ? '' : 's'}.`
      : `${rule.merchant} will be ${what} from now on.`,
    action: { label: 'Undo', onClick: async () => { await api.delete(`/api/rules/${rule.rule_id}`); onChanged?.() } },
  })
}
