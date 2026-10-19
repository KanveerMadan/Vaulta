import { forwardRef } from "react";
import { useCategoryTree } from "../lib/categories";

/**
 * A native <select> over the two-level taxonomy: each group is an <optgroup> whose first option is the group itself,
 * followed by its subcategories (the user's own included). The value is a group name or a subcategory id.
 * `groupOption(name)` labels the group-level option (null: no group-level options); `empty` labels the "" option.
 */
const CategorySelect = forwardRef(function CategorySelect({ value, onChange, empty, groupOption = (g) => `${g} (general)`,
  groups: only, system = true, ...rest }, ref) {
  const tree = useCategoryTree();
  const groups = tree.groups.filter((g) => !only || only.includes(g.name));
  return (
    <select ref={ref} value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
      {empty !== undefined && <option value="">{empty}</option>}
      {groups.map((g) => (
        <optgroup key={g.name} label={g.name}>
          {groupOption && <option value={g.name}>{groupOption(g.name)}</option>}
          {g.subcategories.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </optgroup>
      ))}
      {system && (
        <optgroup label="Other">
          {tree.system_groups.filter((n) => !only || only.includes(n)).map((n) => <option key={n} value={n}>{n}</option>)}
        </optgroup>
      )}
    </select>
  );
});

export default CategorySelect;
